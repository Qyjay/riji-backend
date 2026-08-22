"""
小 V 语音指令意图识别。
LLM 负责判定意图和抽取槽位，超时 / 报错 / 返回非法结构时回落到中文关键词规则，
再兜底到 unknown（端侧打开首页），保证调用方永远拿得到一个合法结果。
"""
import asyncio
import json
import re
from typing import Iterable, Optional
from urllib.parse import quote

from app.config import settings


VOICE_INTENT_ACTIONS = (
    "quick_snap",
    "generate_diary",
    "generate_comic",
    "find_friend",
    "find_friend_with_req",
    "send_message",
    "unknown",
)

_SCORABLE_ACTIONS = (
    "quick_snap",
    "generate_diary",
    "generate_comic",
    "find_friend",
    "send_message",
)

# 同分时意图越具体越靠前
_TIE_BREAK_ORDER = (
    "generate_comic",
    "generate_diary",
    "quick_snap",
    "send_message",
    "find_friend",
)

_STRONG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "quick_snap": ("快拍", "拍照", "拍张照", "拍个照", "拍几张", "照相", "相机", "抓拍", "随手拍"),
    "generate_diary": ("日记", "写日记", "生成日记", "记一篇"),
    "generate_comic": ("漫画", "条漫", "四格", "漫画版"),
    "find_friend": ("找朋友", "找个朋友", "找一个朋友", "交朋友", "交个朋友", "认识新朋友", "找搭子", "找个搭子", "匹配朋友"),
    "send_message": ("发消息", "发条消息", "发个消息", "捎句话", "带句话", "留言", "私信"),
}

_WEAK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "quick_snap": ("拍", "照片", "相片"),
    "generate_diary": ("记录今天", "总结今天", "今日总结"),
    "generate_comic": ("漫", "画"),
    "find_friend": ("朋友", "搭子", "交友", "认识"),
    "send_message": ("说", "告诉", "消息"),
}

# 唤醒词和「在 avalin」这类前缀会污染打分与自由文本抽取，先摘掉
_WAKE_WORD_PATTERN = re.compile(r"小\s*v\s*小\s*v", re.IGNORECASE)

_APP_NAME_PATTERNS = (
    re.compile(r"(?:我)?(?:想|要|想要|准备)?在\s*avalin(?:里面|里|上|中)?", re.IGNORECASE),
    re.compile(r"avalin", re.IGNORECASE),
)

_LEADING_FILLER = re.compile(r"^[\s，,。.、！!？?：:]*(?:帮我|麻烦|请|我想要|我想|我要|然后)?[\s，,。.、！!？?：:]*")

_SEND_MESSAGE_PATTERNS = (
    # 跟搭子小明说晚上一起吃饭 / 给李悠然发条消息说明天见
    re.compile(
        r"(?:跟|和|给|向|对)\s*(?:我(?:的)?)?(?:搭子|朋友|好友|伙伴|同学)?\s*"
        r"([^\s，,。.、！!？?：:]{1,12}?)\s*"
        r"(?:说|讲|发(?:条|个|一条)?消息|留言|捎(?:句|个)话)[\s，,。.、：:]*(.*)$"
    ),
    # 告诉小明晚上一起吃饭
    re.compile(
        r"告诉\s*(?:我(?:的)?)?(?:搭子|朋友|好友|伙伴|同学)?\s*"
        r"([^\s，,。.、！!？?：:]{2,4}?)[\s，,。.、：:]*(.+)$"
    ),
)

_SEND_MESSAGE_BODY_PREFIX = re.compile(r"^[\s，,。.、：:]*(?:说|讲|告诉(?:他|她|它)?)?[\s，,。.、：:]*")

_FIND_FRIEND_PATTERN = re.compile(r"(?:找|认识|结识)(?:个|一个|位|新)*[^\s，,。.、]{0,20}?(?:的)?(?:朋友|搭子|伙伴|人)")

_FIND_REQUIREMENT_PATTERNS = (
    re.compile(r"(?:要求|条件|需求)[是为]?[\s，,。.、：:]*(.+)$"),
    re.compile(r"(?:想找|希望找|我想要|最好是|最好)[\s，,。.、：:]*(.+)$"),
    re.compile(r"(?:找|认识|结识)(?:个|一个|位|新)*(.{2,40}?)(?:的)?(?:朋友|搭子|伙伴)(?:[\s，,。.、！!]|$)"),
)

_SPEECH_BY_ACTION = {
    "quick_snap": "好，帮你打开相机了",
    "generate_diary": "好，正在用今天的记录生成日记",
    "generate_comic": "好，开始画今天的漫画",
    "find_friend": "好，帮你打开找朋友",
    "find_friend_with_req": "好，要求已经帮你填进去了",
    "send_message": "好，消息帮你填好了，确认一下就发",
    "unknown": "这句话我暂时没听懂，先带你回首页",
}

_SYSTEM_PROMPT = (
    "你是 Avalin 的语音指令解析器。用户对着 vivo 蓝心小 V 说一句话，你要判断他想在 Avalin 里做哪一件事。\n"
    "只输出一个 JSON 对象。禁止输出解释、禁止用 markdown 代码块、禁止任何多余文字。\n"
    "JSON 结构固定为：\n"
    '{"action": "<下列七个值之一>", "confidence": <0 到 1 的小数>, '
    '"slots": {"target": "", "text": "", "requirement": ""}}\n'
    "action 的七个取值及判定标准：\n"
    "- quick_snap：想拍照、发快拍、打开相机记录此刻。例：我想在avalin发个快拍；帮我拍张照记一下。\n"
    "- generate_diary：想让 AI 用今天已有的记录生成日记。例：我想在avalin生成日记；把今天的日记写出来。\n"
    "- generate_comic：想生成当天的漫画。例：我想在avalin生成当日漫画；给今天画个漫画。\n"
    "- find_friend：想找人、找朋友、找搭子，且没有说任何具体要求。例：我想在avalin找个朋友。\n"
    "- find_friend_with_req：想找人并且说了具体要求（时间、活动、性格、专业等任意条件）。"
    "把要求原样写进 slots.requirement，保持用户的口语原文，不要改写成书面语，不要补充用户没说的条件。"
    "例：我想在avalin找个朋友，要求周末能一起看电影 → requirement 填 周末能一起看电影。\n"
    "- send_message：想给某个已经认识的搭子或朋友发一条消息。"
    "slots.target 只填收信人昵称本身，不要带「我的」「搭子」「朋友」这类前缀；slots.text 填要发送的正文原文。"
    "例：我想在avalin跟我的搭子小明说晚上一起吃饭 → target 填 小明，text 填 晚上一起吃饭。\n"
    "- unknown：不属于以上六种，或信息太少无法判断。\n"
    "边界规则：\n"
    "1. 同时出现「日记」和「漫画」时以「漫画」为准，归到 generate_comic。\n"
    "2. 说了拍照但没有指明收信人时仍是 quick_snap；只有明确出现「跟某人说 / 告诉某人 / 给某人发消息」才是 send_message。\n"
    "3. 「找个一起看电影的朋友」这类带活动的表述属于 find_friend_with_req，requirement 填 一起看电影。\n"
    "4. 听不出收信人昵称时用 send_message 并把 target 留成空字符串，不要凭空编造名字。\n"
    "5. 用不到的槽位一律填空字符串，不要填 null，不要省略字段。\n"
    "6. confidence 表示你对本次判定的把握，取 0 到 1 之间的小数。"
)


def _clean_slot(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _strip_leading_filler(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    previous = ""
    while previous != text:
        previous = text
        text = _LEADING_FILLER.sub("", text).strip()
    return text


def strip_voice_preamble(utterance: str) -> str:
    """
    去掉唤醒词、App 名和「帮我 / 我想」这类没有信息量的开头。
    先剥一次开头再摘 App 名，否则「帮我在 avalin 里…」会剩下一个孤立的「帮」。
    """
    text = _strip_leading_filler(_WAKE_WORD_PATTERN.sub(" ", str(utterance or "")))
    for pattern in _APP_NAME_PATTERNS:
        text = pattern.sub(" ", text)
    return _strip_leading_filler(text)


def _count_hits(text: str, keywords: Iterable[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _extract_send_message_slots(text: str) -> Optional[dict]:
    for pattern in _SEND_MESSAGE_PATTERNS:
        hit = pattern.search(text)
        if not hit:
            continue
        target = _clean_slot(hit.group(1))
        if not target:
            continue
        body = _clean_slot(_SEND_MESSAGE_BODY_PREFIX.sub("", hit.group(2) or ""))
        return {"target": target, "text": body}
    return None


def _extract_find_requirement(text: str) -> str:
    for pattern in _FIND_REQUIREMENT_PATTERNS:
        hit = pattern.search(text)
        if not hit:
            continue
        requirement = _clean_slot(hit.group(1))
        if requirement:
            return requirement
    return ""


def _empty_slots() -> dict:
    return {"target": "", "text": "", "requirement": ""}


def _result(action: str, confidence: float, slots: dict, source: str) -> dict:
    return {
        "action": action,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 2),
        "slots": slots,
        "source": source,
    }


def parse_by_keywords(utterance: str) -> dict:
    """确定性关键词规则，AI 不可用时的兜底。"""
    text = strip_voice_preamble(utterance)
    if not text:
        return _result("unknown", 0.0, _empty_slots(), "keywords")

    lowered = text.lower()
    message = _extract_send_message_slots(text)
    requirement = _extract_find_requirement(text)

    scores = {
        action: _count_hits(lowered, _STRONG_KEYWORDS[action]) * 3
        + _count_hits(lowered, _WEAK_KEYWORDS[action])
        for action in _SCORABLE_ACTIONS
    }
    if message:
        scores["send_message"] += 4
    if _FIND_FRIEND_PATTERN.search(text):
        scores["find_friend"] += 4

    best = max(scores.values())
    if best <= 0:
        return _result("unknown", 0.0, _empty_slots(), "keywords")

    winner = next((action for action in _TIE_BREAK_ORDER if scores[action] == best), "unknown")
    confidence = 0.7 if best >= 6 else 0.55 if best >= 3 else 0.4

    if winner == "send_message":
        slots = _empty_slots()
        slots["target"] = (message or {}).get("target", "")
        slots["text"] = (message or {}).get("text", "")
        return _result("send_message", confidence, slots, "keywords")

    if winner == "find_friend":
        slots = _empty_slots()
        slots["requirement"] = requirement
        action = "find_friend_with_req" if requirement else "find_friend"
        return _result(action, confidence, slots, "keywords")

    return _result(winner, confidence, _empty_slots(), "keywords")


def _extract_first_json_object(raw: str) -> Optional[dict]:
    text = str(raw or "").strip()
    if not text:
        return None
    depth = 0
    start = -1
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    parsed = json.loads(text[start:index + 1])
                except Exception:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def normalize_llm_payload(raw: str) -> Optional[dict]:
    """模型输出校验；结构非法时返回 None，由调用方回落到关键词结果。"""
    payload = _extract_first_json_object(raw)
    if not payload:
        return None

    action = _clean_slot(payload.get("action"))
    if action not in VOICE_INTENT_ACTIONS:
        return None

    raw_slots = payload.get("slots")
    raw_slots = raw_slots if isinstance(raw_slots, dict) else {}
    slots = {
        "target": _clean_slot(raw_slots.get("target")),
        "text": _clean_slot(raw_slots.get("text")),
        "requirement": _clean_slot(raw_slots.get("requirement")),
    }

    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.5

    return _result(action, confidence, slots, "llm")


def _merge_with_fallback(remote: dict, fallback: dict) -> dict:
    """模型定意图，槽位漏抽时用关键词结果补齐。"""
    slots = {
        key: remote["slots"].get(key) or fallback["slots"].get(key, "")
        for key in ("target", "text", "requirement")
    }
    action = remote["action"]
    if action == "find_friend" and slots["requirement"]:
        action = "find_friend_with_req"
    return _result(action, remote["confidence"], slots, remote["source"])


def build_deeplink(action: str, slots: dict) -> str:
    """给端侧一条可直接执行的 deep link，同时也是快捷指令可以照抄的形态。"""
    target = str(slots.get("target") or "")
    text = str(slots.get("text") or "")
    requirement = str(slots.get("requirement") or "")

    if action == "quick_snap":
        return "avalin://snap"
    if action == "generate_diary":
        return "avalin://memory/generate"
    if action == "generate_comic":
        return "avalin://comic/today"
    if action == "find_friend":
        return "avalin://social/find"
    if action == "find_friend_with_req":
        if not requirement:
            return "avalin://social/find"
        return f"avalin://social/find?intent={quote(requirement, safe='')}"
    if action == "send_message":
        if not target:
            return "avalin://messages"
        link = f"avalin://say?to={quote(target, safe='')}"
        if text:
            link += f"&text={quote(text, safe='')}"
        return link
    return "avalin://home"


async def parse_voice_intent(utterance: str) -> dict:
    """AI 判定意图，超时 / 报错 / 返回非法结构时回落关键词规则。"""
    fallback = parse_by_keywords(utterance)
    text = str(utterance or "").strip()
    if not text:
        return fallback

    from app.ai.minimax_client import get_minimax_client

    client = get_minimax_client()
    if client.mock:
        return fallback

    try:
        raw = await asyncio.wait_for(
            client.chat_completion(
                [{"role": "user", "content": f"用户说：{text[:400]}"}],
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=256,
            ),
            timeout=float(settings.VOICE_INTENT_TIMEOUT_SEC),
        )
    except Exception:
        return fallback

    remote = normalize_llm_payload(raw)
    if not remote or remote["action"] == "unknown":
        return fallback
    return _merge_with_fallback(remote, fallback)


async def resolve_voice_intent(utterance: str) -> dict:
    """接口层出口：补上 deeplink 与语音回执文案。"""
    intent = await parse_voice_intent(utterance)
    return {
        **intent,
        "deeplink": build_deeplink(intent["action"], intent["slots"]),
        "speech": _SPEECH_BY_ACTION.get(intent["action"], _SPEECH_BY_ACTION["unknown"]),
    }

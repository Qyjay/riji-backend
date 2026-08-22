"""
广场帖子板块分类
用 LLM 识别正文归属的板块，失败时回落到中文关键词规则，最后回落到安全默认值。
"""
import asyncio
import re
from typing import Iterable, Optional

from app.config import settings


PLAZA_POST_TYPES = ("buddy", "help", "dating", "share")
DEFAULT_PLAZA_POST_TYPE = "share"

_LABEL_TO_TYPE = {
    "找搭子": "buddy",
    "求助": "help",
    "恋爱": "dating",
    "分享": "share",
}

# 命中即基本可判定的强信号，权重高于泛化词
_STRONG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dating": (
        "恋爱", "谈恋爱", "处对象", "找对象", "脱单", "单身", "女朋友", "男朋友",
        "女友", "男友", "暗恋", "表白", "心动", "相亲", "奔现", "约会", "情侣",
        "伴侣", "喜欢的人", "分手", "前男友", "前女友", "cp",
    ),
    "help": (
        "求助", "帮帮", "求帮忙", "怎么办", "咋办", "求解", "求教", "请教",
        "有没有人知道", "谁知道", "求推荐", "求攻略", "求带", "急需", "跪求",
        "丢了", "捡到", "失物", "找回", "挂科", "补考", "退课", "有偿",
    ),
    "buddy": (
        "搭子", "结伴", "组队", "队友", "拼车", "拼单", "招募", "缺人", "还差",
        "找人一起", "有人一起", "一起去", "一起打", "一起看", "一起学",
        "约球", "开黑", "同行",
    ),
    "share": (
        "分享", "记录一下", "打卡", "安利", "测评", "出片", "vlog", "随手拍",
        "推荐给大家", "碎片记录",
    ),
}

# 泛化词，只在没有强信号时用来拉开差距
_WEAK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dating": ("感情", "喜欢", "心事", "亲密", "长期关系"),
    "help": ("请问", "麻烦", "建议", "咨询", "不知道该", "有偿", "帮我看看", "为什么"),
    "buddy": ("一起", "组个", "报名", "凑", "蹲", "自习", "健身", "剧本杀", "看展"),
    "share": ("今天", "今晚", "刚刚", "好吃", "好看", "心得", "总结", "感受", "攻略", "日常"),
}

# 同分时的兜底优先级：意图越明确越靠前
_TIE_BREAK_ORDER = ("help", "dating", "buddy", "share")

_SYSTEM_PROMPT = (
    "你是校园社区的帖子分类器。只输出一个板块名，禁止输出解释、标点、引号或任何其他文字。\n"
    "四个板块及判定标准：\n"
    "- 找搭子：想约人一起做一件具体的事，或长期找固定伙伴。例：本周六想找人看电影；找个一起备考的自习搭子；缺一个羽毛球球友；找合租室友。\n"
    "- 求助：遇到困难，需要别人给信息、经验或帮忙。例：选课系统进不去怎么办；图书馆丢了饭卡有人捡到吗；想问下这门课好过吗。\n"
    "- 恋爱：明确在找恋爱对象，或在讲自己的恋爱、暗恋、表白、分手困扰。例：想认真谈一段恋爱；暗恋同班同学两年了；和对象吵架了很难过。\n"
    "- 分享：记录或分享见闻、心得、图片、攻略，不需要别人一起行动。例：今天食堂新窗口很好吃；期末复习方法总结；拍到很好看的晚霞。\n"
    "边界规则：\n"
    "1. 写着「想找人一起」但目的是建立恋爱关系时，归到 恋爱。\n"
    "2. 涉及恋爱话题但实质是在问怎么办、求建议时，归到 求助。\n"
    "3. 招募帖不一定是找搭子；如果内容明显是求助、恋爱或分享，按内容判定。\n"
    "4. 只讲自己的经历、不需要别人回应时，归到 分享。\n"
    "只能输出以下四个词之一：找搭子、求助、恋爱、分享"
)


def normalize_post_type(value: object) -> Optional[str]:
    """把中英文板块写法归一成枚举 key；无法识别返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in PLAZA_POST_TYPES:
        return lowered
    return _LABEL_TO_TYPE.get(text)


def _score(text: str, keywords: Iterable[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def classify_by_keywords(
    content: str,
    tags: Optional[Iterable[str]] = None,
    default: str = DEFAULT_PLAZA_POST_TYPE,
) -> str:
    """确定性关键词规则，AI 不可用时的兜底。"""
    haystack = " ".join([str(content or ""), *(str(tag or "") for tag in tags or [])]).lower()
    if not haystack.strip():
        return default if default in PLAZA_POST_TYPES else DEFAULT_PLAZA_POST_TYPE

    scores = {
        post_type: _score(haystack, _STRONG_KEYWORDS[post_type]) * 3
        + _score(haystack, _WEAK_KEYWORDS[post_type])
        for post_type in PLAZA_POST_TYPES
    }
    best = max(scores.values())
    if best <= 0:
        return default if default in PLAZA_POST_TYPES else DEFAULT_PLAZA_POST_TYPE

    for post_type in _TIE_BREAK_ORDER:
        if scores[post_type] == best:
            return post_type
    return default if default in PLAZA_POST_TYPES else DEFAULT_PLAZA_POST_TYPE


def _parse_model_output(raw: str) -> Optional[str]:
    text = re.sub(r"[\s\"'`。，,.：:；;！!\[\]{}]", "", str(raw or ""))
    if not text:
        return None
    matched = [label for label in _LABEL_TO_TYPE if label in text]
    if len(matched) == 1:
        return _LABEL_TO_TYPE[matched[0]]
    return normalize_post_type(text)


async def classify_post_type(
    content: str,
    tags: Optional[Iterable[str]] = None,
    default: str = DEFAULT_PLAZA_POST_TYPE,
) -> str:
    """AI 判定板块，超时/报错/返回非法值时回落关键词规则。"""
    fallback = classify_by_keywords(content, tags, default=default)
    text = str(content or "").strip()
    if not text:
        return fallback

    from app.ai.minimax_client import get_minimax_client

    client = get_minimax_client()
    if client.mock:
        return fallback

    tag_line = "、".join(str(tag or "").strip() for tag in tags or [] if str(tag or "").strip())
    user_prompt = f"帖子正文：\n{text[:1200]}"
    if tag_line:
        user_prompt += f"\n话题标签：{tag_line}"

    try:
        raw = await asyncio.wait_for(
            client.chat_completion(
                [{"role": "user", "content": user_prompt}],
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=24,
            ),
            timeout=float(settings.PLAZA_CLASSIFY_TIMEOUT_SEC),
        )
    except Exception:
        return fallback

    return _parse_model_output(raw) or fallback


async def resolve_post_type(
    content: str,
    tags: Optional[Iterable[str]] = None,
    requested: object = None,
    default: str = DEFAULT_PLAZA_POST_TYPE,
) -> str:
    """用户显式选择优先；没选或选了非法值时才让 AI 判定。"""
    explicit = normalize_post_type(requested)
    if explicit:
        return explicit
    return await classify_post_type(content, tags, default=default)

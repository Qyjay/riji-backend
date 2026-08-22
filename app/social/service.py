"""
社交模块服务层
"""
import json
import logging
import re
import time
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.minimax_client import get_minimax_client
from app.models.social import Match, SocialMessage
from app.models.user import User
from app.models.user_profile import UserProfile
from app.response import ApiException, NOT_FOUND, PARAM_ERROR

logger = logging.getLogger("uvicorn.error")


def _encode(obj, default="") -> str:
    if obj is None:
        return default
    return json.dumps(obj, ensure_ascii=False)


def _decode(s, default=None):
    if default is None:
        default = []
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def get_other_user_id(match: Match, current_user_id: str) -> str:
    """获取对方用户 ID"""
    return match.target_id if match.user_id == current_user_id else match.user_id


def _match_reason(raw_report: str) -> str:
    """将历史 JSON 匹配报告转换为列表可展示的摘要。"""
    text = str(raw_report or "").strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text
    if isinstance(parsed, str):
        return parsed.strip()
    if not isinstance(parsed, dict):
        return text

    reason = str(parsed.get("reason") or "").strip()
    if reason:
        return reason
    analysis = str(parsed.get("analysis") or "").strip()
    if analysis:
        return analysis
    common_points = parsed.get("common_points", parsed.get("commonPoints", []))
    if isinstance(common_points, list):
        points = [str(item).strip() for item in common_points if str(item).strip()]
        if points:
            return f"共同点：{'、'.join(points[:3])}"
    return ""


def match_to_out(match: Match, current_user_id: str, db: Session) -> dict:
    """匹配记录转前端格式（需要 JOIN 用户信息）"""
    other_id = get_other_user_id(match, current_user_id)
    other_user = db.query(User).filter(User.id == other_id).first()

    mission = None
    if match.mission_id:
        from app.models.social import SocialMission

        mission = db.query(SocialMission).filter(SocialMission.id == match.mission_id).first()

    return {
        "id": match.id,
        "user_id": other_user.id if other_user else "",
        "nickname": other_user.name or other_user.username if other_user else "",
        "avatar": other_user.avatar or "" if other_user else "",
        "school": other_user.school or "" if other_user else "",
        "common_tags": _decode(match.common_tags, []),
        "matched_at": match.created_at,
        "status": match.status or "pending",
        "match_type": match.match_type or "long_term",
        "request_direction": "outgoing" if match.user_id == current_user_id else "incoming",
        "reason": _match_reason(match.match_report or ""),
        "mission_id": match.mission_id,
        "mission_title": mission.title if mission else None,
        "mission_mode": mission.mode if mission else None,
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _get_match(db: Session, match_id: str) -> Optional[Match]:
    return db.query(Match).filter(Match.id == match_id).first()


def _get_match_for_user(db: Session, match_id: str, user_id: str) -> Match:
    match = _get_match(db, match_id)
    if not match:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    if match.user_id != user_id and match.target_id != user_id:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    return match


def _profile_to_dict(profile: Optional[UserProfile]) -> dict:
    if not profile:
        return {}
    return {
        "personality": profile.personality or "",
        "interests": _decode(profile.interests, []),
    }


def _avatar_card_to_dict(card) -> dict:
    if not card:
        return {}
    return {
        "display_name": card.display_name or "",
        "public_summary": card.public_summary or "",
        "interest_tags": _decode(card.interest_tags, []),
        "social_intent": _decode(card.social_intent, []),
        "conversation_style": _decode(card.conversation_style, {}),
        "boundaries": _decode(card.boundaries, []),
    }


_MATCH_SCORE_KEYS = ("compatibility", "matchScore", "match_score", "score")
_MATCH_REPORT_FALLBACK_SCORE = 75
_MATCH_ANALYSIS_MAX_CHARS = 600

# 内容分析固定维度：key 入库/API，label 给模型与前端展示
_MATCH_DIMENSION_SPECS = (
    ("interest_fit", "兴趣契合"),
    ("rhythm_fit", "作息节奏"),
    ("communication_style", "沟通风格"),
    ("values_fit", "价值观"),
    ("social_boundary", "社交边界"),
    ("short_term_goal", "短期目标契合"),
)
_MATCH_DIMENSION_KEYS = tuple(key for key, _ in _MATCH_DIMENSION_SPECS)
_MATCH_DIMENSION_LABELS = {key: label for key, label in _MATCH_DIMENSION_SPECS}

_MATCH_REPORT_SYSTEM_PROMPT = (
    "你是社交匹配分析师。只输出一个合法 JSON 对象，不要输出解释、Markdown 代码块或任何多余文字。\n"
    "字段约定（全部必填，除非标注可选）：\n"
    "  compatibility：整数 0-100，两人的综合匹配度（总圆环只用这个数字，不要另算）\n"
    "  summary：字符串，一句话总结（20 字以内）\n"
    "  analysis：字符串，120-220 字中文匹配分析，友好、有温度、可执行\n"
    "  dimensions：对象，固定包含以下 6 个键；每个值是 {\"score\":0-100,\"reason\":\"一句依据\"}\n"
    "    interest_fit（兴趣契合）、rhythm_fit（作息节奏）、communication_style（沟通风格）、\n"
    "    values_fit（价值观）、social_boundary（社交边界）、short_term_goal（短期目标契合）\n"
    "  common_points：字符串数组，至少 3 条具体共同点\n"
    "  differences：字符串数组，至少 2 条具体差异点\n"
    "  suggestions：字符串数组，2-4 条可执行相处建议\n"
    "  risks：字符串数组，0-2 条风险提示（没有就 []）\n"
    "完整示例：\n"
    '{"compatibility":86,"summary":"运动与安静节奏很合拍",'
    '"analysis":"你们都习惯用运动整理情绪，聊起跑步很容易接上话，相处节奏也都偏安静，'
    '适合先约一次夜跑再慢慢熟起来。沟通都偏直接，边界意识也清楚，短期一起完成一场活动的成功率较高。",'
    '"dimensions":{'
    '"interest_fit":{"score":90,"reason":"都在坚持跑步并愿意分享进度"},'
    '"rhythm_fit":{"score":78,"reason":"都偏晚间活动，周末也能对上"},'
    '"communication_style":{"score":84,"reason":"说话都偏直接、不绕弯"},'
    '"values_fit":{"score":80,"reason":"都重视个人空间与真诚"},'
    '"social_boundary":{"score":88,"reason":"都倾向小范围深度社交"},'
    '"short_term_goal":{"score":85,"reason":"都想先找固定运动搭子"}'
    '},'
    '"common_points":["都在坚持跑步","都偏好安静的相处方式","都愿意先从线下小活动熟起来"],'
    '"differences":["作息节奏略有早晚差","对社交密度的需求不同"],'
    '"suggestions":["先约一次 40 分钟轻松夜跑","跑后简短复盘彼此节奏"],'
    '"risks":["避免一开始就安排全天行程"]}'
)

_MOCK_MATCH_REPORT = {
    "compatibility": 85,
    "summary": "学习与生活方式很契合",
    "analysis": "你们有很多共同点，在学习和生活方式上非常契合！沟通都偏真诚，短期一起完成小目标的成功率较高。",
    "dimensions": {
        "interest_fit": {"score": 88, "reason": "都喜欢记录生活与分享兴趣"},
        "rhythm_fit": {"score": 72, "reason": "作息接近但略有早晚差"},
        "communication_style": {"score": 84, "reason": "交流都偏直接友好"},
        "values_fit": {"score": 86, "reason": "都重视成长与真诚"},
        "social_boundary": {"score": 80, "reason": "都接受循序渐进的社交"},
        "short_term_goal": {"score": 83, "reason": "都愿意先从短期活动开始"},
    },
    "common_points": ["都喜欢记录生活", "学习态度积极", "兴趣爱好相近"],
    "differences": ["作息时间略有差异", "对社交的需求程度不同"],
    "suggestions": ["先约一次轻松的线下小活动", "活动后用几句话确认下次节奏"],
    "risks": [],
}

_GENERIC_ANALYSIS = "匹配度较高，有共同语言。"
_GENERIC_SUMMARY = "你们有继续认识的基础"
_GENERIC_COMMON_POINTS = ["有共同兴趣", "相处氛围偏友好", "愿意尝试短期一起行动"]
_GENERIC_DIFFERENCES = ["性格略有差异", "日常节奏不完全相同"]
_GENERIC_SUGGESTIONS = ["先从一次短活动开始熟悉彼此节奏", "见面后用几句话确认下次安排"]
_GENERIC_RISKS: list[str] = []
_GENERIC_DIMENSIONS = {
    key: {"score": _MATCH_REPORT_FALLBACK_SCORE, "reason": "画像信息有限，先按中性估计"}
    for key in _MATCH_DIMENSION_KEYS
}

# 模型只给自然语言时的兜底来源：用户在正文里看到的「匹配度 90%」就出自这类写法
_TEXT_SCORE_PATTERNS = (
    r"(?:匹配度|契合度|适配度|相似度|compatibility|match[\s_-]?score)\s*(?:是|为|达到|[:：=])?\s*(\d{1,3}(?:\.\d+)?)",
    r"(\d{1,3}(?:\.\d+)?)\s*%",
    r"(\d{1,3})\s*分",
)


def _clamp_score(raw_score, *, fallback: int = _MATCH_REPORT_FALLBACK_SCORE) -> int:
    try:
        score = float(raw_score)
        if 0 <= score <= 1:
            score *= 100
        return round(max(0, min(100, score)))
    except (TypeError, ValueError):
        return int(fallback)


def _normalize_dimension_entry(raw, *, fallback_score: int) -> dict:
    if isinstance(raw, dict):
        score = _clamp_score(
            raw.get("score", raw.get("compatibility", fallback_score)),
            fallback=fallback_score,
        )
        reason = str(raw.get("reason") or raw.get("evidence") or raw.get("desc") or "").strip()
    else:
        score = _clamp_score(raw, fallback=fallback_score)
        reason = ""
    if not reason:
        reason = "暂无更细依据"
    return {"score": score, "reason": reason}


def _normalize_dimensions(report_data: dict, *, fallback_score: int) -> list[dict]:
    raw_dimensions = report_data.get("dimensions")
    had_source = False
    if isinstance(raw_dimensions, dict):
        had_source = bool(raw_dimensions)
    elif isinstance(raw_dimensions, list):
        by_key = {}
        for item in raw_dimensions:
            if isinstance(item, dict) and item.get("key"):
                by_key[str(item["key"])] = item
                had_source = True
        raw_dimensions = by_key
    else:
        raw_dimensions = {}

    flat_aliases = {
        "interest_fit": ("interest_fit", "interestFit", "兴趣契合"),
        "rhythm_fit": ("rhythm_fit", "rhythmFit", "作息节奏"),
        "communication_style": ("communication_style", "communicationStyle", "沟通风格"),
        "values_fit": ("values_fit", "valuesFit", "价值观"),
        "social_boundary": ("social_boundary", "socialBoundary", "社交边界"),
        "short_term_goal": ("short_term_goal", "shortTermGoal", "短期目标契合", "短期目标"),
    }
    if not had_source:
        for aliases in flat_aliases.values():
            if any(alias in report_data for alias in aliases):
                had_source = True
                break
    if not had_source:
        return []

    normalized = []
    for key in _MATCH_DIMENSION_KEYS:
        entry = raw_dimensions.get(key)
        if entry is None:
            for alias in flat_aliases.get(key, ()):
                if alias in raw_dimensions:
                    entry = raw_dimensions[alias]
                    break
                if alias in report_data:
                    entry = report_data[alias]
                    break
        if entry is None:
            entry = _GENERIC_DIMENSIONS[key]
        item = _normalize_dimension_entry(entry, fallback_score=fallback_score)
        item["key"] = key
        item["label"] = _MATCH_DIMENSION_LABELS[key]
        normalized.append(item)
    return normalized


def _normalize_match_report(report_data: dict) -> dict:
    raw_score = next(
        (
            report_data.get(key)
            for key in _MATCH_SCORE_KEYS
            if report_data.get(key) is not None
        ),
        _MATCH_REPORT_FALLBACK_SCORE,
    )
    score = _clamp_score(raw_score)
    analysis = str(report_data.get("analysis") or "").strip()
    summary = str(report_data.get("summary") or "").strip()
    if not analysis and summary:
        analysis = summary
    if not summary and analysis:
        summary = analysis[:24]
    common_points = report_data.get("common_points", report_data.get("commonPoints", []))
    differences = report_data.get("differences", [])
    suggestions = report_data.get("suggestions", report_data.get("建议", []))
    risks = report_data.get("risks", report_data.get("风险", []))
    return {
        "compatibility": score,
        "summary": summary,
        "analysis": analysis,
        "dimensions": _normalize_dimensions(report_data, fallback_score=score),
        "common_points": common_points if isinstance(common_points, list) else _string_list(common_points),
        "differences": differences if isinstance(differences, list) else _string_list(differences),
        "suggestions": suggestions if isinstance(suggestions, list) else _string_list(suggestions),
        "risks": risks if isinstance(risks, list) else _string_list(risks),
    }


def _match_report_user_prompt(portrait_a: dict, portrait_b: dict) -> str:
    return (
        f"用户A画像：{json.dumps(portrait_a, ensure_ascii=False)}\n"
        f"用户B画像：{json.dumps(portrait_b, ensure_ascii=False)}\n"
        "请严格按系统提示的字段约定，只输出一个 JSON 对象。"
        "compatibility 必须是综合匹配度整数；dimensions 六个键缺一不可；"
        "common_points 至少 3 条，differences 至少 2 条，suggestions 2-4 条。"
    )


def _balanced_object_spans(text: str) -> list[str]:
    """扫出所有花括号配对的片段，字符串内部的花括号不参与配对。"""
    spans: list[str] = []
    depth = 0
    start = -1
    quote = ""
    escaped = False
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if depth > 0 and char in "\"'":
            quote = char
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append(text[start:index + 1])
    return spans


def _repair_json_text(text: str) -> str:
    """修模型常见的坏习惯：中文引号、结构位置的全角标点、单引号包裹、尾随逗号。"""
    repaired = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    repaired = re.sub(r'"\s*：', '":', repaired)
    repaired = re.sub(r'([}\]\d"])\s*，\s*(?=["}\]])', r"\1,", repaired)
    repaired = re.sub(r"'([^'\n]*)'", r'"\1"', repaired)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return repaired


def _extract_json_object(raw: str) -> Optional[dict]:
    """从模型输出里提取第一个能解析的 JSON 对象。

    候选按可信度排序：整段文本 → 代码块内容 → 每个配对的花括号片段；
    每个候选先原样解析，失败再用 `_repair_json_text` 试一次。
    """
    text = str(raw or "").strip()
    if not text:
        return None

    candidates = [text]
    candidates.extend(
        block.strip() for block in re.findall(r"```[a-zA-Z]*\s*([\s\S]*?)```", text)
    )
    candidates.extend(_balanced_object_spans(text))

    for candidate in candidates:
        if not candidate:
            continue
        for attempt in (candidate, _repair_json_text(candidate)):
            try:
                parsed = json.loads(attempt)
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def _score_from_text(text: str) -> Optional[float]:
    for pattern in _TEXT_SCORE_PATTERNS:
        for hit in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = float(hit.group(1))
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 100:
                return value
    return None


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        items = [part.strip() for part in re.split(r"[、,，;；\n]", value)]
    elif isinstance(value, (list, tuple)):
        items = [str(part).strip() for part in value]
    else:
        items = []
    return [item for item in items if item]


def _readable_analysis(text: str) -> str:
    flat = re.sub(r"```[a-zA-Z]*", " ", str(text or "")).replace("```", " ").strip()
    return flat[:_MATCH_ANALYSIS_MAX_CHARS] if flat else _GENERIC_ANALYSIS


def _match_report_payload_from_raw(raw_report: str) -> dict:
    """把模型原始输出整理成 `_normalize_match_report` 能接收的字典。

    分数取值顺序：结构化字段 → 正文正则抽取 → 兜底分。
    """
    text = str(raw_report or "")
    preview = " ".join(text.split())[:200]

    parsed = _extract_json_object(text)
    if parsed is None:
        logger.warning("匹配报告未解析出 JSON，转为正文抽取；模型原始输出：%s", preview)
        payload: dict = {}
    else:
        payload = dict(parsed)

    if all(payload.get(key) is None for key in _MATCH_SCORE_KEYS):
        score = _score_from_text(text)
        if score is None:
            logger.warning(
                "匹配报告既无结构化分数也无法从正文抽取，回落兜底分 %s；模型原始输出：%s",
                _MATCH_REPORT_FALLBACK_SCORE,
                preview,
            )
        else:
            logger.info("匹配报告分数取自正文抽取：%s", score)
            payload["compatibility"] = score

    analysis = str(payload.get("analysis") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    if not analysis:
        payload["analysis"] = _readable_analysis(text)
    else:
        payload["analysis"] = analysis
    if not summary:
        # 成功解析时用结构化正文开头作摘要，避免再截断 raw[:200]
        source = str(payload.get("analysis") or "").strip()
        payload["summary"] = (source[:24] if source else _GENERIC_SUMMARY)
    else:
        payload["summary"] = summary

    payload["common_points"] = (
        _string_list(payload.get("common_points", payload.get("commonPoints")))
        or list(_GENERIC_COMMON_POINTS)
    )
    payload["differences"] = _string_list(payload.get("differences")) or list(_GENERIC_DIFFERENCES)
    payload["suggestions"] = (
        _string_list(payload.get("suggestions", payload.get("建议")))
        or list(_GENERIC_SUGGESTIONS)
    )
    payload["risks"] = _string_list(payload.get("risks", payload.get("风险")))
    if parsed is not None:
        dims = payload.get("dimensions")
        if not isinstance(dims, (dict, list)) or not dims:
            payload["dimensions"] = dict(_GENERIC_DIMENSIONS)
    return payload


def _match_status_priority(status: Optional[str]) -> int:
    if status == "accepted":
        return 2
    if status == "pending":
        return 1
    return 0


def _representative_match_for_pair(db: Session, match: Match) -> Match:
    """
    同一对用户可能跨事件留下多条 match。报告统一挂在代表 match 上：
    accepted 优先，再取 created_at 最新，最后按 id 倒序打破平局。

    与前端 `compareRepresentativeMatch` 同一套规则，因此聊天页、活动房间、
    A 与 B 双方拿到的都是同一份报告。
    """
    siblings = db.query(Match).filter(
        ((Match.user_id == match.user_id) & (Match.target_id == match.target_id))
        | ((Match.user_id == match.target_id) & (Match.target_id == match.user_id))
    ).all()
    if len(siblings) <= 1:
        return match
    return max(
        siblings,
        key=lambda row: (
            _match_status_priority(row.status),
            row.created_at or 0,
            str(row.id),
        ),
    )


def list_matches(db: Session, user_id: str, include_pending: bool = False) -> list[dict]:
    """查询匹配列表；默认仅已接受（与历史行为一致）。include_pending=True 时包含 pending，便于核对搭子申请。"""
    q = db.query(Match).filter(
        (Match.user_id == user_id) | (Match.target_id == user_id),
    )
    if include_pending:
        q = q.filter(Match.status.in_(["accepted", "pending"]))
    else:
        q = q.filter(Match.status == "accepted")
    matches = q.order_by(Match.created_at.desc()).all()
    return [match_to_out(match, user_id, db) for match in matches]


def create_match_request(db: Session, user_id: str, target_uid: Optional[str]) -> Match:
    """创建长期匹配请求"""
    if not target_uid:
        raise ApiException(code=PARAM_ERROR, message="toUid 不能为空", status_code=400)

    target = db.query(User).filter(User.id == target_uid).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    existing = db.query(Match).filter(
        ((Match.user_id == user_id) & (Match.target_id == target_uid))
        | ((Match.user_id == target_uid) & (Match.target_id == user_id))
    ).first()
    if existing:
        raise ApiException(code=PARAM_ERROR, message="已存在匹配请求", status_code=400)

    match = Match(
        id=_uuid(),
        user_id=user_id,
        target_id=target_uid,
        common_tags=_encode([], "[]"),
        status="pending",
        match_type="long_term",
        created_at=_now_ms(),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


def get_messages(
    db: Session,
    user_id: str,
    match_id: str,
    limit: int = 50,
    before: Optional[str] = None,
) -> list[SocialMessage]:
    """获取指定匹配的聊天记录"""
    match = _get_match_for_user(db, match_id, user_id)

    match_ids = [match.id]
    if match.status == "accepted":
        related = db.query(Match.id).filter(
            Match.status == "accepted",
            (
                ((Match.user_id == match.user_id) & (Match.target_id == match.target_id))
                | ((Match.user_id == match.target_id) & (Match.target_id == match.user_id))
            ),
        ).all()
        match_ids = [row[0] for row in related]

    query = db.query(SocialMessage).filter(SocialMessage.match_id.in_(match_ids))
    if before:
        pivot = db.query(SocialMessage).filter(SocialMessage.id == before).first()
        if pivot:
            query = query.filter(SocialMessage.timestamp < pivot.timestamp)

    return query.order_by(SocialMessage.timestamp.desc()).limit(limit).all()


def send_message(db: Session, user_id: str, match_id: str, content: str) -> SocialMessage:
    """发送社交消息，要求匹配已接受且当前用户属于该匹配"""
    match = _get_match_for_user(db, match_id, user_id)
    if match.status != "accepted":
        raise ApiException(code=PARAM_ERROR, message="匹配未通过，暂时不能发送消息", status_code=400)

    clean_content = content.strip()
    if not clean_content:
        raise ApiException(code=PARAM_ERROR, message="消息内容不能为空", status_code=400)

    message = SocialMessage(
        id=_uuid(),
        match_id=match_id,
        from_uid=user_id,
        content=clean_content,
        timestamp=_now_ms(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    from app.memory.ingestion import ingest_social_message

    ingest_social_message(db, message)
    return message


def _preserved_match_reason(match: Match) -> str:
    """match_report 同时承载搭子申请理由；重新生成前先把纯文本理由取出来，列表文案不会被覆盖。"""
    raw = str(match.match_report or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return raw
    if isinstance(parsed, dict):
        return str(parsed.get("reason") or "").strip()
    if isinstance(parsed, str):
        return parsed.strip()
    return ""


def _cached_match_report(match: Match) -> Optional[dict]:
    raw = str(match.match_report or "").strip()
    if not raw:
        return None
    try:
        cached = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return _normalize_match_report(cached) if isinstance(cached, dict) else None


def _match_portraits(db: Session, match: Match) -> tuple[dict, dict]:
    """按 match 固定的双方顺序取画像，两人拿到的上下文因此完全一致。"""
    from app.models.memory import AvatarCard

    portraits = []
    for uid in (match.user_id, match.target_id):
        profile = db.query(UserProfile).filter(UserProfile.user_id == uid).first()
        card = db.query(AvatarCard).filter(AvatarCard.user_id == uid).first()
        portrait = _profile_to_dict(profile)
        if card:
            portrait["avatar_card"] = _avatar_card_to_dict(card)
        portraits.append(portrait)
    return portraits[0], portraits[1]


async def _generate_match_report_data(match_id: str, portrait_a: dict, portrait_b: dict) -> dict:
    client = get_minimax_client()
    if client.mock:
        return dict(_MOCK_MATCH_REPORT)

    messages = [{"role": "user", "content": _match_report_user_prompt(portrait_a, portrait_b)}]
    call_kwargs = {
        "system_prompt": _MATCH_REPORT_SYSTEM_PROMPT,
        "temperature": 0.5,
        "max_tokens": 2048,
    }
    try:
        try:
            raw_report = await client.chat_completion(
                messages,
                response_format={"type": "json_object"},
                **call_kwargs,
            )
        except Exception as json_mode_error:
            # 部分模型/网关不支持 response_format，回退普通补全，靠解析层兜底
            logger.warning(
                "匹配报告 JSON mode 不可用，回退普通补全：%s",
                str(json_mode_error)[:200],
            )
            raw_report = await client.chat_completion(messages, **call_kwargs)
    except Exception:
        logger.exception("匹配报告生成失败：大模型调用异常，match_id=%s", match_id)
        return {
            "compatibility": _MATCH_REPORT_FALLBACK_SCORE,
            "summary": _GENERIC_SUMMARY,
            "analysis": _GENERIC_ANALYSIS,
            "dimensions": dict(_GENERIC_DIMENSIONS),
            "common_points": list(_GENERIC_COMMON_POINTS),
            "differences": list(_GENERIC_DIFFERENCES),
            "suggestions": list(_GENERIC_SUGGESTIONS),
            "risks": list(_GENERIC_RISKS),
        }
    return _match_report_payload_from_raw(raw_report)


async def refresh_match_report(db: Session, match: Match, *, persist: bool = True) -> dict:
    """重新生成匹配报告；persist=False 只返回结果不落库，供脚本 dry-run 使用。"""
    preserved_reason = _preserved_match_reason(match)
    portrait_a, portrait_b = _match_portraits(db, match)
    report_data = await _generate_match_report_data(match.id, portrait_a, portrait_b)
    normalized_report = _normalize_match_report(report_data)
    if not persist:
        return normalized_report

    stored = dict(normalized_report)
    if preserved_reason:
        stored["reason"] = preserved_reason
    match.match_report = _encode(stored, "{}")
    db.commit()
    return normalized_report


async def get_match_report(db: Session, user_id: str, match_id: str) -> dict:
    """获取或生成匹配报告"""
    match = _representative_match_for_pair(db, _get_match_for_user(db, match_id, user_id))
    cached = _cached_match_report(match)
    if cached is not None:
        return cached
    return await refresh_match_report(db, match)


def respond_match_request(db: Session, user_id: str, request_id: str, accept: bool) -> None:
    """接受或拒绝匹配申请"""
    match = db.query(Match).filter(Match.id == request_id, Match.target_id == user_id).first()
    if not match:
        raise ApiException(code=NOT_FOUND, message="匹配请求不存在", status_code=404)

    match.status = "accepted" if accept else "rejected"
    db.commit()


def apply_buddy(db: Session, user_id: str, target_user_id: str, reason: str = "") -> Match:
    """发起短期搭子申请"""
    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    match = Match(
        id=_uuid(),
        user_id=user_id,
        target_id=target_user_id,
        common_tags=_encode([], "[]"),
        status="pending",
        match_type="buddy",
        match_report=reason,
        created_at=_now_ms(),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


def respond_buddy(db: Session, user_id: str, request_id: str, accept: bool) -> None:
    """同意或拒绝搭子申请（仅接收方 target_id 可操作，与 POST /social/buddy 发起方向一致）"""
    match = db.query(Match).filter(
        Match.id == request_id,
        Match.match_type == "buddy",
    ).first()
    if not match:
        raise ApiException(
            code=NOT_FOUND,
            message="搭子申请不存在：请确认路径里的 id 是「分身 start-chat」或「申请搭子」接口返回的 social 匹配 id，而不是分身推荐 AvatarMatch 的 id",
            status_code=404,
        )
    if match.target_id != user_id:
        if match.user_id == user_id:
            raise ApiException(
                code=PARAM_INVALID,
                message="你是该搭子申请的发起方，不能给自己执行同意/拒绝；请让对方（接收方）登录后调用本接口",
                status_code=400,
            )
        raise ApiException(
            code=NOT_FOUND,
            message="搭子申请不存在或当前登录用户不是该申请的接收方；请用接收方账号（密码见种子数据说明）登录后再试",
            status_code=404,
        )

    if match.status != "pending":
        raise ApiException(code=PARAM_INVALID, message="该搭子申请已处理，无需再次响应", status_code=400)

    match.status = "accepted" if accept else "rejected"

    # 同步关联的 AtoaInteraction.outcome（Phase 8C 社交闭环）
    try:
        from app.models.avatar import AvatarAtoaInteraction
        interaction = (
            db.query(AvatarAtoaInteraction)
            .filter(AvatarAtoaInteraction.triggered_match_id == match.id)
            .first()
        )
        if interaction and interaction.outcome == "connected":
            import time as _time
            interaction.outcome = "connect_confirmed" if accept else "connect_rejected"
            interaction.updated_at = int(_time.time() * 1000)
    except Exception:
        pass  # 不影响主流程

    db.commit()


def _activity_participant(user: Optional[User], *, organizer_id: str) -> dict:
    if not user:
        return {
            "id": "",
            "name": "用户",
            "avatar": "",
            "school": "",
            "is_organizer": False,
        }
    return {
        "id": user.id,
        "name": user.name or user.username,
        "avatar": user.avatar or "",
        "school": user.school or "",
        "is_organizer": user.id == organizer_id,
    }


def get_activity_room(db: Session, user_id: str, match_id: str) -> dict:
    """返回已由双方确认的短期任务房间。"""
    from app.models.social import SocialMission

    match = _get_match_for_user(db, match_id, user_id)
    if match.status != "accepted":
        raise ApiException(code=PARAM_ERROR, message="双方确认后才能进入活动房间", status_code=400)
    if not match.mission_id:
        raise ApiException(code=NOT_FOUND, message="该关系未关联活动任务", status_code=404)

    mission = db.query(SocialMission).filter(SocialMission.id == match.mission_id).first()
    if not mission or mission.mode != "short_term":
        raise ApiException(code=NOT_FOUND, message="活动任务不存在", status_code=404)

    organizer_id = mission.user_id
    user_a = db.query(User).filter(User.id == match.user_id).first()
    user_b = db.query(User).filter(User.id == match.target_id).first()
    status = "completed" if mission.status == "completed" else "active"
    return {
        "match_id": match.id,
        "mission_id": mission.id,
        "title": mission.title,
        "status": status,
        "time_window": _decode(mission.time_window, {}),
        "location": _decode(mission.location, {}),
        "budget": _decode(mission.budget, {}),
        "linked_post_id": mission.linked_post_id,
        "participants": [
            _activity_participant(user_a, organizer_id=organizer_id),
            _activity_participant(user_b, organizer_id=organizer_id),
        ],
        "created_at": match.created_at,
        "completed_at": mission.updated_at if status == "completed" else None,
    }


def complete_activity_room(db: Session, user_id: str, match_id: str) -> dict:
    """由任一参与者确认活动结束，并停止任务继续推荐。"""
    from app.models.social import SocialMission

    match = _get_match_for_user(db, match_id, user_id)
    if match.status != "accepted" or not match.mission_id:
        raise ApiException(code=PARAM_ERROR, message="当前活动不能标记为完成", status_code=400)
    mission = db.query(SocialMission).filter(SocialMission.id == match.mission_id).first()
    if not mission or mission.mode != "short_term":
        raise ApiException(code=NOT_FOUND, message="活动任务不存在", status_code=404)

    mission.status = "completed"
    mission.updated_at = _now_ms()
    db.commit()
    return get_activity_room(db, user_id, match_id)

"""找人任务服务：意图解析、任务状态、候选召回和任务内 AtoA。"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.avatar import AvatarAtoaSession
from app.models.memory import AvatarCard
from app.models.plaza import PlazaPost
from app.models.social import MissionCandidate, SocialMission
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_INVALID


_TZ = ZoneInfo("Asia/Shanghai")
_MISSION_MODES = {"short_term", "long_term"}
_MISSION_STATUSES = {
    "draft",
    "searching",
    "posting",
    "probing",
    "awaiting_user",
    "awaiting_peer",
    "connected",
    "completed",
    "paused",
    "expired",
    "cancelled",
}
_SEARCH_STRATEGIES = {"search_only", "post_only", "search_then_draft"}
_DEFAULT_PERMISSIONS = {
    "search": True,
    "atoaProbe": True,
    "draftPost": True,
    "draftReply": True,
    "autoPublish": False,
    "autoConnect": False,
}
_SHORT_PURPOSES: list[tuple[str, tuple[str, ...]]] = [
    ("movie", ("电影", "看电影", "影院")),
    ("murder_mystery", ("剧本杀", "跑团")),
    ("meal", ("吃饭", "探店", "火锅", "咖啡")),
    ("sport", ("羽毛球", "骑行", "跑步", "运动", "健身", "篮球", "足球")),
    ("exhibition", ("展览", "看展", "博物馆")),
    ("study", ("自习", "学习", "备考", "雅思", "考研")),
    ("travel", ("旅行", "旅游", "周边游")),
    ("game", ("游戏", "开黑", "桌游")),
]
_LONG_PURPOSES: list[tuple[str, tuple[str, ...]]] = [
    ("roommate", ("合租", "室友", "租房")),
    ("dating", ("恋爱", "对象", "谈恋爱", "伴侣")),
    ("friendship", ("交友", "交朋友", "认识朋友", "长期朋友")),
    ("study_partner", ("长期学习", "固定自习", "长期备考")),
    ("sport_partner", ("长期运动", "固定运动", "长期健身")),
]
_PURPOSE_LABELS = {
    "movie": "看电影",
    "murder_mystery": "剧本杀",
    "meal": "吃饭或探店",
    "sport": "运动",
    "exhibition": "看展",
    "study": "学习或自习",
    "travel": "旅行",
    "game": "一起玩游戏",
    "activity": "一起做件事",
    "roommate": "找合租室友",
    "dating": "认真认识恋爱对象",
    "friendship": "认识长期朋友",
    "study_partner": "找长期学习伙伴",
    "sport_partner": "找长期运动伙伴",
    "long_term": "慢慢认识一个人",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _decode(value: Optional[str], default: Any) -> Any:
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _clean_list(values: Optional[list[Any]], limit: int = 12) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text[:80])
        if len(result) >= limit:
            break
    return result


def _public_user(user: Optional[User]) -> Optional[dict]:
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.name or user.username,
        "avatar": user.avatar or "",
        "school": user.school or "",
        "major": user.major or "",
        "grade": user.grade or "",
    }


def _public_post(post: Optional[PlazaPost], author: Optional[User]) -> Optional[dict]:
    if not post:
        return None
    return {
        "id": post.id,
        "authorId": post.user_id,
        "authorName": (author.name or author.username) if author else "",
        "authorAvatar": (author.avatar or "") if author else "",
        "authorSchool": (author.school or "") if author else "",
        "type": post.type,
        "content": post.content or "",
        "location": post.location or "",
        "tags": _decode(post.tags, []),
        "createdAt": post.created_at,
        "allowAgentReply": bool(post.allow_agent_reply),
        "schoolOnly": bool(post.school_only),
        "missionId": post.mission_id,
        "opportunityMode": post.opportunity_mode,
        "category": post.category,
        "startAt": post.start_at,
        "endAt": post.end_at,
        "applyDeadline": post.apply_deadline,
        "slotsTotal": post.slots_total,
        "slotsRemaining": post.slots_remaining,
        "allowWaitlist": bool(post.allow_waitlist),
        "budget": _decode(post.budget, {}),
        "requirements": _decode(post.requirements, []),
        "opportunityStatus": post.opportunity_status or "open",
    }


def _mission_to_dict(mission: SocialMission) -> dict:
    return {
        "id": mission.id,
        "mode": mission.mode,
        "purpose_type": mission.purpose_type,
        "title": mission.title,
        "description": mission.description or "",
        "source": mission.source or "guided_form",
        "status": mission.status or "draft",
        "time_window": _decode(mission.time_window, {}),
        "location": _decode(mission.location, {}),
        "headcount": _decode(mission.headcount, {}),
        "budget": _decode(mission.budget, {}),
        "must_haves": _decode(mission.must_haves, []),
        "preferences": _decode(mission.preferences, []),
        "boundaries": _decode(mission.boundaries, []),
        "public_memory_ids": _decode(mission.public_memory_ids, []),
        "public_card_snapshot": _decode(mission.public_card_snapshot, {}),
        "permissions": {**_DEFAULT_PERMISSIONS, **_decode(mission.permissions, {})},
        "search_strategy": mission.search_strategy or "search_then_draft",
        "linked_post_id": mission.linked_post_id,
        "atoa_session_id": mission.atoa_session_id,
        "candidate_count": mission.candidate_count or 0,
        "pending_count": mission.pending_count or 0,
        "expires_at": mission.expires_at,
        "created_at": mission.created_at,
        "updated_at": mission.updated_at,
    }


def _candidate_to_dict(db: Session, candidate: MissionCandidate) -> dict:
    target_user = (
        db.query(User).filter(User.id == candidate.target_user_id).first()
        if candidate.target_user_id
        else None
    )
    post = (
        db.query(PlazaPost).filter(PlazaPost.id == candidate.target_post_id).first()
        if candidate.target_post_id
        else None
    )
    if post and not target_user:
        target_user = db.query(User).filter(User.id == post.user_id).first()
    return {
        "id": candidate.id,
        "mission_id": candidate.mission_id,
        "target_user_id": candidate.target_user_id,
        "target_post_id": candidate.target_post_id,
        "source": candidate.source,
        "status": candidate.status or "discovered",
        "hard_constraint_result": _decode(candidate.hard_constraint_result, {}),
        "fit_reasons": _decode(candidate.fit_reasons, []),
        "questions": _decode(candidate.questions, []),
        "conflicts": _decode(candidate.conflicts, []),
        "risk_flags": _decode(candidate.risk_flags, []),
        "internal_score": candidate.internal_score or 0,
        "interaction_id": candidate.interaction_id,
        "target_user": _public_user(target_user),
        "target_post": _public_post(post, target_user),
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def _detect_purpose(text: str) -> tuple[str, str]:
    normalized = text.lower()
    for purpose, keywords in _LONG_PURPOSES:
        if any(keyword in normalized for keyword in keywords):
            return "long_term", purpose
    for purpose, keywords in _SHORT_PURPOSES:
        if any(keyword in normalized for keyword in keywords):
            return "short_term", purpose
    if any(keyword in normalized for keyword in ("长期", "固定", "慢慢认识")):
        return "long_term", "long_term"
    return "short_term", "activity"


def _next_weekend_window(now: datetime) -> tuple[datetime, datetime]:
    days_until_saturday = (5 - now.weekday()) % 7
    if days_until_saturday == 0 and now.hour >= 22:
        days_until_saturday = 7
    start = (now + timedelta(days=days_until_saturday)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    end = (start + timedelta(days=1)).replace(hour=23, minute=59)
    return start, end


def _parse_time_window(text: str) -> tuple[dict, bool]:
    now = datetime.now(_TZ)
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    label = ""
    inferred = False
    if "周末" in text:
        start, end = _next_weekend_window(now)
        label = "本周末"
        inferred = True
    elif "明天" in text:
        start = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59)
        label = "明天"
        inferred = True
    elif "今天" in text or "今晚" in text:
        start = now
        end = now.replace(hour=23, minute=59, second=0, microsecond=0)
        label = "今天"
        inferred = True
    else:
        date_match = re.search(r"(\d{1,2})月(\d{1,2})[日号]", text)
        if date_match:
            month, day = int(date_match.group(1)), int(date_match.group(2))
            year = now.year + (1 if (month, day) < (now.month, now.day) else 0)
            try:
                start = datetime(year, month, day, 9, tzinfo=_TZ)
                end = start.replace(hour=23, minute=59)
                label = f"{month}月{day}日"
                inferred = True
            except ValueError:
                start = None

    hour_match = re.search(r"(?<!\d)(\d{1,2})(?:[:：](\d{2})|点(?:半)?)", text)
    if start and hour_match:
        hour = min(int(hour_match.group(1)), 23)
        minute = 30 if "点半" in hour_match.group(0) else int(hour_match.group(2) or 0)
        start = start.replace(hour=hour, minute=minute)
        end = start + timedelta(hours=3)
        label = f"{label} {hour:02d}:{minute:02d}".strip()

    if not start or not end:
        return {"label": "时间可商量", "flexibilityMinutes": 120}, False
    return {
        "label": label,
        "startAt": int(start.timestamp() * 1000),
        "endAt": int(end.timestamp() * 1000),
        "flexibilityMinutes": 120,
    }, inferred


def _parse_headcount(text: str) -> dict:
    match = re.search(r"(?:还差|找|需要|要)\s*([一二两三四五六七八九十\d]+)\s*个?人", text)
    chinese = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    wanted = 1
    if match:
        raw = match.group(1)
        wanted = int(raw) if raw.isdigit() else chinese.get(raw, 1)
    return {"current": 1, "wanted": max(1, min(wanted, 20)), "allowWaitlist": True}


def _parse_budget(text: str) -> dict:
    if "免费" in text:
        return {"type": "free"}
    range_match = re.search(r"(\d{1,4})\s*(?:到|至|-)\s*(\d{1,4})\s*元?", text)
    if range_match:
        return {
            "type": "range",
            "min": int(range_match.group(1)),
            "max": int(range_match.group(2)),
        }
    amount_match = re.search(r"(?:人均|预算|大概)\s*(\d{1,4})\s*元", text)
    if amount_match:
        amount = int(amount_match.group(1))
        return {"type": "range", "min": max(0, amount - 20), "max": amount + 20}
    return {"type": "aa"}


def parse_mission_text(text: str, current_user: User) -> dict:
    clean = str(text or "").strip()
    if not clean:
        raise ApiException(code=PARAM_INVALID, message="请先告诉分身你想找什么样的人")

    mode, purpose_type = _detect_purpose(clean)
    time_window, has_time = _parse_time_window(clean)
    purpose_label = _PURPOSE_LABELS.get(purpose_type, "找朋友")
    location = {
        "label": current_user.school or "位置待确认",
        "radiusKm": 5,
        "precision": "campus" if current_user.school else "district",
    }
    preferences: list[str] = []
    for keyword in (
        "新手友好",
        "不玩重恐",
        "科幻",
        "周末",
        "同校",
        "慢热",
        "小群体",
        "作息相近",
        "先线上聊",
    ):
        if keyword in clean:
            preferences.append(keyword)

    title = purpose_label if mode == "long_term" else f"{time_window.get('label', '')}{purpose_label}".strip()
    questions: list[str] = []
    inferred_fields = ["mode", "purposeType", "title", "headcount", "budget"]
    if has_time:
        inferred_fields.append("timeWindow")
    elif mode == "short_term":
        questions.append("你希望什么时候进行？")
    if not current_user.school:
        questions.append("希望在哪个区域寻找？")
    has_movie_preference = bool(
        re.search(r"《[^》]+》", clean)
        or any(
            keyword in clean
            for keyword in (
                "科幻",
                "喜剧",
                "爱情",
                "动画",
                "悬疑",
                "动作",
                "纪录片",
                "电影可以商量",
                "片子可以商量",
            )
        )
    )
    if purpose_type == "movie" and not has_movie_preference:
        questions.append("想看哪部电影，还是影片可以商量？")
    if purpose_type == "murder_mystery" and not any(
        keyword in clean for keyword in ("欢乐", "推理", "情感", "恐怖", "新手")
    ):
        questions.append("偏好哪种剧本类型？")

    expires_at = None
    if mode == "short_term":
        expires_at = time_window.get("endAt") or (_now_ms() + 7 * 24 * 60 * 60 * 1000)
    else:
        expires_at = _now_ms() + 30 * 24 * 60 * 60 * 1000

    return {
        "draft": {
            "mode": mode,
            "purposeType": purpose_type,
            "title": title or "找朋友",
            "description": clean,
            "source": "natural_language",
            "timeWindow": time_window,
            "location": location,
            "headcount": _parse_headcount(clean),
            "budget": _parse_budget(clean),
            "mustHaves": [],
            "preferences": preferences,
            "boundaries": [],
            "publicMemoryIds": [],
            "permissions": dict(_DEFAULT_PERMISSIONS),
            "searchStrategy": "search_then_draft",
            "expiresAt": expires_at,
        },
        "inferred_fields": inferred_fields,
        "questions": questions[:3],
    }


def _build_public_snapshot(db: Session, current_user: User, data: dict) -> dict:
    card = db.query(AvatarCard).filter(AvatarCard.user_id == current_user.id).first()
    return {
        "displayName": (
            card.display_name if card and card.display_name else (current_user.name or current_user.username)
        ),
        "publicSummary": data.get("description", "")[:240],
        "school": current_user.school or "",
        "interestTags": _clean_list(
            data.get("preferences", [])
            + ([data.get("purpose_type")] if data.get("purpose_type") else [])
        ),
        "socialIntent": [data.get("purpose_type")],
        "conversationStyle": (
            _decode(card.conversation_style, {}) if card else {"tone": "自然、友善、低压力"}
        ),
        "boundaries": _clean_list(data.get("boundaries", []), 8),
    }


def create_mission(db: Session, current_user: User, data: dict) -> dict:
    mode = str(data.get("mode") or "")
    if mode not in _MISSION_MODES:
        raise ApiException(code=PARAM_INVALID, message="找人模式只能是短期或长期")
    strategy = str(data.get("search_strategy") or "search_then_draft")
    if strategy not in _SEARCH_STRATEGIES:
        raise ApiException(code=PARAM_INVALID, message="搜索策略不受支持")
    permissions = {**_DEFAULT_PERMISSIONS, **(data.get("permissions") or {})}
    permissions["autoPublish"] = False
    permissions["autoConnect"] = False
    now = _now_ms()
    mission = SocialMission(
        id=str(uuid4()),
        user_id=current_user.id,
        mode=mode,
        purpose_type=str(data.get("purpose_type") or ("activity" if mode == "short_term" else "long_term")),
        title=str(data.get("title") or "").strip()[:80],
        description=str(data.get("description") or "").strip()[:1000],
        source=str(data.get("source") or "guided_form"),
        status="draft",
        time_window=_encode(data.get("time_window") or {}),
        location=_encode(data.get("location") or {}),
        headcount=_encode(data.get("headcount") or {}),
        budget=_encode(data.get("budget") or {}),
        must_haves=_encode(_clean_list(data.get("must_haves"))),
        preferences=_encode(_clean_list(data.get("preferences"))),
        boundaries=_encode(_clean_list(data.get("boundaries"), 8)),
        public_memory_ids=_encode(_clean_list(data.get("public_memory_ids"), 20)),
        public_card_snapshot=_encode(_build_public_snapshot(db, current_user, data)),
        permissions=_encode(permissions),
        search_strategy=strategy,
        candidate_count=0,
        pending_count=0,
        expires_at=data.get("expires_at"),
        created_at=now,
        updated_at=now,
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return _mission_to_dict(mission)


def _get_mission(db: Session, user_id: str, mission_id: str) -> SocialMission:
    mission = db.query(SocialMission).filter(
        SocialMission.id == mission_id,
        SocialMission.user_id == user_id,
    ).first()
    if not mission:
        raise ApiException(code=NOT_FOUND, message="找人任务不存在", status_code=404)
    return mission


def list_missions(db: Session, user_id: str, status: Optional[str] = None) -> list[dict]:
    query = db.query(SocialMission).filter(SocialMission.user_id == user_id)
    if status:
        query = query.filter(SocialMission.status == status)
    missions = query.order_by(SocialMission.updated_at.desc()).limit(100).all()
    now = _now_ms()
    changed = False
    for mission in missions:
        if (
            mission.expires_at
            and mission.expires_at <= now
            and mission.status not in {"completed", "cancelled", "connected", "expired"}
        ):
            mission.status = "expired"
            mission.updated_at = now
            changed = True
    if changed:
        db.commit()
    return [_mission_to_dict(mission) for mission in missions]


def get_mission(db: Session, user_id: str, mission_id: str) -> dict:
    return _mission_to_dict(_get_mission(db, user_id, mission_id))


def update_mission(db: Session, current_user: User, mission_id: str, data: dict) -> dict:
    mission = _get_mission(db, current_user.id, mission_id)
    if mission.status in {"completed", "cancelled"}:
        raise ApiException(code=PARAM_INVALID, message="已结束任务不能再修改")
    scalar_fields = {"purpose_type", "title", "description", "search_strategy", "expires_at"}
    json_fields = {
        "time_window",
        "location",
        "headcount",
        "budget",
        "must_haves",
        "preferences",
        "boundaries",
        "public_memory_ids",
        "permissions",
    }
    for key, value in data.items():
        if value is None:
            continue
        if key in scalar_fields:
            setattr(mission, key, value)
        elif key in json_fields:
            if key == "permissions":
                value = {**_DEFAULT_PERMISSIONS, **value, "autoPublish": False, "autoConnect": False}
            setattr(mission, key, _encode(value))
    snapshot_data = {
        "purpose_type": mission.purpose_type,
        "description": mission.description,
        "preferences": _decode(mission.preferences, []),
        "boundaries": _decode(mission.boundaries, []),
    }
    mission.public_card_snapshot = _encode(_build_public_snapshot(db, current_user, snapshot_data))
    mission.updated_at = _now_ms()
    db.commit()
    db.refresh(mission)
    return _mission_to_dict(mission)


def set_mission_status(
    db: Session,
    user_id: str,
    mission_id: str,
    action: str,
) -> dict:
    mission = _get_mission(db, user_id, mission_id)
    transitions = {
        "pause": ({"searching", "posting", "probing", "awaiting_user", "awaiting_peer"}, "paused"),
        "resume": ({"paused"}, "searching"),
        "close": (_MISSION_STATUSES - {"completed", "cancelled"}, "cancelled"),
    }
    if action not in transitions:
        raise ApiException(code=PARAM_INVALID, message="任务操作不受支持")
    allowed, next_status = transitions[action]
    if mission.status not in allowed:
        raise ApiException(code=PARAM_INVALID, message=f"当前状态不能执行{action}")
    mission.status = next_status
    mission.updated_at = _now_ms()
    db.commit()
    return _mission_to_dict(mission)


def delete_mission(db: Session, user_id: str, mission_id: str) -> None:
    mission = _get_mission(db, user_id, mission_id)
    candidates = db.query(MissionCandidate).filter(MissionCandidate.mission_id == mission.id).all()
    for candidate in candidates:
        db.delete(candidate)
    db.delete(mission)
    db.commit()


def _mission_terms(mission: SocialMission) -> set[str]:
    values = [
        mission.title,
        mission.description,
        _PURPOSE_LABELS.get(mission.purpose_type, mission.purpose_type),
        *_decode(mission.preferences, []),
        *_decode(mission.must_haves, []),
    ]
    terms: set[str] = set()
    known = {
        keyword
        for _, keywords in (_SHORT_PURPOSES + _LONG_PURPOSES)
        for keyword in keywords
    }
    for value in values:
        text = str(value or "").lower()
        terms.update(keyword for keyword in known if keyword in text)
        terms.update(
            token for token in re.split(r"[\s,，。；;、#]+", text) if 2 <= len(token) <= 12
        )
    terms.add(mission.purpose_type.lower())
    return {term for term in terms if term}


def _upsert_candidate(
    db: Session,
    mission: SocialMission,
    *,
    target_user_id: Optional[str],
    target_post_id: Optional[str],
    source: str,
    score: int,
    hard: dict[str, str],
    reasons: list[dict],
    questions: list[str],
    conflicts: Optional[list[dict]] = None,
) -> MissionCandidate:
    query = db.query(MissionCandidate).filter(MissionCandidate.mission_id == mission.id)
    if target_post_id:
        query = query.filter(MissionCandidate.target_post_id == target_post_id)
    else:
        query = query.filter(
            MissionCandidate.target_user_id == target_user_id,
            MissionCandidate.target_post_id == None,  # noqa: E711
        )
    candidate = query.first()
    now = _now_ms()
    if not candidate:
        candidate = MissionCandidate(
            id=str(uuid4()),
            mission_id=mission.id,
            target_user_id=target_user_id,
            target_post_id=target_post_id,
            source=source,
            status="discovered",
            created_at=now,
            updated_at=now,
        )
        db.add(candidate)
    elif candidate.status in {"expired", "discovered", "ready_for_user"}:
        candidate.status = "discovered"
    candidate.internal_score = max(0, min(int(score), 99))
    candidate.hard_constraint_result = _encode(hard)
    candidate.fit_reasons = _encode(reasons)
    candidate.questions = _encode(questions)
    candidate.conflicts = _encode(conflicts or [])
    candidate.risk_flags = _encode([])
    candidate.updated_at = now
    return candidate


def _search_short_term(db: Session, current_user: User, mission: SocialMission) -> tuple[int, list[MissionCandidate]]:
    terms = _mission_terms(mission)
    location = _decode(mission.location, {})
    location_label = str(location.get("label") or "").lower()
    rows = (
        db.query(PlazaPost, User)
        .join(User, PlazaPost.user_id == User.id)
        .filter(
            PlazaPost.user_id != current_user.id,
            PlazaPost.type.in_(["buddy", "dating"]),
        )
        .order_by(PlazaPost.created_at.desc())
        .limit(100)
        .all()
    )
    matched: list[MissionCandidate] = []
    for post, author in rows:
        if post.school_only and (author.school or "") != (current_user.school or ""):
            continue
        if post.opportunity_status in {"full", "completed", "expired", "cancelled"}:
            continue
        if post.apply_deadline and post.apply_deadline <= _now_ms():
            continue
        post_text = f"{post.content} {post.location} {' '.join(_decode(post.tags, []))}".lower()
        overlaps = sorted(term for term in terms if term and term in post_text)
        purpose_keywords = dict(_SHORT_PURPOSES).get(mission.purpose_type, ())
        purpose_hit = any(keyword in post_text for keyword in purpose_keywords)
        if not purpose_hit and not overlaps:
            continue
        score = 30 + (35 if purpose_hit else 0) + min(20, len(overlaps) * 5)
        reasons: list[dict] = []
        if purpose_hit:
            reasons.append({
                "text": f"活动内容与“{_PURPOSE_LABELS.get(mission.purpose_type, mission.title)}”一致",
                "source": "public_post",
                "confidence": "confirmed",
            })
        if overlaps:
            reasons.append({
                "text": f"公开帖子包含共同条件：{'、'.join(overlaps[:3])}",
                "source": "public_post",
                "confidence": "confirmed",
            })
        same_school = bool(current_user.school and author.school == current_user.school)
        if same_school:
            score += 10
            reasons.append({
                "text": "发布者与你同校",
                "source": "public_profile",
                "confidence": "confirmed",
            })
        location_hit = bool(
            location_label
            and (
                location_label in (post.location or "").lower()
                or location_label in (author.school or "").lower()
            )
        )
        if location_hit:
            score += 10
        mission_window = _decode(mission.time_window, {})
        time_result = "unknown"
        mission_start = mission_window.get("startAt")
        mission_end = mission_window.get("endAt")
        if post.start_at and mission_start:
            post_end = post.end_at or post.start_at
            desired_end = mission_end or mission_start
            time_result = "pass" if post.start_at <= desired_end and post_end >= mission_start else "fail"
            if time_result == "fail":
                continue
            score += 15
        availability = "unknown"
        if post.slots_remaining is not None:
            availability = "pass" if post.slots_remaining > 0 else "fail"
            if availability == "fail":
                continue
            score += 10
        hard = {
            "activity": "pass" if purpose_hit else "unknown",
            "time": time_result,
            "location": "pass" if location_hit or same_school else "unknown",
            "availability": availability,
        }
        questions = []
        if time_result == "unknown":
            questions.append("具体时间是否仍可协调？")
        if availability == "unknown":
            questions.append("目前是否还有名额？")
        if not questions:
            questions.append("参加者是否欢迎第一次见面的新朋友？")
        matched.append(_upsert_candidate(
            db,
            mission,
            target_user_id=author.id,
            target_post_id=post.id,
            source="plaza_post",
            score=score,
            hard=hard,
            reasons=reasons,
            questions=questions,
        ))
    return len(rows), matched


def _search_long_term(db: Session, current_user: User, mission: SocialMission) -> tuple[int, list[MissionCandidate]]:
    my_snapshot = _decode(mission.public_card_snapshot, {})
    my_tags = {str(value).lower() for value in my_snapshot.get("interestTags", [])}
    rows = (
        db.query(AvatarCard, User)
        .join(User, AvatarCard.user_id == User.id)
        .filter(
            AvatarCard.user_id != current_user.id,
            AvatarCard.visibility != "private",
        )
        .limit(100)
        .all()
    )
    matched: list[MissionCandidate] = []
    for card, user in rows:
        tags = {str(value).lower() for value in _decode(card.interest_tags, [])}
        intents = {str(value).lower() for value in _decode(card.social_intent, [])}
        shared = sorted(my_tags & tags)
        intent_text = " ".join(intents)
        intent_hit = mission.purpose_type.lower() in intents or any(
            keyword in intent_text
            for keyword in dict(_LONG_PURPOSES).get(mission.purpose_type, ())
        )
        if not shared and not intent_hit:
            continue
        score = 35 + (30 if intent_hit else 0) + min(20, len(shared) * 6)
        reasons: list[dict] = []
        if intent_hit:
            reasons.append({
                "text": "双方公开的关系目的相容",
                "source": "public_card",
                "confidence": "confirmed",
            })
        if shared:
            reasons.append({
                "text": f"公开兴趣有交集：{'、'.join(shared[:3])}",
                "source": "public_card",
                "confidence": "confirmed",
            })
        if current_user.school and user.school == current_user.school:
            score += 10
            reasons.append({
                "text": "双方在同一所学校",
                "source": "public_profile",
                "confidence": "confirmed",
            })
        matched.append(_upsert_candidate(
            db,
            mission,
            target_user_id=user.id,
            target_post_id=None,
            source="public_card",
            score=score,
            hard={
                "intent": "pass" if intent_hit else "unknown",
                "boundaries": "unknown",
                "location": "pass" if current_user.school == user.school else "unknown",
            },
            reasons=reasons,
            questions=["双方期待的联系频率是否接近？", "更希望先线上聊还是参加共同活动？"],
        ))
    return len(rows), matched


def list_candidates(
    db: Session,
    user_id: str,
    mission_id: str,
    status: Optional[str] = None,
) -> list[dict]:
    _get_mission(db, user_id, mission_id)
    query = db.query(MissionCandidate).filter(MissionCandidate.mission_id == mission_id)
    if status:
        query = query.filter(MissionCandidate.status == status)
    rows = query.order_by(
        MissionCandidate.internal_score.desc(),
        MissionCandidate.updated_at.desc(),
    ).all()
    return [_candidate_to_dict(db, row) for row in rows]


def search_mission(db: Session, current_user: User, mission_id: str) -> dict:
    mission = _get_mission(db, current_user.id, mission_id)
    if mission.status in {"cancelled", "completed", "expired"}:
        raise ApiException(code=PARAM_INVALID, message="任务已结束，不能继续搜索")
    permissions = {**_DEFAULT_PERMISSIONS, **_decode(mission.permissions, {})}
    if not permissions.get("search"):
        raise ApiException(code=PARAM_INVALID, message="请先允许分身搜索公开帖子和名片")
    mission.status = "searching"
    mission.updated_at = _now_ms()
    stale_candidates = db.query(MissionCandidate).filter(
        MissionCandidate.mission_id == mission.id,
        MissionCandidate.status.in_(["discovered", "ready_for_user"]),
    ).all()
    for candidate in stale_candidates:
        candidate.status = "expired"
        candidate.updated_at = mission.updated_at
    if mission.mode == "short_term":
        scanned, matched = _search_short_term(db, current_user, mission)
    else:
        scanned, matched = _search_long_term(db, current_user, mission)
    active_candidates = (
        db.query(MissionCandidate)
        .filter(
            MissionCandidate.mission_id == mission.id,
            MissionCandidate.status.notin_(["user_skipped", "blocked", "expired"]),
        )
        .all()
    )
    mission.candidate_count = len(active_candidates)
    mission.pending_count = sum(
        candidate.status in {"discovered", "ready_for_user"} for candidate in active_candidates
    )
    if mission.pending_count:
        mission.status = "awaiting_user"
    mission.updated_at = _now_ms()
    db.commit()
    candidates = list_candidates(db, current_user.id, mission.id)
    if candidates:
        suggestion = f"找到了 {len(candidates)} 个值得查看的候选，先看硬条件和待确认问题。"
    elif mission.search_strategy in {"search_then_draft", "post_only"}:
        suggestion = "当前没有同时满足条件的候选，可以让分身生成一条招募帖草稿。"
    else:
        suggestion = "当前没有同时满足条件的候选，可以调整时间、地点或非必要条件。"
    return {
        "mission": _mission_to_dict(mission),
        "candidates": candidates,
        "scanned_count": scanned,
        "matched_count": len(matched),
        "suggestion": suggestion,
    }


def start_mission(db: Session, current_user: User, mission_id: str) -> dict:
    mission = _get_mission(db, current_user.id, mission_id)
    if mission.status != "draft":
        raise ApiException(code=PARAM_INVALID, message="只有草稿任务可以开始寻找")
    if mission.expires_at and mission.expires_at <= _now_ms():
        raise ApiException(code=PARAM_INVALID, message="任务时间已经过期，请先修改时间")
    return search_mission(db, current_user, mission_id)


def _mission_scoped_card(mission: SocialMission, user: User) -> AvatarCard:
    snapshot = _decode(mission.public_card_snapshot, {})
    return AvatarCard(
        id=f"mission-card-{mission.id}",
        user_id=user.id,
        display_name=snapshot.get("displayName") or user.name or user.username,
        public_summary=snapshot.get("publicSummary") or mission.description,
        interest_tags=_encode(snapshot.get("interestTags") or [mission.purpose_type]),
        social_intent=_encode(snapshot.get("socialIntent") or [mission.purpose_type]),
        conversation_style=_encode(snapshot.get("conversationStyle") or {"tone": "自然、友善、低压力"}),
        boundaries=_encode(snapshot.get("boundaries") or []),
        visibility="mission_only",
        updated_at=mission.updated_at,
    )


def _candidate_card(
    db: Session,
    candidate: MissionCandidate,
    target: User,
) -> AvatarCard:
    card = db.query(AvatarCard).filter(AvatarCard.user_id == target.id).first()
    if card:
        return card
    post = (
        db.query(PlazaPost).filter(PlazaPost.id == candidate.target_post_id).first()
        if candidate.target_post_id
        else None
    )
    tags = _decode(post.tags, []) if post else []
    return AvatarCard(
        id=f"candidate-card-{candidate.id}",
        user_id=target.id,
        display_name=target.name or target.username,
        public_summary=(post.content if post else "") or "对方仅公开了基础资料。",
        interest_tags=_encode(tags or ["认识新朋友"]),
        social_intent=_encode([post.type if post else "buddy"]),
        conversation_style=_encode({"tone": "自然、友善、低压力"}),
        boundaries=_encode([]),
        visibility="mission_only",
        updated_at=candidate.updated_at,
    )


async def probe_candidate(
    db: Session,
    current_user: User,
    mission_id: str,
    candidate_id: str,
) -> dict:
    from app.avatar import service as avatar_service

    mission = _get_mission(db, current_user.id, mission_id)
    candidate = db.query(MissionCandidate).filter(
        MissionCandidate.id == candidate_id,
        MissionCandidate.mission_id == mission.id,
    ).first()
    if not candidate:
        raise ApiException(code=NOT_FOUND, message="任务候选不存在", status_code=404)
    permissions = {**_DEFAULT_PERMISSIONS, **_decode(mission.permissions, {})}
    if not permissions.get("atoaProbe"):
        raise ApiException(code=PARAM_INVALID, message="这项任务没有授权分身试聊")
    target = db.query(User).filter(User.id == candidate.target_user_id).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="候选用户不存在", status_code=404)

    if candidate.interaction_id:
        interaction = db.query(avatar_service.AvatarAtoaInteraction).filter(
            avatar_service.AvatarAtoaInteraction.id == candidate.interaction_id
        ).first()
        if interaction:
            return {
                "candidate": _candidate_to_dict(db, candidate),
                "interaction_id": interaction.id,
                "session_id": interaction.session_id or "",
            }

    session = None
    if mission.atoa_session_id:
        session = db.query(AvatarAtoaSession).filter(
            AvatarAtoaSession.id == mission.atoa_session_id
        ).first()
    now = _now_ms()
    if not session:
        session = AvatarAtoaSession(
            id=str(uuid4()),
            user_id=current_user.id,
            candidate_ids=_encode([candidate.target_user_id]),
            excluded_ids=_encode([]),
            score_snapshot=_encode({candidate.target_user_id: candidate.internal_score or 0}),
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        db.flush()
        mission.atoa_session_id = session.id
    else:
        candidate_ids = _decode(session.candidate_ids, [])
        if candidate.target_user_id not in candidate_ids:
            candidate_ids.append(candidate.target_user_id)
            session.candidate_ids = _encode(candidate_ids)
            session.updated_at = now

    card_a = _mission_scoped_card(mission, current_user)
    card_b = _candidate_card(db, candidate, target)
    conversation = await avatar_service._simulate_atoa_conversation(
        card_a,
        card_b,
        max_rounds=1,
    )
    fit_reasons = _decode(candidate.fit_reasons, [])
    reason_texts = [
        str(item.get("text") or "") for item in fit_reasons if isinstance(item, dict)
    ]
    shared_topics = sorted(
        set(_decode(card_a.interest_tags, [])) & set(_decode(card_b.interest_tags, []))
    )
    interaction = avatar_service._write_atoa_interaction(
        db,
        current_user.id,
        target.id,
        {
            "outcome": "pending_user_decision",
            "score_ab": candidate.internal_score or 0,
            "score_ba": max(0, (candidate.internal_score or 0) - 5),
            "shared_topics": shared_topics or [mission.title],
            "reasons_ab": reason_texts or ["任务条件与对方公开信息有交集"],
            "reasons_ba": [],
            "risk_flags": _decode(candidate.risk_flags, []),
            "conversation": conversation,
            "intent_type": mission.purpose_type,
            "is_mutual": False,
        },
        session_id=session.id,
    )
    db.flush()
    candidate.interaction_id = interaction.id
    candidate.status = "ready_for_user"
    candidate.updated_at = now
    mission.status = "awaiting_user"
    mission.pending_count = (
        db.query(MissionCandidate)
        .filter(
            MissionCandidate.mission_id == mission.id,
            MissionCandidate.status.in_(["discovered", "ready_for_user"]),
        )
        .count()
    )
    mission.updated_at = now
    db.commit()
    db.refresh(candidate)
    return {
        "candidate": _candidate_to_dict(db, candidate),
        "interaction_id": interaction.id,
        "session_id": session.id,
    }


def skip_candidate(
    db: Session,
    user_id: str,
    mission_id: str,
    candidate_id: str,
) -> dict:
    mission = _get_mission(db, user_id, mission_id)
    candidate = db.query(MissionCandidate).filter(
        MissionCandidate.id == candidate_id,
        MissionCandidate.mission_id == mission.id,
    ).first()
    if not candidate:
        raise ApiException(code=NOT_FOUND, message="任务候选不存在", status_code=404)
    candidate.status = "user_skipped"
    candidate.updated_at = _now_ms()
    mission.pending_count = max(0, (mission.pending_count or 0) - 1)
    if mission.pending_count == 0:
        mission.status = "searching"
    mission.updated_at = _now_ms()
    db.commit()
    return _candidate_to_dict(db, candidate)


def build_post_draft(db: Session, user_id: str, mission_id: str) -> dict:
    mission = _get_mission(db, user_id, mission_id)
    if mission.mode != "short_term":
        post_type = "dating"
    else:
        post_type = "buddy"
    time_window = _decode(mission.time_window, {})
    location = _decode(mission.location, {})
    headcount = _decode(mission.headcount, {})
    budget = _decode(mission.budget, {})
    lines = [mission.title, "", mission.description]
    if time_window.get("label"):
        lines.append(f"时间：{time_window['label']}")
    if location.get("label"):
        lines.append(f"地点：{location['label']}附近")
    if headcount.get("wanted"):
        lines.append(f"人数：希望再找 {headcount['wanted']} 人")
    budget_type = budget.get("type")
    if budget_type == "aa":
        lines.append("预算：默认 AA")
    elif budget_type == "free":
        lines.append("预算：免费")
    elif budget_type == "range":
        lines.append(f"预算：人均 {budget.get('min', 0)} 到 {budget.get('max', 0)} 元")
    must_haves = _decode(mission.must_haves, [])
    preferences = _decode(mission.preferences, [])
    if must_haves:
        lines.append(f"希望：{'、'.join(must_haves)}")
    if preferences:
        lines.append(f"氛围：{'、'.join(preferences)}")
    lines.extend(["", "由我的分身协助整理，发布前已由本人确认。"])
    location_label = str(location.get("label") or "")
    tags = _clean_list(
        [_PURPOSE_LABELS.get(mission.purpose_type, mission.purpose_type), *preferences],
        5,
    )
    return {
        "type": post_type,
        "content": "\n".join(line for line in lines if line is not None).strip(),
        "location": location_label,
        "tags": tags,
        "allow_agent_reply": True,
        "school_only": location.get("precision") == "campus",
    }


def publish_mission_post(
    db: Session,
    current_user: User,
    mission_id: str,
    data: dict,
) -> dict:
    from app.plaza.service import _post_to_dict

    mission = _get_mission(db, current_user.id, mission_id)
    permissions = {**_DEFAULT_PERMISSIONS, **_decode(mission.permissions, {})}
    if not permissions.get("draftPost"):
        raise ApiException(code=PARAM_INVALID, message="这项任务没有授权分身协助发帖")
    if mission.linked_post_id:
        existing = db.query(PlazaPost).filter(PlazaPost.id == mission.linked_post_id).first()
        if existing:
            return _post_to_dict(existing, current_user)
    now = _now_ms()
    post = PlazaPost(
        id=str(uuid4()),
        user_id=current_user.id,
        type="buddy" if mission.mode == "short_term" else "dating",
        content=str(data.get("content") or "").strip(),
        images="[]",
        location=str(data.get("location") or ""),
        tags=_encode(_clean_list(data.get("tags"), 8)),
        likes=0,
        comments=0,
        agent_responses=0,
        is_from_agent=True,
        allow_agent_reply=bool(data.get("allow_agent_reply", True)),
        school_only=bool(data.get("school_only", False)),
        mission_id=mission.id,
        opportunity_mode=mission.mode,
        category=mission.purpose_type,
        start_at=_decode(mission.time_window, {}).get("startAt"),
        end_at=_decode(mission.time_window, {}).get("endAt"),
        apply_deadline=(
            min(
                value
                for value in [
                    _decode(mission.time_window, {}).get("startAt"),
                    mission.expires_at,
                ]
                if value
            )
            if any([
                _decode(mission.time_window, {}).get("startAt"),
                mission.expires_at,
            ])
            else None
        ),
        location_precision=_decode(mission.location, {}).get("precision", "district"),
        slots_total=(
            int(_decode(mission.headcount, {}).get("current", 1))
            + int(_decode(mission.headcount, {}).get("wanted", 1))
        ),
        slots_remaining=int(_decode(mission.headcount, {}).get("wanted", 1)),
        allow_waitlist=bool(_decode(mission.headcount, {}).get("allowWaitlist", False)),
        budget=mission.budget or "{}",
        requirements=_encode([
            *_decode(mission.must_haves, []),
            *_decode(mission.boundaries, []),
        ]),
        opportunity_status="open",
        agent_probe_enabled=bool(_decode(mission.permissions, {}).get("atoaProbe", True)),
        created_at=now,
    )
    db.add(post)
    db.flush()
    mission.linked_post_id = post.id
    mission.status = "posting"
    mission.updated_at = now
    db.commit()
    db.refresh(post)
    return _post_to_dict(post, current_user)


def mark_candidate_connection(
    db: Session,
    interaction_id: str,
    social_match_id: str,
) -> None:
    candidate = db.query(MissionCandidate).filter(
        MissionCandidate.interaction_id == interaction_id
    ).first()
    if not candidate:
        return
    candidate.status = "request_sent"
    candidate.updated_at = _now_ms()
    mission = db.query(SocialMission).filter(
        SocialMission.id == candidate.mission_id
    ).first()
    if mission:
        mission.status = "awaiting_peer"
        mission.pending_count = max(0, (mission.pending_count or 0) - 1)
        mission.updated_at = _now_ms()
    from app.models.social import Match

    match = db.query(Match).filter(Match.id == social_match_id).first()
    if match and mission:
        match.mission_id = mission.id


def mark_candidate_blocked(db: Session, interaction_id: str) -> None:
    candidate = db.query(MissionCandidate).filter(
        MissionCandidate.interaction_id == interaction_id
    ).first()
    if not candidate:
        return
    candidate.status = "blocked"
    candidate.updated_at = _now_ms()
    mission = db.query(SocialMission).filter(
        SocialMission.id == candidate.mission_id
    ).first()
    if mission:
        mission.pending_count = max(0, (mission.pending_count or 0) - 1)
        if mission.pending_count == 0:
            mission.status = "searching"
        mission.updated_at = _now_ms()


def sync_connection_response(db: Session, mission_id: str, accepted: bool) -> None:
    mission = db.query(SocialMission).filter(SocialMission.id == mission_id).first()
    if not mission:
        return
    mission.status = "connected" if accepted else "searching"
    mission.updated_at = _now_ms()
    candidates = db.query(MissionCandidate).filter(
        MissionCandidate.mission_id == mission_id,
        MissionCandidate.status == "request_sent",
    ).all()
    for candidate in candidates:
        candidate.status = "peer_accepted" if accepted else "peer_rejected"
        candidate.updated_at = mission.updated_at

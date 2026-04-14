"""
AI 分身模块服务层
实现记忆 CRUD、状态管理、推荐匹配、侧写生成业务逻辑
"""
import json
import time
from typing import List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.avatar import AvatarMemory, AvatarMatch, AvatarProfile, AvatarStatus
from app.models.plaza import PlazaPost
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_INVALID


def _now_ms() -> int:
    return int(time.time() * 1000)


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = []
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _memory_to_dict(m: AvatarMemory) -> dict:
    """AvatarMemory ORM → 响应字典"""
    return {
        "id": m.id,
        "category": m.category or "",
        "content": m.content or "",
        "source": m.source or "manual",
        "source_ref": m.source_ref or None,
        "confidence": m.confidence if m.confidence is not None else 1.0,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "is_active": m.is_active if m.is_active is not None else True,
        "is_pinned": m.is_pinned or False,
        "need_type": m.need_type or None,
        "urgency": m.urgency or None,
        "expiry": m.expiry or None,
        "match_status": m.match_status or None,
        "tags": _decode(m.tags, []),
    }


def _status_to_dict(s: AvatarStatus) -> dict:
    """AvatarStatus ORM → 响应字典"""
    return {
        "is_active": s.is_active if s.is_active is not None else True,
        "browsed_count": s.browsed_count or 0,
        "matched_count": s.matched_count or 0,
        "chatting_count": s.chatting_count or 0,
        "last_active_at": s.last_active_at or 0,
        "enabled_channels": _decode(s.enabled_channels, ["buddy", "help", "share", "dating"]),
        "enabled_actions": _decode(s.enabled_actions, ["browse", "match", "comment"]),
        "match_range": _decode(s.match_range, {"school": "", "distanceKm": 10}),
    }


# ==================== 记忆 CRUD ====================

def list_memories(db: Session, user_id: str, category: Optional[str] = None) -> List[dict]:
    """记忆列表，可按 category 筛选"""
    query = db.query(AvatarMemory).filter(AvatarMemory.user_id == user_id)
    if category:
        query = query.filter(AvatarMemory.category == category)
    memories = query.order_by(AvatarMemory.created_at.desc()).all()
    return [_memory_to_dict(m) for m in memories]


def add_memory(db: Session, user_id: str, data: dict) -> dict:
    """添加记忆"""
    now = _now_ms()
    memory = AvatarMemory(
        id=str(uuid4()),
        user_id=user_id,
        category=data["category"],
        content=data["content"],
        source="manual",
        source_ref="",
        confidence=1.0,
        is_active=True,
        is_pinned=False,
        tags=_encode([]),
        created_at=now,
        updated_at=now,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return _memory_to_dict(memory)


def update_memory(db: Session, user_id: str, memory_id: str, data: dict) -> dict:
    """更新记忆"""
    m = db.query(AvatarMemory).filter(
        AvatarMemory.id == memory_id,
        AvatarMemory.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)

    if "content" in data and data["content"] is not None:
        m.content = data["content"]
    if "is_active" in data and data["is_active"] is not None:
        m.is_active = data["is_active"]
    if "is_pinned" in data and data["is_pinned"] is not None:
        m.is_pinned = data["is_pinned"]
    if "category" in data and data["category"] is not None:
        m.category = data["category"]
    if "tags" in data and data["tags"] is not None:
        m.tags = _encode(data["tags"])

    m.updated_at = _now_ms()
    db.commit()
    db.refresh(m)
    return _memory_to_dict(m)


def delete_memory(db: Session, user_id: str, memory_id: str) -> None:
    """删除记忆"""
    m = db.query(AvatarMemory).filter(
        AvatarMemory.id == memory_id,
        AvatarMemory.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)
    db.delete(m)
    db.commit()


# ==================== 分身状态 ====================

def _get_or_create_status(db: Session, user_id: str) -> AvatarStatus:
    """获取分身状态，首次访问自动创建默认记录"""
    status = db.query(AvatarStatus).filter(AvatarStatus.user_id == user_id).first()
    if not status:
        status = AvatarStatus(
            id=str(uuid4()),
            user_id=user_id,
            is_active=True,
            browsed_count=0,
            matched_count=0,
            chatting_count=0,
            last_active_at=0,
            enabled_channels=_encode(["buddy", "help", "share", "dating"]),
            enabled_actions=_encode(["browse", "match", "comment"]),
            match_range=_encode({"school": "", "distanceKm": 10}),
        )
        db.add(status)
        db.commit()
        db.refresh(status)
    return status


def get_status(db: Session, user_id: str) -> dict:
    """获取分身状态"""
    status = _get_or_create_status(db, user_id)
    return _status_to_dict(status)


def update_status(db: Session, user_id: str, data: dict) -> dict:
    """更新分身状态"""
    status = _get_or_create_status(db, user_id)

    if "is_active" in data and data["is_active"] is not None:
        status.is_active = data["is_active"]
    if "enabled_channels" in data and data["enabled_channels"] is not None:
        status.enabled_channels = _encode(data["enabled_channels"])
    if "enabled_actions" in data and data["enabled_actions"] is not None:
        status.enabled_actions = _encode(data["enabled_actions"])
    if "match_range" in data and data["match_range"] is not None:
        status.match_range = _encode(data["match_range"])

    db.commit()
    db.refresh(status)
    return _status_to_dict(status)


# ==================== 分身推荐 ====================

def _post_to_dict(post: PlazaPost, user: User) -> dict:
    """复用广场帖子序列化（避免循环导入，独立实现）"""
    return {
        "id": post.id,
        "author_id": post.user_id,
        "author_name": user.name or user.username,
        "author_avatar": user.avatar or "",
        "author_school": user.school or "",
        "author_major": user.major or "",
        "author_grade": user.grade or "",
        "type": post.type,
        "content": post.content or "",
        "images": _decode(post.images, []),
        "location": post.location or "",
        "tags": _decode(post.tags, []),
        "likes": post.likes or 0,
        "comments": post.comments or 0,
        "agent_responses": post.agent_responses or 0,
        "created_at": post.created_at,
        "is_from_agent": post.is_from_agent or False,
        "allow_agent_reply": post.allow_agent_reply if post.allow_agent_reply is not None else True,
        "school_only": post.school_only or False,
    }


def list_matches(db: Session, user_id: str) -> List[dict]:
    """分身推荐列表，排除 dismissed，按 match_score DESC"""
    rows = (
        db.query(AvatarMatch, PlazaPost, User)
        .join(PlazaPost, AvatarMatch.post_id == PlazaPost.id)
        .join(User, PlazaPost.user_id == User.id)
        .filter(AvatarMatch.user_id == user_id)
        .filter(AvatarMatch.status != "dismissed")
        .order_by(AvatarMatch.match_score.desc())
        .all()
    )

    result = []
    for match, post, user in rows:
        result.append({
            "id": match.id,
            "post_id": match.post_id,
            "post": _post_to_dict(post, user),
            "match_score": match.match_score or 0,
            "match_reasons": _decode(match.match_reasons, []),
            "agent_conversation": _decode(match.agent_conversation, []),
            "status": match.status or "new",
            "created_at": match.created_at,
        })
    return result


def match_action(db: Session, user_id: str, match_id: str, action: str) -> None:
    """分身匹配操作：dismiss / chat"""
    if action not in ("dismiss", "chat"):
        raise ApiException(code=PARAM_INVALID, message="action 只能是 dismiss 或 chat")

    match = db.query(AvatarMatch).filter(
        AvatarMatch.id == match_id,
        AvatarMatch.user_id == user_id,
    ).first()
    if not match:
        raise ApiException(code=NOT_FOUND, message="匹配记录不存在", status_code=404)

    status_map = {"dismiss": "dismissed", "chat": "chatting"}
    match.status = status_map[action]
    db.commit()


# ==================== 分身侧写 ====================

def _profile_to_dict(p: AvatarProfile) -> dict:
    """AvatarProfile ORM → 响应字典"""
    return {
        "summary": p.summary or "",
        "diary_count": p.diary_count or 0,
        "chat_count": p.chat_count or 0,
        "generated_at": p.generated_at or 0,
    }


def get_profile(db: Session, user_id: str) -> dict:
    """获取分身侧写，不存在返回默认空侧写"""
    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    if not profile:
        return {"summary": "", "diary_count": 0, "chat_count": 0, "generated_at": 0}
    return _profile_to_dict(profile)


async def regenerate_profile(db: Session, user_id: str) -> dict:
    """重新生成分身侧写：读取记忆+日记+聊天 → 调用 AI 生成摘要"""
    from app.models.diary import Diary
    from app.models.chat import ChatMessage
    from app.ai.minimax_client import get_minimax_client

    # 收集用户记忆
    memories = (
        db.query(AvatarMemory)
        .filter(AvatarMemory.user_id == user_id, AvatarMemory.is_active == True)  # noqa: E712
        .order_by(AvatarMemory.created_at.desc())
        .limit(50)
        .all()
    )
    memory_text = "\n".join([
        f"- [{m.category}] {m.content}" for m in memories
    ]) if memories else "暂无记忆"

    # 收集近期日记（最近 10 篇）
    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user_id)
        .order_by(Diary.created_at.desc())
        .limit(10)
        .all()
    )
    diary_count = len(diaries)
    diary_text = "\n".join([
        f"- {d.title or '无标题'}: {(d.content or '')[:100]}" for d in diaries
    ]) if diaries else "暂无日记"

    # 收集近期聊天（最近 30 条）
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.role == "user")
        .order_by(ChatMessage.timestamp.desc())
        .limit(30)
        .all()
    )
    chat_count = len(messages)
    chat_text = "\n".join([
        f"- {msg.content[:80]}" for msg in messages
    ]) if messages else "暂无对话"

    # 调用 AI 生成侧写
    system_prompt = (
        "你是一个用户画像分析师。根据用户的记忆库、日记摘要和聊天记录，"
        "生成一段简洁的人格侧写（150-300字），描述用户的性格特征、兴趣爱好、"
        "社交偏好和生活习惯。语言要自然温暖，像朋友之间的了解。"
    )
    user_prompt = (
        f"【记忆库】\n{memory_text}\n\n"
        f"【近期日记摘要】\n{diary_text}\n\n"
        f"【近期聊天内容】\n{chat_text}\n\n"
        "请基于以上信息生成用户人格侧写："
    )

    client = get_minimax_client()
    summary = await client.chat_completion(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.7,
    )

    # 写入/更新 avatar_profiles 表
    now = _now_ms()
    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    if profile:
        profile.summary = summary
        profile.diary_count = diary_count
        profile.chat_count = chat_count
        profile.generated_at = now
    else:
        profile = AvatarProfile(
            id=str(uuid4()),
            user_id=user_id,
            summary=summary,
            diary_count=diary_count,
            chat_count=chat_count,
            generated_at=now,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)
    return _profile_to_dict(profile)

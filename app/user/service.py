# app/user/service.py
# 用户业务逻辑
import json
import time

from sqlalchemy.orm import Session


def _now_ms() -> int:
    return int(time.time() * 1000)


def _decode(s, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def get_portrait(db: Session, user_id: str) -> dict | None:
    """获取用户 AI 画像（从 user_profiles 取）"""
    from app.models.user_profile import UserProfile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        return None
    return {
        "personality": profile.personality or "",
        "writing_style": profile.writing_style or "",
        "interests": _decode(profile.interests, []),
        "preferences": _decode(profile.preferences, {}),
        "relations": _decode(profile.relations, {}),
        "updated_at": profile.updated_at,
    }


async def refresh_portrait(db: Session, user_id: str) -> dict:
    """调用 AI 分析日记+聊天数据，刷新用户画像"""
    from app.models.diary import Diary
    from app.models.chat import ChatMessage
    from app.models.user_profile import UserProfile
    from app.ai.minimax_client import get_minimax_client

    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user_id)
        .order_by(Diary.created_at.desc())
        .limit(10)
        .all()
    )
    diary_summaries = "\n".join([
        f"[{d.date}] {d.title or ''}: {(d.content or '')[:100]}"
        for d in diaries
    ])

    chats = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.role == "user")
        .order_by(ChatMessage.timestamp.desc())
        .limit(20)
        .all()
    )
    chat_summaries = "\n".join([c.content[:80] for c in chats])

    client = get_minimax_client()
    result = await client.generate_portrait(diary_summaries, chat_summaries)

    now = _now_ms()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id, updated_at=now)
        db.add(profile)

    profile.personality = result.get("personality", "")
    profile.writing_style = result.get("writing_style", "")
    profile.interests = json.dumps(result.get("interests", []), ensure_ascii=False)
    profile.preferences = json.dumps(result.get("preferences", {}), ensure_ascii=False)
    profile.relations = json.dumps(result.get("relations", {}), ensure_ascii=False)
    profile.updated_at = now

    db.commit()
    db.refresh(profile)
    return result

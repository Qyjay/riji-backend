"""业务对象进入统一记忆系统的适配层。"""
import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.memory.service import create_memory_document

logger = logging.getLogger("uvicorn.error")


def _decode(raw: Any, default=None):
    if default is None:
        default = []
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _safe_commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _run_safely(label: str, fn) -> None:
    try:
        fn()
    except Exception as exc:
        logger.warning("[memory] %s failed: %s", label, str(exc))


def ingest_chat_session(db: Session, session) -> None:
    """将一段 AI 对话会话沉淀为私有记忆。"""
    def _do() -> None:
        from app.chat.service import list_session_messages

        messages = list_session_messages(db, session.id)
        if not messages:
            return
        lines = [f"对话时间：{session.date or ''}".strip()]
        for message in messages:
            role = "用户" if message.role == "user" else "AI"
            content = (message.content or "").strip()
            if content:
                lines.append(f"{role}：{content}")
        content = "\n".join(lines)
        create_memory_document(
            db,
            user_id=session.user_id,
            source_type="chat_session",
            source_id=session.id,
            title=session.title or "AI 对话",
            content=content,
            summary=session.summary or "",
            visibility="private",
            memory_scope="self",
            emotion={"label": session.mood or "", "emoji": session.mood_emoji or ""},
            tags=_decode(session.topic_tags, []),
            metadata={"message_count": session.message_count or len(messages)},
            occurred_at=session.start_time,
        )
        _safe_commit(db)

    _run_safely("ingest_chat_session", _do)


def ingest_diary(db: Session, diary) -> None:
    """将日记沉淀为私有记忆。"""
    def _do() -> None:
        content = (diary.content or "").strip()
        if not content:
            return
        create_memory_document(
            db,
            user_id=diary.user_id,
            source_type="diary",
            source_id=diary.id,
            title=diary.title or "日记",
            content=content,
            summary=(content[:180] + "...") if len(content) > 180 else content,
            visibility="private",
            memory_scope="self",
            emotion=_decode(diary.emotion_summary, _decode(diary.emotion, {})),
            tags=_decode(diary.tags, []),
            metadata={"date": diary.date or "", "weather": diary.weather or "", "status": diary.status or ""},
            occurred_at=diary.created_at,
        )
        _safe_commit(db)

    _run_safely("ingest_diary", _do)


def ingest_material(db: Session, material) -> None:
    """将原始素材沉淀为私有记忆。"""
    def _do() -> None:
        content = (material.content or "").strip()
        if not content:
            return
        create_memory_document(
            db,
            user_id=material.user_id,
            source_type="material",
            source_id=material.id,
            title=f"{material.type or '素材'}素材",
            content=content,
            summary=(content[:160] + "...") if len(content) > 160 else content,
            visibility="private",
            memory_scope="self",
            emotion=_decode(material.emotion, {}),
            tags=_decode(material.tags, []),
            metadata={"date": material.date or "", "type": material.type or ""},
            occurred_at=material.created_at,
        )
        _safe_commit(db)

    _run_safely("ingest_material", _do)


def ingest_plaza_post(db: Session, post) -> None:
    """将用户自己发出的广场帖子沉淀为社交记忆。"""
    def _do() -> None:
        content = (post.content or "").strip()
        if not content:
            return
        tags = _decode(post.tags, [])
        shared_visibility = "school" if bool(post.school_only) else "public"
        create_memory_document(
            db,
            user_id=post.user_id,
            source_type="plaza_post",
            source_id=post.id,
            title=f"广场帖子 / {post.type or 'share'}",
            content=content,
            summary=(content[:160] + "...") if len(content) > 160 else content,
            visibility="avatar_only",
            memory_scope="social",
            tags=tags,
            metadata={"type": post.type or "", "school_only": bool(post.school_only)},
            occurred_at=post.created_at,
        )
        # 额外保留一份共享索引，用于广场匹配和 agent-to-agent 检索。
        create_memory_document(
            db,
            user_id=post.user_id,
            source_type="plaza_post_index",
            source_id=post.id,
            title=f"广场公开索引 / {post.type or 'share'}",
            content=content,
            summary=(content[:160] + "...") if len(content) > 160 else content,
            visibility=shared_visibility,
            memory_scope="social",
            tags=tags,
            metadata={"type": post.type or "", "school_only": bool(post.school_only)},
            occurred_at=post.created_at,
        )
        _safe_commit(db)

    _run_safely("ingest_plaza_post", _do)


def ingest_plaza_comment(db: Session, comment) -> None:
    """将用户评论或分身评论沉淀为社交表达记忆。"""
    def _do() -> None:
        content = (comment.content or "").strip()
        if not content:
            return
        create_memory_document(
            db,
            user_id=comment.user_id,
            source_type="plaza_comment",
            source_id=comment.id,
            title="广场评论" if not comment.is_agent else "分身广场评论",
            content=content,
            summary=(content[:160] + "...") if len(content) > 160 else content,
            visibility="avatar_only",
            memory_scope="social",
            metadata={"post_id": comment.post_id, "is_agent": bool(comment.is_agent)},
            occurred_at=comment.created_at,
        )
        _safe_commit(db)

    _run_safely("ingest_plaza_comment", _do)


def ingest_social_message(db: Session, message) -> None:
    """将社交私聊消息沉淀为私有社交记忆。"""
    def _do() -> None:
        content = (message.content or "").strip()
        if not content:
            return
        create_memory_document(
            db,
            user_id=message.from_uid,
            source_type="social_message",
            source_id=message.id,
            title="社交私聊消息",
            content=content,
            summary=(content[:160] + "...") if len(content) > 160 else content,
            visibility="private",
            memory_scope="social",
            metadata={"match_id": message.match_id},
            occurred_at=message.timestamp,
        )
        _safe_commit(db)

    _run_safely("ingest_social_message", _do)


def format_ms(ts: Optional[int]) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")

"""实时语音 Transcript、Session 与 Tool Call 持久化。"""
from __future__ import annotations

import json
import hashlib
import time
from typing import Optional

from sqlalchemy.orm import Session

from app.chat.service import (
    close_and_materialize,
    create_chat_message,
    get_or_create_session,
)
from app.models.chat import ChatMessage, ChatSession
from app.models.realtime_voice import RealtimeVoiceSession
from app.models.user import UserSettings


def _now_ms() -> int:
    return int(time.time() * 1000)


def _user_settings(db: Session, user_id: str) -> UserSettings:
    row = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if row:
        return row
    return UserSettings(
        user_id=user_id,
        chat_material_enabled=True,
        chat_silence_threshold=30,
        chat_material_toast=True,
        chat_min_rounds=3,
    )


async def create_voice_session(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    client_platform: str,
    voice: str,
) -> RealtimeVoiceSession:
    now = _now_ms()
    user_settings = _user_settings(db, user_id)
    silence_threshold = int(user_settings.chat_silence_threshold or 30)
    chat_session, old_session = get_or_create_session(
        db,
        user_id,
        now,
        silence_threshold,
    )
    if old_session:
        await close_and_materialize(db, old_session, user_settings)
    row = RealtimeVoiceSession(
        id=session_id,
        user_id=user_id,
        chat_session_id=chat_session.id,
        provider="volcengine_duplex",
        status="connecting",
        client_platform=client_platform,
        input_format="pcm_16k_s16le",
        output_format="pcm_24k_s16le",
        voice=voice,
        started_at=now,
        last_active_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def mark_session_ready(
    db: Session,
    *,
    session_id: str,
    provider_session_id: str,
    provider_log_id: str = "",
) -> None:
    row = db.query(RealtimeVoiceSession).filter(RealtimeVoiceSession.id == session_id).first()
    if not row:
        return
    now = _now_ms()
    row.provider_session_id = provider_session_id
    row.provider_log_id = provider_log_id
    row.status = "active"
    row.last_active_at = now
    row.updated_at = now
    db.commit()


def touch_voice_session(db: Session, session_id: str) -> None:
    row = db.query(RealtimeVoiceSession).filter(RealtimeVoiceSession.id == session_id).first()
    if row:
        now = _now_ms()
        row.last_active_at = now
        row.updated_at = now
        db.commit()


def save_transcript_message(
    db: Session,
    *,
    voice_session_id: str,
    user_id: str,
    role: str,
    content: str,
    provider_item_id: str,
) -> Optional[ChatMessage]:
    clean_content = str(content or "").strip()
    if not clean_content or role not in {"user", "assistant"}:
        return None
    voice_session = (
        db.query(RealtimeVoiceSession)
        .filter(
            RealtimeVoiceSession.id == voice_session_id,
            RealtimeVoiceSession.user_id == user_id,
        )
        .first()
    )
    if not voice_session or not voice_session.chat_session_id:
        return None

    stable_item_id = str(provider_item_id or "").strip()
    client_message_id = (
        f"realtime:{role}:{stable_item_id}"
        if stable_item_id
        else (
            f"realtime:{role}:{voice_session_id}:"
            f"{hashlib.sha256(clean_content.encode('utf-8')).hexdigest()[:24]}"
        )
    )
    existing = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.user_id == user_id,
            ChatMessage.client_message_id == client_message_id,
        )
        .first()
    )
    if existing:
        return existing

    now = _now_ms()
    message = create_chat_message(
        db,
        user_id=user_id,
        role=role,
        content=clean_content,
        timestamp=now,
        session_id=voice_session.chat_session_id,
        client_message_id=client_message_id,
        attachments=[],
    )
    chat_session = (
        db.query(ChatSession)
        .filter(ChatSession.id == voice_session.chat_session_id)
        .first()
    )
    if chat_session:
        chat_session.end_time = now
        chat_session.message_count = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == chat_session.id)
            .count()
            + 1
        )
    voice_session.last_active_at = now
    voice_session.updated_at = now
    db.commit()
    db.refresh(message)
    return message


def update_voice_usage(
    db: Session,
    *,
    session_id: str,
    usage: dict,
) -> None:
    row = db.query(RealtimeVoiceSession).filter(RealtimeVoiceSession.id == session_id).first()
    if not row:
        return
    row.usage_json = json.dumps(usage or {}, ensure_ascii=False)
    row.updated_at = _now_ms()
    db.commit()


def mark_voice_error(
    db: Session,
    *,
    session_id: str,
    error_code: str,
) -> None:
    row = db.query(RealtimeVoiceSession).filter(RealtimeVoiceSession.id == session_id).first()
    if not row:
        return
    row.status = "error"
    row.error_code = str(error_code or "")[:120]
    row.updated_at = _now_ms()
    db.commit()


async def close_voice_session(
    db: Session,
    *,
    session_id: str,
    reason: str,
) -> None:
    row = db.query(RealtimeVoiceSession).filter(RealtimeVoiceSession.id == session_id).first()
    if not row:
        return
    now = _now_ms()
    row.status = "closed" if row.status != "error" else "error"
    row.ended_at = now
    row.last_active_at = now
    row.close_reason = str(reason or "user")[:80]
    row.updated_at = now
    db.commit()

    if not row.chat_session_id:
        return
    chat_session = db.query(ChatSession).filter(ChatSession.id == row.chat_session_id).first()
    if not chat_session or chat_session.status == "closed":
        return
    try:
        await close_and_materialize(db, chat_session, _user_settings(db, row.user_id))
    except Exception:
        # 会话关闭与 transcript 已落库；摘要失败不应阻塞清理。
        chat_session.status = "closed"
        chat_session.end_time = chat_session.end_time or now
        db.commit()

"""实时语音 Provider 与 Session 配置构造。"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.config import settings
from app.models.chat import ChatMessage
from app.models.memory import AvatarCard, MemoryProfile
from app.models.user import User
from app.realtime_voice.fake_provider import FakeRealtimeVoiceProvider
from app.realtime_voice.prompts import build_realtime_voice_instructions
from app.realtime_voice.provider import (
    ProviderSessionConfig,
    RealtimeVoiceProvider,
    ToolDefinition,
)
from app.realtime_voice.volcengine import VolcengineDuplexProvider


def _decode(raw: str, default):
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _recent_history_items(db: Session, user_id: str, *, max_rounds: int = 6) -> list[dict]:
    rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.user_id == user_id,
            ChatMessage.role.in_(["user", "assistant"]),
        )
        .order_by(ChatMessage.timestamp.desc())
        .limit(max_rounds * 6)
        .all()
    )
    chronological = list(reversed(rows))
    pairs: list[tuple[ChatMessage, ChatMessage]] = []
    pending_user: ChatMessage | None = None
    for message in chronological:
        if message.role == "user":
            pending_user = message
        elif message.role == "assistant" and pending_user:
            pairs.append((pending_user, message))
            pending_user = None
    selected = pairs[-max_rounds:]
    items: list[dict] = []
    for user_message, assistant_message in selected:
        for message in (user_message, assistant_message):
            content = str(message.content or "").strip()
            if not content:
                continue
            items.append(
                {
                    "role": message.role,
                    "content": [
                        {
                            "type": "input_text",
                            "text": content[:1200],
                        }
                    ],
                }
            )
    return items[: max_rounds * 2]


def build_provider_session_config(
    db: Session,
    *,
    user: User,
    voice: str,
    tools: list[ToolDefinition],
    resume_session_id: str | None = None,
    entry_mode: str = "general",
) -> ProviderSessionConfig:
    profile = (
        db.query(MemoryProfile)
        .filter(
            MemoryProfile.user_id == user.id,
            MemoryProfile.profile_type == "avatar",
        )
        .first()
    )
    card = db.query(AvatarCard).filter(AvatarCard.user_id == user.id).first()
    boundaries = _decode(card.boundaries, []) if card else []
    instructions = build_realtime_voice_instructions(
        user_name=user.name or user.username,
        profile_summary=profile.summary if profile else "",
        boundaries=boundaries,
        mode=entry_mode,
    )
    return ProviderSessionConfig(
        instructions=instructions,
        voice=voice,
        model=settings.VOLC_REALTIME_VOICE_MODEL,
        resume_session_id=resume_session_id,
        tools=tools,
        initial_context=_recent_history_items(db, user.id, max_rounds=6),
    )


def create_provider() -> RealtimeVoiceProvider:
    provider_name = str(settings.REALTIME_VOICE_PROVIDER or "volcengine_duplex").strip()
    if provider_name == "fake":
        return FakeRealtimeVoiceProvider()
    if provider_name != "volcengine_duplex":
        raise RuntimeError(f"不支持的实时语音 Provider：{provider_name}")
    return VolcengineDuplexProvider(
        api_key=settings.VOLC_REALTIME_VOICE_API_KEY,
        url=settings.VOLC_REALTIME_VOICE_URL,
    )


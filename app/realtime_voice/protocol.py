"""Avalin 客户端实时语音 WebSocket 协议。"""
from __future__ import annotations

import base64
import binascii
import json
import time
from typing import Literal, Optional, Union
from uuid import uuid4

from pydantic import ConfigDict, Field, ValidationError, field_validator

from app.serializers import CamelModel


MAX_AUDIO_BASE64_CHARS = 128 * 1024


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str, *, recoverable: bool = True):
        self.code = code
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)


class _ClientEvent(CamelModel):
    model_config = ConfigDict(
        alias_generator=CamelModel.model_config["alias_generator"],
        populate_by_name=True,
        extra="forbid",
    )

    type: str
    event_id: str = Field(min_length=1, max_length=128)


class SessionStartEvent(_ClientEvent):
    type: Literal["session.start"]
    voice: str = ""
    resume_session_id: Optional[str] = None
    entry_mode: Literal["general", "social_mission"] = "general"


class AudioAppendEvent(_ClientEvent):
    type: Literal["audio.append"]
    audio: str = Field(min_length=1, max_length=MAX_AUDIO_BASE64_CHARS)

    @field_validator("audio")
    @classmethod
    def validate_audio_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("audio 必须是合法 Base64") from exc
        return value


class AudioCommitEvent(_ClientEvent):
    type: Literal["audio.commit"]


class ResponseCancelEvent(_ClientEvent):
    type: Literal["response.cancel"]


class ConfirmationResolveEvent(_ClientEvent):
    type: Literal["confirmation.resolve"]
    confirmation_id: str = Field(min_length=1, max_length=128)
    decision: Literal["approve", "reject"]


class SessionCloseEvent(_ClientEvent):
    type: Literal["session.close"]


ClientEvent = Union[
    SessionStartEvent,
    AudioAppendEvent,
    AudioCommitEvent,
    ResponseCancelEvent,
    ConfirmationResolveEvent,
    SessionCloseEvent,
]

_EVENT_MODELS = {
    "session.start": SessionStartEvent,
    "audio.append": AudioAppendEvent,
    "audio.commit": AudioCommitEvent,
    "response.cancel": ResponseCancelEvent,
    "confirmation.resolve": ConfirmationResolveEvent,
    "session.close": SessionCloseEvent,
}

_ALLOWED_STATES = {
    "session.start": {"idle", "connecting"},
    "audio.append": {
        "ready",
        "listening",
        "thinking",
        "speaking",
        "tool_running",
        "awaiting_confirmation",
    },
    "audio.commit": {
        "ready",
        "listening",
        "thinking",
        "speaking",
        "tool_running",
        "awaiting_confirmation",
    },
    "response.cancel": {"thinking", "speaking", "tool_running"},
    "confirmation.resolve": {"awaiting_confirmation"},
    "session.close": {
        "connecting",
        "ready",
        "listening",
        "thinking",
        "speaking",
        "interrupted",
        "tool_running",
        "awaiting_confirmation",
        "reconnecting",
        "error",
    },
}


def parse_client_event(raw: str | dict, *, state: str) -> ClientEvent:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid_json", "消息不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("invalid_event", "消息必须是 JSON 对象")

    event_type = str(payload.get("type") or "")
    model = _EVENT_MODELS.get(event_type)
    if not model:
        raise ProtocolError("unknown_event", f"不支持的事件类型：{event_type or 'empty'}")
    allowed = _ALLOWED_STATES[event_type]
    if state not in allowed:
        raise ProtocolError(
            "invalid_state",
            f"当前状态 {state} 不允许事件 {event_type}",
            recoverable=state != "closed",
        )
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        detail = str(first.get("msg") or "字段不合法")
        raise ProtocolError("invalid_event", detail) from exc


def server_event(
    event_type: str,
    *,
    session_id: str,
    event_id: str | None = None,
    **payload,
) -> dict:
    return {
        "type": event_type,
        "eventId": event_id or f"evt-{uuid4()}",
        "sessionId": session_id,
        "timestamp": int(time.time() * 1000),
        **payload,
    }


def error_event(
    *,
    session_id: str,
    code: str,
    message: str,
    recoverable: bool,
) -> dict:
    return server_event(
        "error",
        session_id=session_id,
        code=code,
        message=message,
        recoverable=recoverable,
    )

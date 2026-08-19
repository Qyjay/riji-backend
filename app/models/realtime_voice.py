"""实时语音分身会话与工具调用审计模型。"""
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)

from app.database import Base


def _uuid() -> str:
    return str(uuid4())


class RealtimeVoiceSession(Base):
    """一次客户端到豆包全双工模型的实时语音会话。"""

    __tablename__ = "realtime_voice_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    chat_session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=True)
    provider = Column(String, default="volcengine_duplex")
    provider_session_id = Column(String, default="")
    status = Column(String, default="connecting")
    client_platform = Column(String, default="h5")
    input_format = Column(String, default="pcm_16k_s16le")
    output_format = Column(String, default="pcm_24k_s16le")
    voice = Column(String, default="")
    started_at = Column(BigInteger, nullable=False)
    ended_at = Column(BigInteger, nullable=True)
    last_active_at = Column(BigInteger, nullable=False)
    close_reason = Column(String, default="")
    provider_log_id = Column(String, default="")
    usage_json = Column(Text, default="{}")
    error_code = Column(String, default="")
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_realtime_voice_sessions_user_time", "user_id", "created_at"),
        Index("ix_realtime_voice_sessions_status_active", "status", "last_active_at"),
        Index("ix_realtime_voice_sessions_provider_session", "provider_session_id"),
    )


class RealtimeToolCall(Base):
    """实时模型 Function Calling 的持久化审计与幂等记录。"""

    __tablename__ = "realtime_tool_calls"

    id = Column(String, primary_key=True, default=_uuid)
    voice_session_id = Column(
        String,
        ForeignKey("realtime_voice_sessions.id"),
        nullable=False,
    )
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider_call_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    arguments_json = Column(Text, default="{}")
    risk_level = Column(String, default="R0")
    status = Column(String, default="received")
    result_json = Column(Text, default="{}")
    confirmation_id = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=False)
    error_message = Column(Text, default="")
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    finished_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "voice_session_id",
            "provider_call_id",
            name="uq_realtime_tool_call_provider",
        ),
        Index("ix_realtime_tool_calls_user_time", "user_id", "created_at"),
        Index("ix_realtime_tool_calls_status", "status", "updated_at"),
        Index("ix_realtime_tool_calls_idempotency", "idempotency_key"),
    )

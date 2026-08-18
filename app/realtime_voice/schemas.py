"""实时语音 REST API Schema。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.serializers import CamelModel


class CreateVoiceTicketRequest(BaseModel):
    voice: str = ""
    output_format: Literal["pcm_s16le"] = "pcm_s16le"
    client_platform: Literal["h5", "app-android"] = "h5"


class AudioFormatOut(CamelModel):
    type: str
    sample_rate: int
    channels: int
    bits_per_sample: int
    recommended_frame_ms: Optional[int] = None


class VoiceTicketOut(CamelModel):
    ticket: str
    expires_at: int
    websocket_path: str
    input: AudioFormatOut
    output: AudioFormatOut


class VoiceHealthOut(CamelModel):
    enabled: bool
    configured: bool
    provider: str
    active_sessions: int
    max_sessions: int
    metrics: dict[str, int] = Field(default_factory=dict)

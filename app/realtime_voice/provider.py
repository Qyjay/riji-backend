"""实时语音供应商抽象与标准化事件。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]

    def to_provider_dict(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass
class ProviderSessionConfig:
    instructions: str
    voice: str
    input_type: str = "pcm"
    input_rate: int = 16000
    output_type: str = "pcm_s16le"
    output_rate: int = 24000
    speed: int = 0
    loudness: int = 0
    model: str = "1.2.6.1"
    resume_session_id: str | None = None
    tools: list[ToolDefinition] = field(default_factory=list)
    initial_context: list[dict[str, Any]] = field(default_factory=list)
    extension: dict[str, Any] = field(
        default_factory=lambda: {"asr": {}, "tts": {}, "dialog": {}}
    )


@dataclass
class ProviderToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass
class ProviderToolResult:
    call_id: str
    output: str


@dataclass
class ProviderEvent:
    type: str
    event_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[ProviderToolCall] = field(default_factory=list)


class RealtimeVoiceProvider(Protocol):
    provider_log_id: str
    provider_session_id: str

    async def connect(self, config: ProviderSessionConfig) -> None: ...

    async def reconnect(self, config: ProviderSessionConfig) -> None: ...

    async def send_audio(self, pcm_base64: str, event_id: str) -> None: ...

    async def commit_audio(self, event_id: str) -> None: ...

    async def cancel_response(self, event_id: str) -> None: ...

    async def send_tool_results(self, results: list[ProviderToolResult]) -> None: ...

    async def update_tools(self, tools: list[ToolDefinition]) -> None: ...

    async def send_context(self, items: list[dict[str, Any]]) -> None: ...

    def receive(self) -> AsyncIterator[ProviderEvent]: ...

    async def close(self) -> None: ...

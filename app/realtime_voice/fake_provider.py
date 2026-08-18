"""无需网络的实时语音 Provider，用于单元测试和本地协议联调。"""
from __future__ import annotations

import asyncio

from app.realtime_voice.provider import (
    ProviderEvent,
    ProviderSessionConfig,
    ProviderToolResult,
    ToolDefinition,
)


class FakeRealtimeVoiceProvider:
    def __init__(self, scripted_events: list[ProviderEvent] | None = None) -> None:
        self.provider_log_id = "fake-log-id"
        self.provider_session_id = "fake-provider-session"
        self.config: ProviderSessionConfig | None = None
        self.audio_events: list[tuple[str, str]] = []
        self.commits: list[str] = []
        self.cancels: list[str] = []
        self.tool_results: list[ProviderToolResult] = []
        self.tool_updates: list[list[ToolDefinition]] = []
        self.context_items: list[dict] = []
        self.closed = False
        self.connect_count = 0
        self.reconnect_count = 0
        self._scripted_events = list(scripted_events or [])
        self._queue: asyncio.Queue | None = None

    async def connect(self, config: ProviderSessionConfig) -> None:
        self.connect_count += 1
        self.config = config
        self._queue = asyncio.Queue()
        for event in self._scripted_events:
            self._queue.put_nowait(event)

    async def reconnect(self, config: ProviderSessionConfig) -> None:
        self.reconnect_count += 1
        self.config = config
        if self._queue is None:
            self._queue = asyncio.Queue()

    async def send_audio(self, pcm_base64: str, event_id: str) -> None:
        self.audio_events.append((event_id, pcm_base64))

    async def commit_audio(self, event_id: str) -> None:
        self.commits.append(event_id)

    async def cancel_response(self, event_id: str) -> None:
        self.cancels.append(event_id)

    async def send_tool_results(self, results: list[ProviderToolResult]) -> None:
        self.tool_results.extend(results)

    async def update_tools(self, tools: list[ToolDefinition]) -> None:
        self.tool_updates.append(list(tools))

    async def send_context(self, items: list[dict]) -> None:
        self.context_items.extend(items)

    async def push(self, event: ProviderEvent) -> None:
        if self._queue is None:
            self._queue = asyncio.Queue()
        await self._queue.put(event)

    async def finish(self) -> None:
        if self._queue is None:
            self._queue = asyncio.Queue()
        await self._queue.put(None)

    async def receive(self):
        if self._queue is None:
            self._queue = asyncio.Queue()
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event

    async def close(self) -> None:
        self.closed = True
        await self.finish()

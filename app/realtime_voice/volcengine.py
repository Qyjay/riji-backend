"""豆包实时语音模型 3.0 全双工 WebSocket Provider。"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import websockets

from app.realtime_voice.provider import (
    ProviderEvent,
    ProviderSessionConfig,
    ProviderToolCall,
    ProviderToolResult,
    ToolDefinition,
)


class VolcengineRealtimeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        recoverable: bool = False,
    ) -> None:
        self.code = code
        self.recoverable = recoverable
        super().__init__(message)


class VolcengineDuplexProvider:
    def __init__(
        self,
        *,
        api_key: str,
        url: str,
        open_timeout: float = 10,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        self._url = url
        self._open_timeout = open_timeout
        self._ws: Any = None
        self._session_closed = asyncio.Event()
        self.provider_log_id = ""
        self.provider_session_id = ""

    async def _send(self, payload: dict) -> None:
        if not self._ws:
            raise VolcengineRealtimeError("实时语音连接尚未建立")
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    async def connect(self, config: ProviderSessionConfig) -> None:
        if not self._api_key:
            raise VolcengineRealtimeError("实时语音 API Key 未配置")
        self._session_closed = asyncio.Event()
        self._ws = await websockets.connect(
            self._url,
            extra_headers={"X-Api-Key": self._api_key},
            open_timeout=self._open_timeout,
            ping_interval=20,
            ping_timeout=20,
            max_size=2 * 1024 * 1024,
        )
        headers = getattr(self._ws, "response_headers", None)
        if headers:
            self.provider_log_id = str(
                headers.get("X-Tt-Logid") or headers.get("x-tt-logid") or ""
            )

        session: dict[str, Any] = {
            "type": "realtime",
            "model": config.model,
            "instructions": config.instructions,
            "audio": {
                "input": {
                    "format": {
                        "type": config.input_type,
                        "rate": config.input_rate,
                    }
                },
                "output": {
                    "format": {
                        "type": config.output_type,
                        "rate": config.output_rate,
                    },
                    "voice": config.voice,
                    "speed": config.speed,
                    "loudness": config.loudness,
                },
            },
            "tools": [tool.to_provider_dict() for tool in config.tools],
        }
        if config.resume_session_id:
            session["id"] = config.resume_session_id
        await self._send(
            {
                "type": "session.create",
                "event_id": f"evt-{uuid4()}",
                "session": session,
                "extension": config.extension,
            }
        )

    async def reconnect(self, config: ProviderSessionConfig) -> None:
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        await self.connect(config)

    async def send_audio(self, pcm_base64: str, event_id: str) -> None:
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "event_id": event_id,
                "audio": pcm_base64,
            }
        )

    async def commit_audio(self, event_id: str) -> None:
        await self._send(
            {
                "type": "input_audio_buffer.commit",
                "event_id": event_id,
            }
        )

    async def cancel_response(self, event_id: str) -> None:
        await self._send({"type": "response.cancel", "event_id": event_id})

    async def send_tool_results(self, results: list[ProviderToolResult]) -> None:
        if not results:
            return
        await self._send(
            {
                "type": "conversation.item.create",
                "event_id": f"evt-{uuid4()}",
                "items": [
                    {
                        "call_id": result.call_id,
                        "role": "tool",
                        "content": [
                            {
                                "type": "input_text",
                                "text": result.output,
                            }
                        ],
                    }
                    for result in results
                ],
            }
        )

    async def update_tools(self, tools: list[ToolDefinition]) -> None:
        await self._send(
            {
                "type": "session.update",
                "event_id": f"evt-{uuid4()}",
                "session": {
                    "tools": [tool.to_provider_dict() for tool in tools],
                },
            }
        )

    async def send_context(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        await self._send(
            {
                "type": "conversation.item.create",
                "event_id": f"evt-{uuid4()}",
                "items": items[:40],
            }
        )

    @staticmethod
    def _text(payload: dict) -> str:
        return str(
            payload.get("delta")
            or payload.get("text")
            or payload.get("transcript")
            or ""
        )

    @staticmethod
    def _tool_calls(payload: dict) -> list[ProviderToolCall]:
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raw_item = payload.get("item")
            raw_items = [raw_item] if isinstance(raw_item, dict) else []
        calls = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            call_id = str(item.get("call_id") or item.get("callId") or "").strip()
            name = str(item.get("name") or "").strip()
            arguments = item.get("arguments", "{}")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            if call_id and name:
                calls.append(
                    ProviderToolCall(
                        call_id=call_id,
                        name=name,
                        arguments=arguments,
                    )
                )
        return calls

    def _map_event(self, payload: dict) -> ProviderEvent | None:
        raw_type = str(payload.get("type") or "")
        event_id = str(payload.get("event_id") or "")
        if raw_type == "session.created":
            session = payload.get("session") or {}
            self.provider_session_id = str(session.get("id") or "")
            return ProviderEvent(
                "session.ready",
                event_id,
                {"providerSessionId": self.provider_session_id},
            )
        if raw_type == "session.updated":
            return ProviderEvent("session.updated", event_id, {})
        if raw_type == "session.closed":
            self._session_closed.set()
            return ProviderEvent("session.closed", event_id, {})
        if raw_type == "input_audio_buffer.committed":
            return ProviderEvent("audio.committed", event_id, {})
        if raw_type == "conversation.item.input_audio_transcription.started":
            return ProviderEvent("asr.started", event_id, {})
        if raw_type == "conversation.item.input_audio_transcription.delta":
            return ProviderEvent("asr.delta", event_id, {"text": self._text(payload)})
        if raw_type == "conversation.item.input_audio_transcription.completed":
            return ProviderEvent(
                "asr.done",
                event_id,
                {
                    "text": self._text(payload),
                    "itemId": str(payload.get("item_id") or payload.get("question_id") or ""),
                },
            )
        if raw_type == "conversation.item.input_audio_transcription.failed":
            return ProviderEvent(
                "asr.failed",
                event_id,
                {"message": str(payload.get("message") or "语音识别失败")},
            )
        if raw_type == "response.output_text.delta":
            return ProviderEvent(
                "assistant.text.delta",
                event_id,
                {"text": self._text(payload)},
            )
        if raw_type == "response.output_text.done":
            return ProviderEvent(
                "assistant.text.done",
                event_id,
                {
                    "text": self._text(payload),
                    "itemId": str(payload.get("item_id") or payload.get("reply_id") or ""),
                },
            )
        if raw_type == "response.output_audio.started":
            return ProviderEvent(
                "assistant.audio.started",
                event_id,
                {"ttsType": str(payload.get("tts_type") or "default")},
            )
        if raw_type == "response.output_audio.delta":
            return ProviderEvent(
                "assistant.audio.delta",
                event_id,
                {
                    "audio": str(payload.get("delta") or payload.get("audio") or ""),
                    "sequence": int(payload.get("sequence") or 0),
                },
            )
        if raw_type == "response.output_audio.done":
            return ProviderEvent(
                "assistant.audio.done",
                event_id,
                {"statusCode": str(payload.get("status_code") or "")},
            )
        if raw_type == "response.function_call_arguments.done":
            return ProviderEvent(
                "tool.calls",
                event_id,
                {},
                tool_calls=self._tool_calls(payload),
            )
        if raw_type == "response.done":
            return ProviderEvent(
                "response.done",
                event_id,
                {"usage": payload.get("usage") or {}},
            )
        if raw_type == "response.canceled":
            return ProviderEvent("response.canceled", event_id, {})
        if raw_type == "error":
            code = str(payload.get("status_code") or payload.get("code") or "provider_error")
            message = str(payload.get("message") or "实时语音服务异常")
            return ProviderEvent(
                "error",
                event_id,
                {
                    "code": code,
                    "message": message,
                    "recoverable": code.startswith("5"),
                },
            )
        return None

    async def receive(self):
        if not self._ws:
            raise VolcengineRealtimeError("实时语音连接尚未建立")
        async for raw in self._ws:
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            event = self._map_event(payload)
            if event:
                yield event

    async def close(self) -> None:
        if not self._ws:
            return
        if not self._session_closed.is_set():
            try:
                await self._send(
                    {
                        "type": "session.close",
                        "event_id": f"evt-{uuid4()}",
                    }
                )
                await asyncio.wait_for(self._session_closed.wait(), timeout=3)
            except Exception:
                pass
        await self._ws.close()
        self._ws = None

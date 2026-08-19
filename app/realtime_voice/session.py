"""单次实时语音会话编排。"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any, Callable
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from app.config import settings
from sqlalchemy.orm import Session
from app.models.user import User
from app.realtime_voice.config import build_provider_session_config
from app.realtime_voice.observability import (
    hash_user_id,
    log_voice_event,
    voice_metrics,
)
from app.realtime_voice.persistence import (
    close_voice_session,
    create_voice_session,
    mark_session_ready,
    mark_voice_error,
    save_transcript_message,
    touch_voice_session,
    update_voice_usage,
)
from app.realtime_voice.protocol import (
    AudioAppendEvent,
    AudioCommitEvent,
    ConfirmationResolveEvent,
    ProtocolError,
    ResponseCancelEvent,
    SessionCloseEvent,
    SessionStartEvent,
    error_event,
    parse_client_event,
    server_event,
)
from app.realtime_voice.provider import (
    ProviderEvent,
    ProviderSessionConfig,
    ProviderToolResult,
    RealtimeVoiceProvider,
)


class RealtimeVoiceSessionRunner:
    def __init__(
        self,
        *,
        websocket: WebSocket,
        user: User,
        ticket_payload: dict,
        provider: RealtimeVoiceProvider,
        db_factory: Callable[[], Session],
        tool_router: Any = None,
    ) -> None:
        self.websocket = websocket
        self.user = user
        self.ticket_payload = ticket_payload
        self.provider = provider
        self.db_factory = db_factory
        self.tool_router = tool_router
        self.session_id = str(uuid4())
        self.state = "idle"
        self.close_reason = "network"
        self._stop_event = asyncio.Event()
        self._last_active_monotonic = time.monotonic()
        self._last_touch_persisted = 0.0
        self._session_closed_sent = False
        self._initial_context: list[dict] = []
        self._provider_config: ProviderSessionConfig | None = None
        self._provider_ready = asyncio.Event()
        self._provider_queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue(
            maxsize=max(10, int(settings.REALTIME_VOICE_MAX_INPUT_FRAMES))
        )
        self._backpressure_hits = 0
        self._reconnect_attempt = 0
        self._started_monotonic = time.monotonic()
        self._memory_evidence_count = 0
        self._mission_id = ""

    async def _send(self, event: dict) -> None:
        await self.websocket.send_json(event)

    async def _send_state(self, state: str) -> None:
        self.state = state
        await self._send(
            server_event(
                "session.state",
                session_id=self.session_id,
                state=state,
            )
        )

    def _touch(self) -> None:
        self._last_active_monotonic = time.monotonic()
        if self._last_active_monotonic - self._last_touch_persisted < 5:
            return
        self._last_touch_persisted = self._last_active_monotonic
        db = self.db_factory()
        try:
            touch_voice_session(db, self.session_id)
        finally:
            db.close()

    async def _first_event(self) -> SessionStartEvent:
        try:
            raw = await asyncio.wait_for(self.websocket.receive_text(), timeout=15)
        except asyncio.TimeoutError as exc:
            raise ProtocolError(
                "session_start_timeout",
                "等待 session.start 超时",
                recoverable=False,
            ) from exc
        event = parse_client_event(raw, state="idle")
        if not isinstance(event, SessionStartEvent):
            raise ProtocolError(
                "session_start_required",
                "首个事件必须是 session.start",
                recoverable=False,
            )
        ticket_voice = str(self.ticket_payload.get("voice") or "")
        if event.voice and event.voice != ticket_voice:
            raise ProtocolError(
                "voice_mismatch",
                "音色与 Ticket 不一致",
                recoverable=False,
            )
        return event

    async def _create_persistence(self) -> None:
        db = self.db_factory()
        try:
            await create_voice_session(
                db,
                session_id=self.session_id,
                user_id=self.user.id,
                client_platform=str(self.ticket_payload.get("platform") or "h5"),
                voice=str(self.ticket_payload.get("voice") or ""),
            )
        finally:
            db.close()

    async def _enqueue_provider_action(
        self,
        *,
        kind: str,
        payload: str,
        event_id: str,
    ) -> bool:
        try:
            self._provider_queue.put_nowait((kind, payload, event_id))
            self._backpressure_hits = 0
            return True
        except asyncio.QueueFull:
            self._backpressure_hits += 1
            voice_metrics.increment("input_backpressure")
            await self._send(
                server_event(
                    "client.slow_down",
                    session_id=self.session_id,
                    queuedFrames=self._provider_queue.qsize(),
                    maxFrames=self._provider_queue.maxsize,
                )
            )
            if self._backpressure_hits >= 3:
                self.close_reason = "client_backpressure"
                await self._send(
                    error_event(
                        session_id=self.session_id,
                        code="client_backpressure",
                        message="音频发送速度过快，请重新连接后再试",
                        recoverable=False,
                    )
                )
                self._stop_event.set()
            return False

    async def _provider_sender(self) -> None:
        while not self._stop_event.is_set():
            kind, payload, event_id = await self._provider_queue.get()
            try:
                await self._provider_ready.wait()
                if kind == "audio":
                    await self.provider.send_audio(payload, event_id)
                elif kind == "commit":
                    await self.provider.commit_audio(event_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                voice_metrics.increment("provider_send_error")
                log_voice_event(
                    "provider_send_error",
                    level=logging.WARNING,
                    voice_session_id=self.session_id,
                    user_id_hash=hash_user_id(self.user.id),
                    error_code=type(exc).__name__,
                )
            finally:
                self._provider_queue.task_done()

    def _discard_queued_audio(self) -> int:
        discarded = 0
        while True:
            try:
                self._provider_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                self._provider_queue.task_done()
                discarded += 1
        if discarded:
            voice_metrics.increment("reconnect_dropped_frames", discarded)
        return discarded

    async def _client_reader(self) -> None:
        try:
            while not self._stop_event.is_set():
                raw = await self.websocket.receive_text()
                try:
                    event = parse_client_event(raw, state=self.state)
                except ProtocolError as exc:
                    await self._send(
                        error_event(
                            session_id=self.session_id,
                            code=exc.code,
                            message=exc.message,
                            recoverable=exc.recoverable,
                        )
                    )
                    if not exc.recoverable:
                        self.close_reason = "protocol_error"
                        self._stop_event.set()
                    continue

                self._touch()
                if isinstance(event, AudioAppendEvent):
                    await self._enqueue_provider_action(
                        kind="audio",
                        payload=event.audio,
                        event_id=event.event_id,
                    )
                elif isinstance(event, AudioCommitEvent):
                    await self._enqueue_provider_action(
                        kind="commit",
                        payload="",
                        event_id=event.event_id,
                    )
                    await self._send_state("thinking")
                elif isinstance(event, ResponseCancelEvent):
                    await self.provider.cancel_response(event.event_id)
                    await self._send_state("interrupted")
                elif isinstance(event, ConfirmationResolveEvent):
                    if not self.tool_router:
                        await self._send(
                            error_event(
                                session_id=self.session_id,
                                code="confirmation_unavailable",
                                message="当前没有待确认操作",
                                recoverable=True,
                            )
                        )
                    else:
                        try:
                            provider_result, display_events = (
                                await self.tool_router.resolve_confirmation(
                                    confirmation_id=event.confirmation_id,
                                    decision=event.decision,
                                )
                            )
                            for display_event in display_events:
                                await self._send(display_event)
                            if provider_result:
                                await self.provider.send_context(
                                    [
                                        {
                                            "role": "user",
                                            "content": [
                                                {
                                                    "type": "input_text",
                                                    "text": (
                                                        "用户已通过屏幕完成确认。"
                                                        f"执行结果：{provider_result.output}"
                                                    ),
                                                }
                                            ],
                                        }
                                    ]
                                )
                            await self._send_state(
                                "thinking"
                                if event.decision == "approve"
                                else "listening"
                            )
                        except Exception as exc:
                            await self._send(
                                error_event(
                                    session_id=self.session_id,
                                    code="confirmation_unavailable",
                                    message=str(exc)[:200],
                                    recoverable=True,
                                )
                            )
                elif isinstance(event, SessionCloseEvent):
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._provider_queue.join(), timeout=1)
                    self.close_reason = "user"
                    self._stop_event.set()
        except WebSocketDisconnect:
            self.close_reason = "network"
            self._stop_event.set()

    def _save_transcript(self, *, role: str, event: ProviderEvent) -> None:
        db = self.db_factory()
        try:
            save_transcript_message(
                db,
                voice_session_id=self.session_id,
                user_id=self.user.id,
                role=role,
                content=str(event.payload.get("text") or ""),
                provider_item_id=str(
                    event.payload.get("itemId") or event.event_id or uuid4()
                ),
            )
        finally:
            db.close()

    async def _handle_tool_calls(self, event: ProviderEvent) -> None:
        if not event.tool_calls:
            return
        if not self.tool_router:
            results = [
                ProviderToolResult(
                    call_id=call.call_id,
                    output='{"ok":false,"data":null,"error":"工具服务尚未启用"}',
                )
                for call in event.tool_calls
            ]
            await self.provider.send_tool_results(results)
            return

        await self._send_state("tool_running")
        for call in event.tool_calls:
            await self._send(
                server_event(
                    "tool.started",
                    session_id=self.session_id,
                    toolCallId=call.call_id,
                    name=call.name,
                )
            )
        results, display_events = await self.tool_router.execute_calls(event.tool_calls)
        requires_confirmation = False
        for display_event in display_events:
            if display_event.get("type") == "tool.result":
                display = display_event.get("display") or {}
                if display.get("kind") == "memory_evidence":
                    self._memory_evidence_count += len(display.get("items") or [])
                mission = display.get("mission") or {}
                self._mission_id = str(
                    display.get("missionId")
                    or mission.get("id")
                    or self._mission_id
                )
            await self._send(display_event)
            if display_event.get("type") == "confirmation.required":
                requires_confirmation = True
        await self.provider.send_tool_results(results)
        await self._send_state(
            "awaiting_confirmation" if requires_confirmation else "thinking"
        )

    async def _attempt_provider_reconnect(self, error_code: str) -> bool:
        max_reconnects = max(0, int(settings.REALTIME_VOICE_MAX_RECONNECTS))
        self._provider_ready.clear()
        self._discard_queued_audio()
        while self._reconnect_attempt < max_reconnects and not self._stop_event.is_set():
            self._reconnect_attempt += 1
            attempt = self._reconnect_attempt
            voice_metrics.increment("provider_reconnect_attempt")
            await self._send_state("reconnecting")
            await self._send(
                server_event(
                    "session.reconnecting",
                    session_id=self.session_id,
                    attempt=attempt,
                    maxAttempts=max_reconnects,
                )
            )
            log_voice_event(
                "provider_reconnecting",
                level=logging.WARNING,
                voice_session_id=self.session_id,
                user_id_hash=hash_user_id(self.user.id),
                attempt=attempt,
                error_code=error_code,
            )
            await asyncio.sleep(attempt)
            if not self._provider_config:
                break
            self._provider_config.resume_session_id = (
                self.provider.provider_session_id
                or self._provider_config.resume_session_id
            )
            try:
                await self.provider.reconnect(self._provider_config)
                return True
            except Exception as exc:
                error_code = type(exc).__name__
        voice_metrics.increment("provider_reconnect_exhausted")
        db = self.db_factory()
        try:
            mark_voice_error(
                db,
                session_id=self.session_id,
                error_code=str(error_code or "provider_reconnect_failed"),
            )
        finally:
            db.close()
        await self._send(
            error_event(
                session_id=self.session_id,
                code="provider_reconnect_failed",
                message="未能恢复语音连接，请重新开始通话",
                recoverable=False,
            )
        )
        self.close_reason = "provider_error"
        self._stop_event.set()
        return False

    async def _handle_provider_event(self, event: ProviderEvent) -> str:
        """返回 reconnect、stop 或 continue。"""
        self._touch()
        event_type = event.type
        if event_type == "session.ready":
            provider_session_id = str(event.payload.get("providerSessionId") or "")
            db = self.db_factory()
            try:
                mark_session_ready(
                    db,
                    session_id=self.session_id,
                    provider_session_id=provider_session_id,
                    provider_log_id=self.provider.provider_log_id,
                )
            finally:
                db.close()
            self._provider_ready.set()
            self._reconnect_attempt = 0
            voice_metrics.increment("session_ready")
            await self._send(
                server_event(
                    "session.ready",
                    session_id=self.session_id,
                    event_id=event.event_id or None,
                    providerSessionId=provider_session_id,
                )
            )
            if self._initial_context:
                await self.provider.send_context(self._initial_context)
                self._initial_context = []
            await self._send_state("listening")
            return "continue"
        if event_type == "asr.started":
            await self._send_state("listening")
        elif event_type == "asr.done":
            self._save_transcript(role="user", event=event)
            if self.tool_router:
                self.tool_router.note_user_turn()
        elif event_type == "assistant.text.delta" and self.state != "speaking":
            await self._send_state("thinking")
        elif event_type == "assistant.text.done":
            self._save_transcript(role="assistant", event=event)
        elif event_type == "assistant.audio.started":
            await self._send_state("speaking")
        elif event_type == "assistant.audio.done":
            await self._send_state("listening")
        elif event_type == "audio.committed":
            await self._send_state("thinking")
        elif event_type == "tool.calls":
            await self._handle_tool_calls(event)
            return "continue"
        elif event_type == "response.canceled":
            voice_metrics.increment("response_canceled")
            await self._send_state("listening")
        elif event_type == "response.done":
            db = self.db_factory()
            try:
                update_voice_usage(
                    db,
                    session_id=self.session_id,
                    usage=event.payload.get("usage") or {},
                )
            finally:
                db.close()
        elif event_type == "error":
            if bool(event.payload.get("recoverable")):
                await self._send(
                    server_event(
                        event_type,
                        session_id=self.session_id,
                        event_id=event.event_id or None,
                        **event.payload,
                    )
                )
                return "reconnect"
            db = self.db_factory()
            try:
                mark_voice_error(
                    db,
                    session_id=self.session_id,
                    error_code=str(event.payload.get("code") or "provider_error"),
                )
            finally:
                db.close()
            self.close_reason = "provider_error"
            self._stop_event.set()
        elif event_type == "session.closed":
            self.close_reason = "provider_closed"
            self._stop_event.set()

        await self._send(
            server_event(
                event_type,
                session_id=self.session_id,
                event_id=event.event_id or None,
                **event.payload,
            )
        )
        return "stop" if self._stop_event.is_set() else "continue"

    async def _provider_reader(self) -> None:
        while not self._stop_event.is_set():
            reconnect_code = "provider_disconnected"
            try:
                async for event in self.provider.receive():
                    action = await self._handle_provider_event(event)
                    if action == "reconnect":
                        reconnect_code = str(
                            event.payload.get("code") or "provider_5xx"
                        )
                        break
                    if action == "stop":
                        return
                else:
                    if self._stop_event.is_set():
                        return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                reconnect_code = type(exc).__name__
                log_voice_event(
                    "provider_receive_error",
                    level=logging.WARNING,
                    voice_session_id=self.session_id,
                    user_id_hash=hash_user_id(self.user.id),
                    error_code=reconnect_code,
                )
            if not await self._attempt_provider_reconnect(reconnect_code):
                return

    async def _watchdog(self) -> None:
        started = time.monotonic()
        idle_limit = max(30, int(settings.REALTIME_VOICE_IDLE_CLOSE_SEC))
        max_duration = max(60, int(settings.REALTIME_VOICE_MAX_SESSION_SEC))
        while not self._stop_event.is_set():
            await asyncio.sleep(1)
            now = time.monotonic()
            if now - started >= max_duration:
                self.close_reason = "max_duration"
                self._stop_event.set()
            elif now - self._last_active_monotonic >= idle_limit:
                self.close_reason = "idle"
                self._stop_event.set()

    async def run(self) -> None:
        tasks: list[asyncio.Task] = []
        try:
            start_event = await self._first_event()
            await self._create_persistence()
            if self.tool_router is None:
                from app.realtime_voice.tools import ToolRouter

                self.tool_router = ToolRouter(
                    voice_session_id=self.session_id,
                    client_session_id=self.session_id,
                    user_id=self.user.id,
                    db_factory=self.db_factory,
                )
            await self._send_state("connecting")
            tools = self.tool_router.tool_definitions() if self.tool_router else []
            db = self.db_factory()
            try:
                config = build_provider_session_config(
                    db,
                    user=self.user,
                    voice=str(self.ticket_payload.get("voice") or ""),
                    resume_session_id=start_event.resume_session_id,
                    entry_mode=start_event.entry_mode,
                    tools=tools,
                )
                self._initial_context = config.initial_context
                self._provider_config = config
            finally:
                db.close()
            await self.provider.connect(config)
            voice_metrics.increment("session_started")
            log_voice_event(
                "session_started",
                voice_session_id=self.session_id,
                user_id_hash=hash_user_id(self.user.id),
                client_platform=str(self.ticket_payload.get("platform") or "h5"),
            )

            tasks = [
                asyncio.create_task(self._client_reader()),
                asyncio.create_task(self._provider_sender()),
                asyncio.create_task(self._provider_reader()),
                asyncio.create_task(self._watchdog()),
                asyncio.create_task(self._stop_event.wait()),
            ]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except ProtocolError as exc:
            await self._send(
                error_event(
                    session_id=self.session_id,
                    code=exc.code,
                    message=exc.message,
                    recoverable=exc.recoverable,
                )
            )
            self.close_reason = "protocol_error"
        except Exception as exc:
            await self._send(
                error_event(
                    session_id=self.session_id,
                    code="session_error",
                    message="实时语音会话未能继续",
                    recoverable=False,
                )
            )
            self.close_reason = "error"
            log_voice_event(
                "session_error",
                level=logging.ERROR,
                voice_session_id=self.session_id,
                user_id_hash=hash_user_id(self.user.id),
                error_code=type(exc).__name__,
            )
            db = self.db_factory()
            try:
                mark_voice_error(
                    db,
                    session_id=self.session_id,
                    error_code=type(exc).__name__,
                )
            finally:
                db.close()
        finally:
            self.state = "closing"
            with contextlib.suppress(Exception):
                await self.provider.close()
            for task in tasks:
                if not task.done():
                    task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            db = self.db_factory()
            try:
                await close_voice_session(
                    db,
                    session_id=self.session_id,
                    reason=self.close_reason,
                )
            finally:
                db.close()
            if not self._session_closed_sent:
                summary = {
                    "durationSec": max(
                        0,
                        int(time.monotonic() - self._started_monotonic),
                    ),
                    "memoryCount": self._memory_evidence_count,
                    "missionId": self._mission_id or None,
                }
                with contextlib.suppress(Exception):
                    await self._send(
                        server_event(
                            "session.closed",
                            session_id=self.session_id,
                            reason=self.close_reason,
                            summary=summary,
                        )
                    )
                self._session_closed_sent = True
            voice_metrics.increment("session_closed")
            if self.close_reason not in {"user", "idle", "max_duration"}:
                voice_metrics.increment("session_abnormal_close")
            log_voice_event(
                "session_closed",
                voice_session_id=self.session_id,
                user_id_hash=hash_user_id(self.user.id),
                close_reason=self.close_reason,
                duration_sec=max(
                    0,
                    int(time.monotonic() - self._started_monotonic),
                ),
                provider_log_id=self.provider.provider_log_id,
            )

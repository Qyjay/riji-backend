import asyncio
import json
import time

from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.models.realtime_voice import RealtimeToolCall, RealtimeVoiceSession
from app.models.user import User
from app.realtime_voice.fake_provider import FakeRealtimeVoiceProvider
from app.realtime_voice.registry import RealtimeSessionRegistry
from app.realtime_voice.session import RealtimeVoiceSessionRunner
from app.realtime_voice.tools import (
    ToolHandlerOutput,
    ToolRegistry,
    ToolRouter,
    ToolSpec,
)
from app.realtime_voice.policy import ToolRisk
from app.realtime_voice.provider import ProviderToolCall
from tests.conftest import TestingSessionLocal, create_test_user


class RecordingWebSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def test_session_registry_enforces_global_and_single_user_limit():
    registry = RealtimeSessionRegistry()
    assert registry.claim("user-a", "session-a", max_sessions=2) is True
    assert registry.claim("user-a", "session-other", max_sessions=2) is False
    assert registry.claim("user-b", "session-b", max_sessions=2) is True
    assert registry.claim("user-c", "session-c", max_sessions=2) is False
    registry.release("user-a", "wrong-session")
    assert registry.active_count == 2
    registry.release("user-a", "session-a")
    assert registry.claim("user-c", "session-c", max_sessions=2) is True


def test_input_audio_queue_warns_then_closes_on_sustained_overflow(monkeypatch):
    monkeypatch.setattr(settings, "REALTIME_VOICE_MAX_INPUT_FRAMES", 10)

    async def run():
        websocket = RecordingWebSocket()
        runner = RealtimeVoiceSessionRunner(
            websocket=websocket,
            user=User(id="voice-limit-user", username="voice_limit"),
            ticket_payload={"voice": "voice", "platform": "h5"},
            provider=FakeRealtimeVoiceProvider(),
            db_factory=TestingSessionLocal,
        )
        for index in range(13):
            await runner._enqueue_provider_action(
                kind="audio",
                payload="AAE=",
                event_id=f"audio-{index}",
            )
        return websocket, runner

    websocket, runner = asyncio.run(run())
    types = [event["type"] for event in websocket.events]
    assert types.count("client.slow_down") == 3
    assert types[-1] == "error"
    assert websocket.events[-1]["code"] == "client_backpressure"
    assert runner.close_reason == "client_backpressure"
    assert runner._stop_event.is_set()


def test_slow_tool_returns_timeout_and_updates_audit(client, db, monkeypatch):
    auth = create_test_user(client, username="voice_slow_tool")
    now = int(time.time() * 1000)
    db.add(
        RealtimeVoiceSession(
            id="voice-slow-session",
            user_id=auth["user"]["id"],
            status="active",
            started_at=now,
            last_active_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    registry = ToolRegistry()

    def slow_handler(*_args):
        time.sleep(1.05)
        return ToolHandlerOutput(data={"late": True})

    registry.register(
        ToolSpec(
            name="slow_read",
            description="慢查询",
            args_model=EmptyArgs,
            risk=ToolRisk.R0,
            handler=slow_handler,
        )
    )
    router = ToolRouter(
        voice_session_id="voice-slow-session",
        client_session_id="voice-slow-session",
        user_id=auth["user"]["id"],
        db_factory=TestingSessionLocal,
        registry=registry,
    )
    monkeypatch.setattr(settings, "REALTIME_VOICE_TOOL_TIMEOUT_SEC", 1)

    results, _ = asyncio.run(
        router.execute_calls(
            [ProviderToolCall("slow-call", "slow_read", "{}")]
        )
    )
    envelope = json.loads(results[0].output)
    assert envelope["ok"] is False
    assert "没有完成" in envelope["error"]
    db.expire_all()
    row = db.query(RealtimeToolCall).filter_by(provider_call_id="slow-call").one()
    assert row.status == "failed"
    assert row.error_message == "tool_timeout"

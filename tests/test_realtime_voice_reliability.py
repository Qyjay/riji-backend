import asyncio

from app.config import settings
from app.models.user import User
from app.realtime_voice.fake_provider import FakeRealtimeVoiceProvider
from app.realtime_voice.provider import ProviderEvent, ProviderSessionConfig
from app.realtime_voice.session import RealtimeVoiceSessionRunner
from tests.conftest import TestingSessionLocal


class RecordingWebSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


def _runner(provider):
    runner = RealtimeVoiceSessionRunner(
        websocket=RecordingWebSocket(),
        user=User(id="voice-reliable-user", username="voice_reliable"),
        ticket_payload={"voice": "voice", "platform": "h5"},
        provider=provider,
        db_factory=TestingSessionLocal,
    )
    runner._provider_config = ProviderSessionConfig(
        instructions="test",
        voice="voice",
    )
    return runner


def test_recoverable_provider_error_reconnects_without_replaying_audio(monkeypatch):
    monkeypatch.setattr(settings, "REALTIME_VOICE_MAX_RECONNECTS", 2)

    async def run():
        provider = FakeRealtimeVoiceProvider()
        provider.provider_session_id = "dialog-old"
        runner = _runner(provider)
        runner._provider_queue.put_nowait(("audio", "AAE=", "audio-old"))
        action = await runner._handle_provider_event(
            ProviderEvent(
                "error",
                payload={
                    "code": "503",
                    "message": "temporary",
                    "recoverable": True,
                },
            )
        )
        assert action == "reconnect"
        assert await runner._attempt_provider_reconnect("503") is True
        return provider, runner

    provider, runner = asyncio.run(run())
    assert provider.reconnect_count == 1
    assert runner._provider_queue.empty()
    assert runner._provider_config.resume_session_id == "dialog-old"
    assert "session.reconnecting" in {
        event["type"] for event in runner.websocket.events
    }


def test_nonrecoverable_provider_error_does_not_retry():
    async def run():
        provider = FakeRealtimeVoiceProvider()
        runner = _runner(provider)
        action = await runner._handle_provider_event(
            ProviderEvent(
                "error",
                payload={
                    "code": "401",
                    "message": "unauthorized",
                    "recoverable": False,
                },
            )
        )
        assert action == "stop"
        return provider, runner

    provider, runner = asyncio.run(run())
    assert provider.reconnect_count == 0
    assert runner.close_reason == "provider_error"
    assert runner._stop_event.is_set()


def test_provider_reconnect_exhaustion_stops_session(monkeypatch):
    monkeypatch.setattr(settings, "REALTIME_VOICE_MAX_RECONNECTS", 2)

    class FailingProvider(FakeRealtimeVoiceProvider):
        async def reconnect(self, config):
            self.reconnect_count += 1
            raise RuntimeError("still unavailable")

    async def run():
        provider = FailingProvider()
        runner = _runner(provider)
        assert await runner._attempt_provider_reconnect("503") is False
        return provider, runner

    provider, runner = asyncio.run(run())
    assert provider.reconnect_count == 2
    assert runner.close_reason == "provider_error"
    assert runner._stop_event.is_set()
    errors = [event for event in runner.websocket.events if event["type"] == "error"]
    assert errors[-1]["code"] == "provider_reconnect_failed"

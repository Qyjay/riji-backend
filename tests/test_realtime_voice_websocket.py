import base64

from app.config import settings
from app.models.chat import ChatMessage
from app.models.realtime_voice import RealtimeVoiceSession
from app.realtime_voice.fake_provider import FakeRealtimeVoiceProvider
from app.realtime_voice.provider import ProviderEvent
from app.realtime_voice.registry import session_registry
from app.realtime_voice.tickets import ticket_store
from tests.conftest import create_test_user, get_auth_header


def test_realtime_websocket_forwards_audio_transcript_and_closes(
    client,
    db,
    monkeypatch,
):
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_ENABLED", True)
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "REALTIME_VOICE_PROVIDER", "fake")
    monkeypatch.setattr(settings, "REALTIME_VOICE_IDLE_CLOSE_SEC", 60)
    ticket_store.reset()
    session_registry.reset()

    provider = FakeRealtimeVoiceProvider(
        [
            ProviderEvent("session.ready", payload={"providerSessionId": "dialog-test"}),
            ProviderEvent(
                "asr.done",
                event_id="asr-1",
                payload={"text": "你还记得晚霞吗", "itemId": "question-1"},
            ),
            ProviderEvent(
                "assistant.text.done",
                event_id="text-1",
                payload={"text": "我先帮你查找对应记录。", "itemId": "reply-1"},
            ),
            ProviderEvent(
                "assistant.audio.delta",
                payload={"audio": "AAE=", "sequence": 1},
            ),
            ProviderEvent("response.done", payload={"usage": {"total_tokens": 12}}),
        ]
    )
    monkeypatch.setattr(
        "app.realtime_voice.config.create_provider",
        lambda: provider,
    )
    auth = create_test_user(client, username="voice_socket")
    ticket_response = client.post(
        "/api/realtime-voice/tickets",
        json={},
        headers=get_auth_header(auth["token"]),
    )
    ticket = ticket_response.json()["data"]["ticket"]

    with client.websocket_connect(f"/ws/realtime-avatar?ticket={ticket}") as websocket:
        websocket.send_json(
            {
                "type": "session.start",
                "eventId": "start-1",
                "entryMode": "general",
            }
        )
        received = []
        for _ in range(4):
            event = websocket.receive_json()
            received.append(event)
            if event["type"] == "session.ready":
                break
        assert "session.ready" in {event["type"] for event in received}

        audio = base64.b64encode(b"\x00\x00" * 320).decode()
        websocket.send_json(
            {
                "type": "audio.append",
                "eventId": "audio-1",
                "audio": audio,
            }
        )

        for _ in range(12):
            event = websocket.receive_json()
            received.append(event)
            if event["type"] == "response.done":
                break
        assert "asr.done" in {event["type"] for event in received}
        assert "assistant.text.done" in {event["type"] for event in received}
        assert "assistant.audio.delta" in {event["type"] for event in received}

        websocket.send_json({"type": "session.close", "eventId": "close-1"})
        closed = None
        for _ in range(6):
            event = websocket.receive_json()
            if event["type"] == "session.closed":
                closed = event
                break
        assert closed is not None
        assert closed["reason"] == "user"

    assert provider.audio_events == [("audio-1", audio)]
    assert {tool.name for tool in provider.config.tools} == {
        "search_personal_memory",
        "get_memory_document",
        "draft_social_mission",
        "create_social_mission_draft",
        "start_social_mission",
        "list_social_missions",
        "get_social_mission_progress",
        "open_app_page",
    }
    voice_row = db.query(RealtimeVoiceSession).one()
    assert voice_row.status == "closed"
    assert voice_row.provider_session_id == "dialog-test"
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == auth["user"]["id"])
        .order_by(ChatMessage.timestamp)
        .all()
    )
    assert [message.content for message in messages] == [
        "你还记得晚霞吗",
        "我先帮你查找对应记录。",
    ]


def test_realtime_websocket_rejects_replayed_ticket(client, monkeypatch):
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_ENABLED", True)
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_API_KEY", "test-key")
    ticket_store.reset()
    session_registry.reset()
    auth = create_test_user(client, username="voice_replay")
    ticket = client.post(
        "/api/realtime-voice/tickets",
        json={},
        headers=get_auth_header(auth["token"]),
    ).json()["data"]["ticket"]

    provider = FakeRealtimeVoiceProvider()
    monkeypatch.setattr("app.realtime_voice.config.create_provider", lambda: provider)
    with client.websocket_connect(f"/ws/realtime-avatar?ticket={ticket}") as first:
        first.send_json({"type": "session.start", "eventId": "start"})
        first.send_json({"type": "session.close", "eventId": "close"})
        while first.receive_json()["type"] != "session.closed":
            pass

    with client.websocket_connect(f"/ws/realtime-avatar?ticket={ticket}") as replay:
        event = replay.receive_json()
        assert event["type"] == "error"
        assert event["code"] == "invalid_ticket"

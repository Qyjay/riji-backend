import base64

import pytest

from app.realtime_voice.protocol import (
    AudioAppendEvent,
    ProtocolError,
    error_event,
    parse_client_event,
    server_event,
)


def test_parse_audio_append_and_reject_unknown_fields():
    audio = base64.b64encode(b"\x00\x01" * 320).decode()
    event = parse_client_event(
        {"type": "audio.append", "eventId": "evt-1", "audio": audio},
        state="listening",
    )
    assert isinstance(event, AudioAppendEvent)
    assert event.event_id == "evt-1"

    with pytest.raises(ProtocolError, match="Extra inputs"):
        parse_client_event(
            {
                "type": "audio.append",
                "eventId": "evt-2",
                "audio": audio,
                "unexpected": True,
            },
            state="listening",
        )


def test_protocol_rejects_invalid_json_event_and_state():
    with pytest.raises(ProtocolError) as invalid_json:
        parse_client_event("{", state="listening")
    assert invalid_json.value.code == "invalid_json"

    with pytest.raises(ProtocolError) as unknown:
        parse_client_event(
            {"type": "system.delete_everything", "eventId": "evt-3"},
            state="listening",
        )
    assert unknown.value.code == "unknown_event"

    with pytest.raises(ProtocolError) as invalid_state:
        parse_client_event(
            {"type": "audio.commit", "eventId": "evt-4"},
            state="closed",
        )
    assert invalid_state.value.code == "invalid_state"
    assert invalid_state.value.recoverable is False


def test_server_event_has_stable_envelope():
    event = server_event("session.ready", session_id="voice-1", providerSessionId="p-1")
    assert event["type"] == "session.ready"
    assert event["sessionId"] == "voice-1"
    assert event["providerSessionId"] == "p-1"
    assert event["eventId"]
    assert event["timestamp"] > 0

    err = error_event(
        session_id="voice-1",
        code="invalid_state",
        message="状态错误",
        recoverable=True,
    )
    assert err["recoverable"] is True

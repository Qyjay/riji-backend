import json
import logging

from app.realtime_voice.observability import log_voice_event, safe_log_payload


def test_structured_voice_log_redacts_secrets_audio_and_private_content(caplog):
    payload = safe_log_payload(
        "tool.completed",
        voice_session_id="voice-1",
        api_key="secret-key",
        ticket="secret-ticket",
        audio="AAECAwQ=",
        arguments={
            "query": "晚霞",
            "content": "完整私密日记正文",
            "confirmationToken": "secret-confirmation",
        },
        latency_ms=42,
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["voice_session_id"] == "voice-1"
    assert payload["latency_ms"] == 42
    assert "secret-key" not in serialized
    assert "secret-ticket" not in serialized
    assert "AAECAwQ=" not in serialized
    assert "完整私密日记正文" not in serialized
    assert "secret-confirmation" not in serialized
    assert serialized.count("[REDACTED]") >= 5

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        log_voice_event(
            "session.ready",
            voice_session_id="voice-log",
            authorization="Bearer secret",
        )
    assert "voice-log" in caplog.text
    assert "Bearer secret" not in caplog.text


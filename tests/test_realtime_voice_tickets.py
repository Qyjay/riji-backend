import time

import pytest
from jose import jwt

from app.config import settings
from app.realtime_voice.tickets import VoiceTicketError, consume_ticket, ticket_store
from tests.conftest import create_test_user, get_auth_header


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_ENABLED", True)
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "REALTIME_VOICE_TICKET_TTL_SEC", 60)
    ticket_store.reset()


def test_ticket_requires_auth(client, monkeypatch):
    _enable(monkeypatch)
    response = client.post("/api/realtime-voice/tickets", json={})
    assert response.status_code == 401


def test_ticket_disabled_or_unconfigured(client, monkeypatch):
    user = create_test_user(client, username="voice_ticket_off")
    headers = get_auth_header(user["token"])
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_ENABLED", False)
    response = client.post("/api/realtime-voice/tickets", json={}, headers=headers)
    assert response.status_code == 503

    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_ENABLED", True)
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_API_KEY", "")
    response = client.post("/api/realtime-voice/tickets", json={}, headers=headers)
    assert response.status_code == 503


def test_ticket_can_only_be_consumed_once(client, monkeypatch):
    _enable(monkeypatch)
    user = create_test_user(client, username="voice_ticket_once")
    response = client.post(
        "/api/realtime-voice/tickets",
        json={"client_platform": "h5"},
        headers=get_auth_header(user["token"]),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    payload = consume_ticket(data["ticket"])
    assert payload["sub"] == user["user"]["id"]
    assert payload["aud"] == "realtime_voice"
    assert payload["input_format"] == "pcm_16k_s16le"
    with pytest.raises(VoiceTicketError, match="已使用"):
        consume_ticket(data["ticket"])


def test_ticket_rejects_invalid_audience_and_expired(monkeypatch):
    _enable(monkeypatch)
    now = int(time.time())
    invalid_aud = jwt.encode(
        {
            "sub": "user",
            "aud": "wrong",
            "jti": "jti-wrong",
            "iat": now,
            "exp": now + 60,
            "voice": "voice",
            "input_format": "pcm_16k_s16le",
            "output_format": "pcm_s16le",
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(VoiceTicketError, match="audience"):
        consume_ticket(invalid_aud)

    expired = jwt.encode(
        {
            "sub": "user",
            "aud": "realtime_voice",
            "jti": "jti-expired",
            "iat": now - 120,
            "exp": now - 60,
            "voice": "voice",
            "input_format": "pcm_16k_s16le",
            "output_format": "pcm_s16le",
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(VoiceTicketError, match="过期"):
        consume_ticket(expired)


def test_ticket_rejects_invalid_voice(client, monkeypatch):
    _enable(monkeypatch)
    user = create_test_user(client, username="voice_ticket_voice")
    response = client.post(
        "/api/realtime-voice/tickets",
        json={"voice": "bad voice with spaces"},
        headers=get_auth_header(user["token"]),
    )
    assert response.status_code == 400

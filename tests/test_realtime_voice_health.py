from app.config import settings
from app.realtime_voice.registry import session_registry


def test_realtime_voice_health_reports_feature_state(client, monkeypatch):
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_ENABLED", False)
    monkeypatch.setattr(settings, "VOLC_REALTIME_VOICE_API_KEY", "")
    monkeypatch.setattr(settings, "REALTIME_VOICE_MAX_GLOBAL_SESSIONS", 5)
    session_registry.reset()

    response = client.get("/api/realtime-voice/health")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["enabled"] is False
    assert data["configured"] is False
    assert data["provider"] == "volcengine_duplex"
    assert data["activeSessions"] == 0
    assert data["maxSessions"] == 5
    assert isinstance(data["metrics"], dict)
    assert "apiKey" not in response.text

"""
AI + 聊天模块测试
"""
import asyncio
from pathlib import Path

from tests.conftest import create_test_user, get_auth_header


def test_chat_returns_message_entities(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/chat", json={"message": "你好，请介绍一下自己"}, headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0

    data = payload["data"]
    assert "sessionId" in data
    assert data["userMessage"]["role"] == "user"
    assert data["assistantMessage"]["role"] == "assistant"
    assert data["userMessage"]["id"]
    assert data["assistantMessage"]["id"]
    assert data["userMessage"]["attachments"] == []


def test_chat_stream_supports_attachments(client):
    user_data = create_test_user(client, username="chat_stream_user")
    headers = get_auth_header(user_data["token"])

    chunks = []
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": "帮我看看这份资料",
            "clientMessageId": "cmsg_test_1",
            "attachments": [
                {
                    "type": "file",
                    "name": "notes.pdf",
                    "url": "/uploads/test/chat-file/notes.pdf",
                    "mimeType": "application/pdf",
                    "size": 1024,
                }
            ],
        },
        headers=headers,
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line:
                chunks.append(line)

    joined = "\n".join(chunks)
    assert '"type": "session"' in joined
    assert '"type": "ack"' in joined
    assert '"type": "done"' in joined
    assert '"clientMessageId": "cmsg_test_1"' in joined


def test_chat_history_returns_complete_messages(client):
    user_data = create_test_user(client, username="chat_history_user")
    headers = get_auth_header(user_data["token"])

    client.post(
        "/api/chat",
        json={
            "message": "你好",
            "clientMessageId": "history_msg_1",
            "attachments": [
                {
                    "type": "image",
                    "name": "sunset.jpg",
                    "url": "/uploads/test/diary-image/sunset.jpg",
                    "thumbnailUrl": "/uploads/test/diary-image/thumb_sunset.jpg",
                }
            ],
        },
        headers=headers,
    )

    resp = client.get("/api/chat/history?limit=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data and "total" in data
    assert data["total"] >= 2
    first_user = next(item for item in data["items"] if item["role"] == "user")
    assert first_user["id"]
    assert first_user["clientMessageId"] == "history_msg_1"
    assert first_user["sessionId"]
    assert isinstance(first_user["attachments"], list)
    assert first_user["attachments"][0]["type"] == "image"


def test_session_messages_returns_complete_messages(client):
    user_data = create_test_user(client, username="chat_session_user")
    headers = get_auth_header(user_data["token"])

    send_resp = client.post("/api/chat", json={"message": "今天天气不错"}, headers=headers)
    assert send_resp.status_code == 200
    session_id = send_resp.json()["data"]["sessionId"]

    resp = client.get(f"/api/chat/session/{session_id}/messages", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["session"]["id"] == session_id
    assert len(payload["messages"]) >= 2
    assert payload["messages"][0]["id"]


def test_fortune(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/ai/fortune", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    f = data["data"]
    assert "overall" in f
    assert "study" in f
    assert "social" in f
    assert "health" in f
    assert "tip" in f
    assert "luckyColor" in f
    assert "luckyNumber" in f


def test_tts(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/ai/tts", json={"text": "你好，这是测试语音"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], str)


def test_understand_image_text_with_local_upload_url(monkeypatch):
    from app.ai import service as ai_service

    monkeypatch.setattr(ai_service.settings, "ARK_VISION_ENABLED", True)
    monkeypatch.setattr(ai_service.settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(ai_service.settings, "ARK_VISION_TIMEOUT_SEC", 5)

    upload_root = Path(ai_service.settings.UPLOAD_DIR)
    image_path = upload_root / "test-user" / "diary-image" / "ark-local-path.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"fake-image-bytes")

    captured = {"image_input": ""}

    async def fake_call(image_input: str, _prompt: str):
        captured["image_input"] = image_input
        return {"output_text": "识别结果"}

    monkeypatch.setattr(ai_service, "_call_ark_vision_async", fake_call)

    result = asyncio.run(
        ai_service.understand_image_text(
            image_url="/uploads/test-user/diary-image/ark-local-path.jpg",
            prompt="请描述图片",
        )
    )

    assert result == "识别结果"
    expected_posix = image_path.resolve().as_posix()
    assert captured["image_input"].startswith("file://")
    assert captured["image_input"].endswith(expected_posix)

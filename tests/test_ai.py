"""
AI + 聊天模块测试
"""
import asyncio
from pathlib import Path

from tests.conftest import create_test_user, get_auth_header


def test_chat_returns_string(client):
    """POST /chat 返回纯文本 string"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/chat", json={"message": "你好，请介绍一下自己"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    # data 应该是 string
    assert isinstance(data["data"], str)


def test_chat_history(client):
    """GET /chat/history 返回 {items, total}"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    client.post("/api/chat", json={"message": "你好"}, headers=headers)

    resp = client.get("/api/chat/history?limit=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "items" in data["data"]
    assert "total" in data["data"]
    # 应该有 user 和 assistant 消息
    items = data["data"]["items"]
    roles = [m["role"] for m in items]
    assert "user" in roles
    assert "assistant" in roles


def test_fortune(client):
    """GET /ai/fortune 返回正确字段"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/ai/fortune", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    f = data["data"]
    # 验证所有运势字段（camelCase）
    assert "overall" in f
    assert "study" in f
    assert "social" in f
    assert "health" in f
    assert "tip" in f
    assert "luckyColor" in f
    assert "luckyNumber" in f


def test_tts(client):
    """POST /ai/tts 返回 URL string"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/ai/tts", json={"text": "你好，这是测试语音"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], str)


def test_understand_image_text_with_local_upload_url(monkeypatch):
    """当素材 URL 为 /uploads/... 时，Ark 调用应自动使用 file:// URI。"""
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

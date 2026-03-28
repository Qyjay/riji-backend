"""
AI + 聊天模块测试
"""
import pytest
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

"""
学习模块测试（番茄钟 + 待办）
"""
import pytest
from tests.conftest import create_test_user, get_auth_header


def test_create_pomodoro(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/study/pomodoros", json={
        "task": "背单词",
        "subject": "英语",
        "duration": 25,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    p = data["data"]
    # 验证 camelCase
    assert "createdAt" in p
    assert p["task"] == "背单词"
    assert p["duration"] == 25


def test_list_pomodoros_bare_array(client):
    """GET /study/pomodoros 返回裸数组"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    client.post("/api/study/pomodoros", json={"task": "任务1"}, headers=headers)
    client.post("/api/study/pomodoros", json={"task": "任务2"}, headers=headers)

    resp = client.get("/api/study/pomodoros", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 2


def test_complete_pomodoro(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/study/pomodoros", json={"task": "完成测试"}, headers=headers)
    pomo_id = create_resp.json()["data"]["id"]

    resp = client.post(f"/api/study/pomodoros/{pomo_id}/complete", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] is None


def test_create_todo(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/study/todos", json={
        "content": "完成作业",
        "priority": "high",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    t = data["data"]
    assert "createdAt" in t
    assert t["content"] == "完成作业"
    assert t["completed"] == False
    assert t["priority"] == "high"


def test_list_todos_bare_array(client):
    """GET /study/todos 返回裸数组"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    client.post("/api/study/todos", json={"content": "待办1"}, headers=headers)
    client.post("/api/study/todos", json={"content": "待办2"}, headers=headers)

    resp = client.get("/api/study/todos", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 2


def test_toggle_todo(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/study/todos", json={"content": "切换测试"}, headers=headers)
    todo_id = create_resp.json()["data"]["id"]

    # 切换为 True
    resp = client.post(f"/api/study/todos/{todo_id}/toggle", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["completed"] == True

    # 再次切换为 False
    resp2 = client.post(f"/api/study/todos/{todo_id}/toggle", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["completed"] == False

"""
纪念日模块测试
"""
import pytest
from tests.conftest import create_test_user, get_auth_header


def test_create_anniversary(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/anniversaries", json={
        "title": "认识小明",
        "date": "03-25",
        "year": 2024,
        "related_person": "小明",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    ann = data["data"]
    # 验证 camelCase
    assert "userId" in ann
    assert "relatedPerson" in ann
    assert "createdAt" in ann
    assert ann["title"] == "认识小明"


def test_list_anniversaries_bare_array(client):
    """GET /anniversaries 返回裸数组"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    client.post("/api/anniversaries", json={"title": "纪念日1", "date": "01-01"}, headers=headers)
    client.post("/api/anniversaries", json={"title": "纪念日2", "date": "06-01"}, headers=headers)

    resp = client.get("/api/anniversaries", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 2


def test_update_anniversary(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/anniversaries", json={"title": "原标题", "date": "03-25"}, headers=headers)
    ann_id = create_resp.json()["data"]["id"]

    resp = client.put(f"/api/anniversaries/{ann_id}", json={"title": "新标题"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "新标题"


def test_delete_anniversary(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/anniversaries", json={"title": "待删除", "date": "12-25"}, headers=headers)
    ann_id = create_resp.json()["data"]["id"]

    resp = client.delete(f"/api/anniversaries/{ann_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] is None


def test_today_anniversaries(client):
    """GET /anniversaries/today 返回 {today, on_this_day}（snake_case 外层 key）"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/anniversaries/today", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    result = data["data"]
    # 外层 key 是 snake_case（前端直接读 res.today 和 res.on_this_day）
    assert "today" in result
    assert "on_this_day" in result
    assert isinstance(result["today"], list)
    assert isinstance(result["on_this_day"], list)

"""
素材模块测试
"""
import pytest
from tests.conftest import create_test_user, get_auth_header


def test_create_material_text(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/materials", json={
        "type": "text",
        "content": "今天天气很好，心情愉快！",
        "date": "2026-03-25",
    }, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    m = data["data"]
    # 验证 camelCase 字段
    assert "userId" in m
    assert "mediaUrl" in m
    assert "thumbnailUrl" in m
    assert "createdAt" in m
    assert m["type"] == "text"
    assert m["content"] == "今天天气很好，心情愉快！"


def test_list_materials_bare_array(client):
    """GET /materials?date= 返回裸数组"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    # 创建 2 条素材
    for i in range(2):
        client.post("/api/materials", json={
            "type": "text",
            "content": f"素材 {i}",
            "date": "2026-03-25",
        }, headers=headers)

    resp = client.get("/api/materials?date=2026-03-25", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    # 应该是裸数组，不是 {items, total}
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 2


def test_get_material_detail(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "详情测试",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/materials/{material_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert resp.json()["data"]["id"] == material_id


def test_update_material(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "原始内容",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.put(f"/api/materials/{material_id}", json={
        "content": "更新后的内容",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "更新后的内容"


def test_delete_material(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "待删除",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.delete(f"/api/materials/{material_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] is None


def test_emotion_extraction(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "今天很开心，考试考得不错！",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.post(f"/api/materials/{material_id}/emotion", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "label" in data
    assert "score" in data
    assert "emoji" in data


def test_polish_text_returns_only_polished(client):
    """POST /materials/{id}/polish 只返回 {polished}"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "今天学习了很多东西",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.post(f"/api/materials/{material_id}/polish", json={
        "style": "文艺"
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "polished" in data
    # 不应该有 original 和 style
    assert "original" not in data
    assert "style" not in data


def test_material_no_auth(client):
    resp = client.get("/api/materials")
    assert resp.status_code == 401 or resp.json().get("code", 0) != 0

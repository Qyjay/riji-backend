"""
素材管理模块测试
- 测试素材 CRUD
- 测试情绪提取（mock 模式）
- 测试文字润色（mock 模式）
"""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_test_user, get_auth_header


def _create_material(client, headers, **kwargs) -> dict:
    """Helper: 创建一条素材"""
    data = {
        "type": "text",
        "content": "今天在图书馆看书，感觉很充实",
        "date": "2026-03-25",
    }
    data.update(kwargs)
    resp = client.post("/api/materials", json=data, headers=headers)
    assert resp.status_code == 200, f"创建素材失败: {resp.json()}"
    return resp.json()["data"]


class TestMaterialCRUD:
    """素材 CRUD 测试"""

    def test_create_material_text(self, client: TestClient):
        """创建文字素材"""
        auth = create_test_user(client, username="mat_user1")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/materials", json={
            "type": "text",
            "content": "今天去跑步了，很开心！",
            "date": "2026-03-25",
            "tags": ["运动", "健康"],
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        m = data["data"]
        assert m["type"] == "text"
        assert m["content"] == "今天去跑步了，很开心！"
        assert m["tags"] == ["运动", "健康"]
        assert m["date"] == "2026-03-25"
        assert "id" in m

    def test_create_material_image(self, client: TestClient):
        """创建图片素材"""
        auth = create_test_user(client, username="mat_user2")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/materials", json={
            "type": "image",
            "media_url": "https://example.com/photo.jpg",
            "content": "图书馆的阳光",
            "date": "2026-03-25",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "image"
        assert data["media_url"] == "https://example.com/photo.jpg"

    def test_list_materials_by_date(self, client: TestClient):
        """按日期查询素材"""
        auth = create_test_user(client, username="mat_user3")
        headers = get_auth_header(auth["token"])

        # 创建两条不同日期素材
        _create_material(client, headers, date="2026-03-25", content="今天")
        _create_material(client, headers, date="2026-03-24", content="昨天")

        # 按日期过滤
        resp = client.get("/api/materials?date=2026-03-25", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["date"] == "2026-03-25"

    def test_list_materials_all(self, client: TestClient):
        """不传 date 返回全部"""
        auth = create_test_user(client, username="mat_user4")
        headers = get_auth_header(auth["token"])

        _create_material(client, headers, date="2026-03-25")
        _create_material(client, headers, date="2026-03-24")

        resp = client.get("/api/materials", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2

    def test_get_material_detail(self, client: TestClient):
        """获取素材详情"""
        auth = create_test_user(client, username="mat_user5")
        headers = get_auth_header(auth["token"])

        m = _create_material(client, headers)
        resp = client.get(f"/api/materials/{m['id']}", headers=headers)
        assert resp.status_code == 200
        detail = resp.json()["data"]
        assert detail["id"] == m["id"]

    def test_update_material(self, client: TestClient):
        """更新素材"""
        auth = create_test_user(client, username="mat_user6")
        headers = get_auth_header(auth["token"])

        m = _create_material(client, headers)
        resp = client.put(f"/api/materials/{m['id']}", json={
            "content": "修改后的内容",
            "tags": ["更新", "测试"],
        }, headers=headers)
        assert resp.status_code == 200
        updated = resp.json()["data"]
        assert updated["content"] == "修改后的内容"
        assert updated["tags"] == ["更新", "测试"]

    def test_delete_material(self, client: TestClient):
        """删除素材"""
        auth = create_test_user(client, username="mat_user7")
        headers = get_auth_header(auth["token"])

        m = _create_material(client, headers)
        resp = client.delete(f"/api/materials/{m['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # 再次获取应 404
        resp2 = client.get(f"/api/materials/{m['id']}", headers=headers)
        assert resp2.status_code == 404

    def test_get_nonexistent_material(self, client: TestClient):
        """获取不存在的素材"""
        auth = create_test_user(client, username="mat_user8")
        headers = get_auth_header(auth["token"])

        resp = client.get("/api/materials/nonexistent-id", headers=headers)
        assert resp.status_code == 404

    def test_material_isolation(self, client: TestClient):
        """用户间素材隔离"""
        auth_a = create_test_user(client, username="mat_isol_a")
        auth_b = create_test_user(client, username="mat_isol_b")
        headers_a = get_auth_header(auth_a["token"])
        headers_b = get_auth_header(auth_b["token"])

        m = _create_material(client, headers_a)

        # 用户 B 无法访问用户 A 的素材
        resp = client.get(f"/api/materials/{m['id']}", headers=headers_b)
        assert resp.status_code == 404


class TestMaterialAI:
    """素材 AI 功能测试（Mock 模式）"""

    def test_emotion_extraction(self, client: TestClient):
        """情绪提取（mock 模式）"""
        auth = create_test_user(client, username="mat_ai_user1")
        headers = get_auth_header(auth["token"])

        m = _create_material(client, headers, content="今天超级开心，考试考了满分！")
        resp = client.post(f"/api/materials/{m['id']}/emotion", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "label" in data
        assert "score" in data
        assert "emoji" in data
        assert 0.0 <= data["score"] <= 1.0

    def test_text_polish(self, client: TestClient):
        """文字润色（mock 模式）"""
        auth = create_test_user(client, username="mat_ai_user2")
        headers = get_auth_header(auth["token"])

        m = _create_material(client, headers, content="今天吃了饭")
        resp = client.post(f"/api/materials/{m['id']}/polish", json={"style": "文艺"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "original" in data
        assert "polished" in data
        assert data["style"] == "文艺"
        assert len(data["polished"]) > 0

    def test_polish_different_styles(self, client: TestClient):
        """多种润色风格"""
        auth = create_test_user(client, username="mat_ai_user3")
        headers = get_auth_header(auth["token"])

        m = _create_material(client, headers, content="今天散步")
        for style in ["文艺", "幽默", "简洁", "温暖"]:
            resp = client.post(f"/api/materials/{m['id']}/polish", json={"style": style}, headers=headers)
            assert resp.status_code == 200
            assert resp.json()["data"]["style"] == style

    def test_no_auth_returns_401(self, client: TestClient):
        """未认证返回 401"""
        resp = client.get("/api/materials")
        assert resp.status_code == 401

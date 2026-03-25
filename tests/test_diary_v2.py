"""
日记 v2 模块测试
- 测试日记生成
- 测试修改次数限制
- 测试情绪趋势查询
"""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_test_user, get_auth_header


def _create_user_with_material(client, username):
    """Helper: 创建用户并添加素材"""
    auth = create_test_user(client, username=username)
    headers = get_auth_header(auth["token"])

    # 创建当天素材
    resp = client.post("/api/materials", json={
        "type": "text",
        "content": "早上去图书馆读书，收获满满",
        "date": "2026-03-25",
        "emotion": {"label": "开心", "score": 0.85, "emoji": "😊"},
    }, headers=headers)
    assert resp.status_code == 200

    return auth, headers


class TestDiaryGeneration:
    """日记 AI 生成测试"""

    def test_generate_diary(self, client: TestClient):
        """AI 生成日记"""
        auth, headers = _create_user_with_material(client, "diary_gen1")

        resp = client.post("/api/diaries/generate", json={
            "date": "2026-03-25",
            "weather": "晴",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "id" in data
        assert "content" in data
        assert len(data["content"]) > 0
        assert data["date"] == "2026-03-25"
        assert data["status"] == "draft"

    def test_generate_diary_no_materials(self, client: TestClient):
        """无素材时也能生成日记（AI 发挥）"""
        auth = create_test_user(client, username="diary_gen2")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/diaries/generate", json={
            "date": "2026-01-01",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["content"]) > 0

    def test_generate_diary_increments_count(self, client: TestClient):
        """生成日记后，用户日记数量+1"""
        auth, headers = _create_user_with_material(client, "diary_gen3")

        client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        resp = client.get("/api/diaries", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 1


class TestDiaryList:
    """日记列表测试"""

    def test_list_diaries_empty(self, client: TestClient):
        """空列表"""
        auth = create_test_user(client, username="diary_list1")
        headers = get_auth_header(auth["token"])

        resp = client.get("/api/diaries", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_diaries_pagination(self, client: TestClient):
        """分页查询"""
        auth = create_test_user(client, username="diary_list2")
        headers = get_auth_header(auth["token"])

        # 生成多篇日记
        for i in range(3):
            client.post("/api/diaries/generate", json={"date": f"2026-03-{25 - i:02d}"}, headers=headers)

        resp = client.get("/api/diaries?page=1&pageSize=2", headers=headers)
        data = resp.json()["data"]
        assert data["total"] == 3
        assert len(data["items"]) == 2


class TestDiaryUpdate:
    """日记修改次数限制测试"""

    def test_update_diary_success(self, client: TestClient):
        """正常修改日记"""
        auth, headers = _create_user_with_material(client, "diary_upd1")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        diary_id = gen_resp.json()["data"]["id"]

        resp = client.put(f"/api/diaries/{diary_id}", json={"content": "修改后的内容"}, headers=headers)
        assert resp.status_code == 200
        updated = resp.json()["data"]
        assert updated["content"] == "修改后的内容"
        assert updated["edit_count"] == 1

    def test_update_diary_edit_limit(self, client: TestClient):
        """修改次数达到上限后返回错误"""
        auth, headers = _create_user_with_material(client, "diary_upd2")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        diary_id = gen_resp.json()["data"]["id"]

        # 修改 max_edits 次（默认 3）
        for i in range(3):
            resp = client.put(f"/api/diaries/{diary_id}", json={"content": f"第{i+1}次修改"}, headers=headers)
            assert resp.status_code == 200

        # 第 4 次应该失败
        resp = client.put(f"/api/diaries/{diary_id}", json={"content": "第4次修改"}, headers=headers)
        assert resp.status_code == 400
        assert resp.json()["code"] != 0

    def test_update_nonexistent_diary(self, client: TestClient):
        """修改不存在的日记"""
        auth = create_test_user(client, username="diary_upd3")
        headers = get_auth_header(auth["token"])

        resp = client.put("/api/diaries/nonexistent-id", json={"content": "修改"}, headers=headers)
        assert resp.status_code == 404


class TestDiaryEmotionTrend:
    """情绪趋势测试"""

    def test_emotion_trend_no_materials(self, client: TestClient):
        """无关联素材时情绪趋势为空"""
        auth, headers = _create_user_with_material(client, "diary_emo1")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        diary_id = gen_resp.json()["data"]["id"]

        resp = client.get(f"/api/diaries/{diary_id}/emotion-trend", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "trend" in data
        assert "dominant" in data

    def test_emotion_trend_with_materials(self, client: TestClient):
        """有关联素材时返回情绪趋势"""
        auth = create_test_user(client, username="diary_emo2")
        headers = get_auth_header(auth["token"])

        # 创建带情绪的素材
        for _ in range(2):
            client.post("/api/materials", json={
                "type": "text",
                "content": "开心的事",
                "date": "2026-03-25",
                "emotion": {"label": "开心", "score": 0.9, "emoji": "😊"},
            }, headers=headers)

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        diary_id = gen_resp.json()["data"]["id"]

        resp = client.get(f"/api/diaries/{diary_id}/emotion-trend", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dominant"] == "开心"
        assert len(data["trend"]) == 2


class TestDiaryAI:
    """日记 AI 功能测试"""

    def test_extract_diary_info(self, client: TestClient):
        """AI 提取日记信息（mock 模式）"""
        auth, headers = _create_user_with_material(client, "diary_ai1")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        diary_id = gen_resp.json()["data"]["id"]

        resp = client.post(f"/api/diaries/{diary_id}/extract", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "anniversaries" in data
        assert "persons" in data
        assert "preferences" in data

    def test_generate_derivative_share_card(self, client: TestClient):
        """生成分享卡衍生内容"""
        auth, headers = _create_user_with_material(client, "diary_ai2")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        diary_id = gen_resp.json()["data"]["id"]

        resp = client.post(f"/api/diaries/{diary_id}/derivative", json={"type": "share_card"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "share_card"
        assert "content" in data
        assert data["share_scope"] == "private"

"""
日记 v2 模块测试
- 测试日记生成
- 测试修改次数限制
- 测试情绪趋势查询
"""
import asyncio
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.ai import minimax_client
from app.diary.service import DIARY_MAX_EDITS
from app.models.anniversary import Anniversary
from app.models.diary import Diary
from app.models.derivative import DiaryDerivative
from app.models.user_profile import UserProfile
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
        assert data["editCount"] == 0
        assert data["maxEdits"] == DIARY_MAX_EDITS

    def test_generate_diary_no_materials(self, client: TestClient):
        """无素材时默认提示先记录素材"""
        auth = create_test_user(client, username="diary_gen2")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/diaries/generate", json={
            "date": "2026-01-01",
        }, headers=headers)
        assert resp.status_code == 400
        body = resp.json()
        assert body.get("code", 0) != 0
        assert "素材" in body.get("message", "")

    def test_generate_diary_no_materials_with_fallback(self, client: TestClient):
        """无素材时允许通过 allow_fallback 走兜底生成"""
        auth = create_test_user(client, username="diary_gen5")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/diaries/generate", json={
            "date": "2026-01-02",
            "allow_fallback": True,
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["content"]) > 0
        assert data["editCount"] == 0
        assert data["maxEdits"] == DIARY_MAX_EDITS

    def test_generate_diary_increments_count(self, client: TestClient):
        """生成日记后，用户日记数量+1"""
        auth, headers = _create_user_with_material(client, "diary_gen3")

        client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        resp = client.get("/api/diaries", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 1

    def test_generate_diary_same_day_returns_existing(self, client: TestClient):
        """同一天重复生成：应返回已有日记，不新增第二篇，也不覆盖内容"""
        auth, headers = _create_user_with_material(client, "diary_gen4")

        first_resp = client.post(
            "/api/diaries/generate",
            json={"date": "2026-03-25", "weather": "晴"},
            headers=headers,
        )
        assert first_resp.status_code == 200
        first_data = first_resp.json()["data"]
        first_id = first_data["id"]

        # 补一条同日素材，二次生成应直接返回已有日记。
        add_mat_resp = client.post("/api/materials", json={
            "type": "text",
            "content": "晚上和同学一起散步",
            "date": "2026-03-25",
        }, headers=headers)
        assert add_mat_resp.status_code == 200

        second_resp = client.post(
            "/api/diaries/generate",
            json={"date": "2026-03-25", "weather": "阴"},
            headers=headers,
        )
        assert second_resp.status_code == 200
        second_data = second_resp.json()["data"]

        assert second_data["id"] == first_id
        assert second_data["weather"] == "晴"
        assert second_data["editCount"] == 0
        assert second_data["maxEdits"] == DIARY_MAX_EDITS

        # 列表总数保持 1，说明没有新增第二篇。
        list_resp = client.get("/api/diaries", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["data"]["total"] == 1

    def test_generate_diary_normalizes_weather_without_temperature(self, client: TestClient):
        """生成日记时应仅保存天气，不保存温度。"""
        auth, headers = _create_user_with_material(client, "diary_gen_weather")

        resp = client.post(
            "/api/diaries/generate",
            json={"date": "2026-03-25", "weather": "多云 18℃"},
            headers=headers,
        )
        assert resp.status_code == 200

        data = resp.json()["data"]
        assert data["weather"] == "多云"

        search_resp = client.get("/api/diaries/search?weather=多云", headers=headers)
        assert search_resp.status_code == 200
        assert search_resp.json()["data"]["total"] == 1

    def test_generate_diary_material_ids_emotion_summary_db_roundtrip(self, client: TestClient, db):
        """material_ids/emotion_summary 应在 DB 以 JSON string 存储，API 返回反序列化结构。"""
        auth, headers = _create_user_with_material(client, "diary_gen_json")

        resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        diary_id = data["id"]

        # API 层应返回反序列化后的 list/dict
        assert isinstance(data["materialIds"], list)
        assert isinstance(data["emotionSummary"], dict)

        # DB 层应存 JSON 字符串
        d = db.query(Diary).filter(Diary.id == diary_id).first()
        assert d is not None
        assert isinstance(d.material_ids, str)
        assert isinstance(d.emotion_summary, str)
        assert json.loads(d.material_ids) == data["materialIds"]
        assert json.loads(d.emotion_summary) == data["emotionSummary"]

        # 详情接口再次读取时应保持结构一致
        detail_resp = client.get(f"/api/diaries/{diary_id}", headers=headers)
        assert detail_resp.status_code == 200
        detail = detail_resp.json()["data"]
        assert detail["materialIds"] == data["materialIds"]
        assert detail["emotionSummary"] == data["emotionSummary"]

    def test_auto_generate_missing_diaries_creates_for_user_with_material(self, client: TestClient, db):
        """22 点自动任务：有素材且未手动生成时应自动补生成。"""
        auth, headers = _create_user_with_material(client, "diary_auto_gen1")

        from app.diary import service as diary_service

        result = asyncio.run(
            diary_service.auto_generate_missing_diaries(db, "2026-03-25")
        )

        assert result["candidate_count"] == 1
        assert result["generated_count"] == 1
        assert result["skipped_existing_count"] == 0
        assert result["failed"] == []

        list_resp = client.get("/api/diaries", headers=headers)
        assert list_resp.status_code == 200
        data = list_resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["date"] == "2026-03-25"

    def test_auto_generate_missing_diaries_skips_existing_manual_diary(self, client: TestClient, db):
        """22 点自动任务：当天已有手动生成日记时应跳过。"""
        auth, headers = _create_user_with_material(client, "diary_auto_gen2")

        manual_resp = client.post(
            "/api/diaries/generate",
            json={"date": "2026-03-25", "weather": "晴"},
            headers=headers,
        )
        assert manual_resp.status_code == 200

        from app.diary import service as diary_service

        result = asyncio.run(
            diary_service.auto_generate_missing_diaries(db, "2026-03-25")
        )

        assert result["candidate_count"] == 1
        assert result["generated_count"] == 0
        assert result["skipped_existing_count"] == 1
        assert result["failed"] == []

        list_resp = client.get("/api/diaries", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["data"]["total"] == 1

    def test_generate_diary_populates_images_and_tags(self, client: TestClient, monkeypatch):
        """生成日记时：images=当日图片URL；tags=素材标签+AI标签（去重合并）。"""
        auth = create_test_user(client, username="diary_gen_assets")
        headers = get_auth_header(auth["token"])

        resp1 = client.post("/api/materials", json={
            "type": "image",
            "content": "图书馆窗外晚霞",
            "media_url": "https://example.com/img1.jpg",
            "tags": ["校园", "晚霞"],
            "emotion": {"label": "开心", "score": 0.85, "emoji": "😊"},
            "date": "2026-03-25",
        }, headers=headers)
        assert resp1.status_code == 200

        resp2 = client.post("/api/materials", json={
            "type": "image",
            "content": "操场黄昏",
            "media_url": "https://example.com/img2.jpg",
            "tags": ["运动", "校园"],
            "emotion": {"label": "平静", "score": 0.75, "emoji": "😌"},
            "date": "2026-03-25",
        }, headers=headers)
        assert resp2.status_code == 200

        resp3 = client.post("/api/materials", json={
            "type": "text",
            "content": "今天复习了算法和操作系统",
            "tags": ["学习"],
            "emotion": {"label": "专注", "score": 0.8, "emoji": "🧠"},
            "date": "2026-03-25",
        }, headers=headers)
        assert resp3.status_code == 200

        class FakeMiniMaxClient:
            async def generate_diary(self, *args, **kwargs):
                return {
                    "title": "测试标题",
                    "content": "测试正文",
                    "emotion_summary": {
                        "dominant": "平静",
                        "distribution": {"平静": 1.0},
                    },
                    "ai_tags": ["成长", "回忆"],
                }

        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

        gen_resp = client.post("/api/diaries/generate", json={
            "date": "2026-03-25",
            "weather": "晴",
        }, headers=headers)
        assert gen_resp.status_code == 200
        data = gen_resp.json()["data"]

        assert data["images"] == [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
        ]
        for tag in ["校园", "晚霞", "运动", "学习", "成长", "回忆"]:
            assert tag in data["tags"]

    def test_generate_diary_image_understand_enabled_uses_cache(self, client: TestClient, monkeypatch):
        """图片理解开启后：首轮识别、次轮命中缓存，避免重复识别。"""
        auth = create_test_user(client, username="img_understand_c")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/materials", json={
            "type": "image",
            "content": "",
            "media_url": ["https://example.com/understand-cache.jpg"],
            "date": "2026-03-25",
        }, headers=headers)
        assert resp.status_code == 200

        from app.diary import service as diary_service
        from app.ai import service as ai_service
        ai_service.clear_image_understand_cache()

        calls = {"count": 0}

        async def fake_understand_image_text(image_url: str, prompt: str = "", timeout_sec: int = 20):
            calls["count"] += 1
            return "图书馆窗边晚霞"

        monkeypatch.setattr(ai_service, "understand_image_text", fake_understand_image_text)

        class FakeMiniMaxClient:
            def __init__(self):
                self.last_materials_text = ""

            async def generate_diary(self, materials_text: str, **kwargs):
                self.last_materials_text = materials_text
                return {
                    "title": "测试标题",
                    "content": "测试正文",
                    "emotion_summary": {"dominant": "平静", "distribution": {"平静": 1.0}},
                    "ai_tags": ["测试标签"],
                }

        fake_client = FakeMiniMaxClient()
        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: fake_client)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_ENABLED", True)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_MAX_IMAGES", 3)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_CACHE_TTL_SEC", 3600)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_PROMPT", "请描述图片")

        first_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        second_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)

        assert first_resp.status_code == 200
        assert second_resp.status_code == 200
        assert calls["count"] == 1
        assert "图书馆窗边晚霞" in fake_client.last_materials_text
        first_data = first_resp.json()["data"]
        assert "imageUnderstandings" in first_data
        assert isinstance(first_data["imageUnderstandings"], list)
        assert "图书馆窗边晚霞" in first_data["imageUnderstandings"]

    def test_generate_diary_image_understand_merges_when_content_exists(self, client: TestClient, monkeypatch):
        """图片素材已有 content 时，也应补充图片理解结果。"""
        auth = create_test_user(client, username="img_understand_m")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/materials", json={
            "type": "image",
            "content": "操场上有人在跑步",
            "media_url": ["https://example.com/understand-merge.jpg"],
            "date": "2026-03-25",
        }, headers=headers)
        assert resp.status_code == 200

        from app.diary import service as diary_service
        from app.ai import service as ai_service
        ai_service.clear_image_understand_cache()

        calls = {"count": 0}

        async def fake_understand_image_text(image_url: str, prompt: str = "", timeout_sec: int = 20):
            calls["count"] += 1
            return "夕阳下学生在跑道冲刺"

        monkeypatch.setattr(ai_service, "understand_image_text", fake_understand_image_text)

        class FakeMiniMaxClient:
            def __init__(self):
                self.last_materials_text = ""

            async def generate_diary(self, materials_text: str, **kwargs):
                self.last_materials_text = materials_text
                return {
                    "title": "测试标题",
                    "content": "测试正文",
                    "emotion_summary": {"dominant": "平静", "distribution": {"平静": 1.0}},
                    "ai_tags": ["测试标签"],
                }

        fake_client = FakeMiniMaxClient()
        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: fake_client)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_ENABLED", True)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_MAX_IMAGES", 3)

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        assert calls["count"] == 1
        assert "操场上有人在跑步" in fake_client.last_materials_text
        assert "夕阳下学生在跑道冲刺" in fake_client.last_materials_text

    def test_generate_diary_image_understand_failure_fallback(self, client: TestClient, monkeypatch):
        """图片理解失败时应降级，不影响日记生成主流程。"""
        auth = create_test_user(client, username="img_understand_f")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/materials", json={
            "type": "image",
            "content": "",
            "media_url": ["https://example.com/understand-fail.jpg"],
            "date": "2026-03-25",
        }, headers=headers)
        assert resp.status_code == 200

        from app.diary import service as diary_service
        from app.ai import service as ai_service
        ai_service.clear_image_understand_cache()

        async def fake_understand_image_text(image_url: str, prompt: str = "", timeout_sec: int = 20):
            raise RuntimeError("ark unavailable")

        monkeypatch.setattr(ai_service, "understand_image_text", fake_understand_image_text)

        class FakeMiniMaxClient:
            async def generate_diary(self, materials_text: str, **kwargs):
                return {
                    "title": "降级标题",
                    "content": "即使图片识别失败也可以生成",
                    "emotion_summary": {"dominant": "平静", "distribution": {"平静": 1.0}},
                    "ai_tags": ["降级"],
                }

        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_ENABLED", True)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_MAX_IMAGES", 3)

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        data = gen_resp.json()["data"]
        assert data["title"] == "降级标题"

    def test_generate_diary_image_understand_returns_per_image_result(self, client: TestClient, monkeypatch):
        """同一条 image 素材含多张图时，应返回按图片数量的理解结果。"""
        auth = create_test_user(client, username="img_understand_n")
        headers = get_auth_header(auth["token"])

        image_urls = [
            "https://example.com/multi-a.jpg",
            "https://example.com/multi-b.jpg",
        ]

        resp = client.post("/api/materials", json={
            "type": "image",
            "content": "",
            "media_url": image_urls,
            "date": "2026-03-25",
        }, headers=headers)
        assert resp.status_code == 200

        from app.diary import service as diary_service
        from app.ai import service as ai_service
        ai_service.clear_image_understand_cache()

        calls = []

        async def fake_understand_image_text(image_url: str, prompt: str = "", timeout_sec: int = 20):
            calls.append(image_url)
            if image_url.endswith("multi-a.jpg"):
                return "识图结果A"
            if image_url.endswith("multi-b.jpg"):
                return "识图结果B"
            return ""

        monkeypatch.setattr(ai_service, "understand_image_text", fake_understand_image_text)

        class FakeMiniMaxClient:
            def __init__(self):
                self.last_materials_text = ""

            async def generate_diary(self, materials_text: str, **kwargs):
                self.last_materials_text = materials_text
                return {
                    "title": "测试标题",
                    "content": "测试正文",
                    "emotion_summary": {"dominant": "平静", "distribution": {"平静": 1.0}},
                    "ai_tags": ["测试标签"],
                }

        fake_client = FakeMiniMaxClient()
        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: fake_client)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_ENABLED", True)
        monkeypatch.setattr(diary_service.settings, "ARK_VISION_MAX_IMAGES", 10)

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200

        data = gen_resp.json()["data"]
        assert calls == image_urls
        assert data["imageUnderstandings"] == ["识图结果A", "识图结果B"]
        assert "识图结果A" in fake_client.last_materials_text
        assert "识图结果B" in fake_client.last_materials_text

        search_resp = client.get(
            "/api/diaries/search?from=2026-03-25&to=2026-03-25",
            headers=headers,
        )
        assert search_resp.status_code == 200
        search_items = search_resp.json()["data"]["items"]
        assert len(search_items) == 1
        assert search_items[0]["imageUnderstandings"] == ["识图结果A", "识图结果B"]


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
            client.post(
                "/api/diaries/generate",
                json={"date": f"2026-03-{25 - i:02d}", "allow_fallback": True},
                headers=headers,
            )

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
        assert updated["editCount"] == 1

    def test_update_diary_edit_limit(self, client: TestClient):
        """修改次数达到上限后返回错误"""
        auth, headers = _create_user_with_material(client, "diary_upd2")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        diary_id = gen_resp.json()["data"]["id"]

        # 修改 max_edits 次
        for i in range(DIARY_MAX_EDITS):
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


class TestDiaryNotFound:
    """不存在 diary_id 的接口行为测试"""

    def test_get_nonexistent_diary(self, client: TestClient):
        auth = create_test_user(client, username="diary_nf_get")
        headers = get_auth_header(auth["token"])

        resp = client.get("/api/diaries/nonexistent-id", headers=headers)
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 40202
        assert "日记不存在" in body["message"]

    def test_extract_nonexistent_diary(self, client: TestClient):
        auth = create_test_user(client, username="diary_nf_extract")
        headers = get_auth_header(auth["token"])

        resp = client.post("/api/diaries/nonexistent-id/extract", headers=headers)
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 40202
        assert "日记不存在" in body["message"]

    def test_generate_derivative_nonexistent_diary(self, client: TestClient):
        auth = create_test_user(client, username="diary_nf_der")
        headers = get_auth_header(auth["token"])

        resp = client.post(
            "/api/diaries/nonexistent-id/derivative",
            json={"type": "share_card"},
            headers=headers,
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 40202
        assert "日记不存在" in body["message"]


class TestDiaryEmotionTrend:
    """情绪趋势测试"""

    def test_emotion_trend_no_materials(self, client: TestClient):
        """无关联素材时情绪趋势为空"""
        auth = create_test_user(client, username="diary_emo1")
        headers = get_auth_header(auth["token"])

        gen_resp = client.post(
            "/api/diaries/generate",
            json={"date": "2026-03-25", "allow_fallback": True},
            headers=headers,
        )
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        resp = client.get(f"/api/diaries/{diary_id}/emotion-trend", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dominant"] == ""
        assert data["trend"] == []

    def test_emotion_trend_with_materials(self, client: TestClient):
        """有关联素材时返回情绪趋势，并校验时间格式"""
        auth = create_test_user(client, username="diary_emo2")
        headers = get_auth_header(auth["token"])

        # 创建带情绪的素材；同一分钟内多条素材只保留最早一条
        for idx in range(2):
            client.post("/api/materials", json={
                "type": "text",
                "content": f"开心的事{idx + 1}",
                "date": "2026-03-25",
                "emotion": {"label": "开心", "score": 8, "emoji": "😊"},
            }, headers=headers)

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        diary_id = gen_resp.json()["data"]["id"]

        resp = client.get(f"/api/diaries/{diary_id}/emotion-trend", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dominant"] == "开心"
        assert len(data["trend"]) == 1

        # 时间格式校验：趋势精确到分钟，分数为 -10~10，趋势按时间非降序
        times = []
        for item in data["trend"]:
            assert isinstance(item["hour"], int)
            assert 0 <= item["hour"] <= 23
            assert isinstance(item["minute"], int)
            assert 0 <= item["minute"] <= 59
            assert isinstance(item["time"], str)
            assert len(item["time"]) == 5
            assert isinstance(item["label"], str) and item["label"]
            assert isinstance(item["score"], int)
            assert -10 <= item["score"] <= 10
            times.append(item["time"])

        assert times == sorted(times)

    def test_emotion_trend_all_materials_without_label(self, client: TestClient):
        """所有素材都没有 emotion.label 时，趋势应为空"""
        auth = create_test_user(client, username="diary_emo3")
        headers = get_auth_header(auth["token"])

        # 使用非空 emotion 对象但不带 label，且 content 为空以避免创建时触发自动情绪提取
        for _ in range(2):
            resp = client.post("/api/materials", json={
                "type": "text",
                "content": "",
                "date": "2026-03-25",
                "emotion": {"score": 0.3, "emoji": "😶"},
            }, headers=headers)
            assert resp.status_code == 200

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        trend_resp = client.get(f"/api/diaries/{diary_id}/emotion-trend", headers=headers)
        assert trend_resp.status_code == 200
        trend_data = trend_resp.json()["data"]
        assert trend_data["dominant"] == ""
        assert trend_data["trend"] == []

    def test_emotion_trend_mixed_materials_only_keep_labeled(self, client: TestClient):
        """混合素材中仅保留带 emotion.label 的记录进入趋势"""
        auth = create_test_user(client, username="diary_emo4")
        headers = get_auth_header(auth["token"])

        # 有效情绪素材：兼容旧版 0~1 置信分，按情绪类型映射为 -10~10 好坏分
        valid_resp = client.post("/api/materials", json={
            "type": "text",
            "content": "开心的事",
            "date": "2026-03-25",
            "emotion": {"label": "开心", "score": 0.9, "emoji": "😊"},
        }, headers=headers)
        assert valid_resp.status_code == 200

        # 无效情绪素材：无 label，不应进入 trend
        invalid_resp = client.post("/api/materials", json={
            "type": "text",
            "content": "",
            "date": "2026-03-25",
            "emotion": {"score": 0.2, "emoji": "😶"},
        }, headers=headers)
        assert invalid_resp.status_code == 200

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        trend_resp = client.get(f"/api/diaries/{diary_id}/emotion-trend", headers=headers)
        assert trend_resp.status_code == 200
        trend_data = trend_resp.json()["data"]

        assert trend_data["dominant"] == "开心"
        assert len(trend_data["trend"]) == 1
        item = trend_data["trend"][0]
        assert item["label"] == "开心"
        assert item["score"] == 7
        assert isinstance(item["hour"], int)
        assert 0 <= item["hour"] <= 23
        assert isinstance(item["minute"], int)
        assert 0 <= item["minute"] <= 59
        assert isinstance(item["time"], str)


class TestDiaryAI:
    """日记 AI 功能测试"""

    def test_extract_diary_info(self, client: TestClient, db, monkeypatch):
        """AI 提取结果应写入纪念日与用户画像，并可被跨模块接口读取"""
        auth, headers = _create_user_with_material(client, "diary_ai1")
        user_id = auth["user"]["id"]

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        class FakeMiniMaxClient:
            async def extract_info(self, content: str):
                return {
                    "anniversaries": [
                        {"title": "和小明聚餐", "date": "03-25", "related_person": "小明"}
                    ],
                    "persons": [
                        {"name": "小明", "relation": "室友", "mentions": 2}
                    ],
                    "preferences": ["日料", {"item": "跑步", "sentiment": "positive"}],
                }

        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

        resp = client.post(f"/api/diaries/{diary_id}/extract", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        # API 返回结构
        assert len(data["anniversaries"]) == 1
        assert data["anniversaries"][0]["title"] == "和小明聚餐"
        assert data["anniversaries"][0]["date"] == "03-25"
        assert data["anniversaries"][0]["relatedPerson"] == "小明"
        assert len(data["persons"]) == 1
        assert data["persons"][0]["name"] == "小明"
        assert data["persons"][0]["relation"] == "室友"
        assert any((isinstance(p, str) and p == "日料") for p in data["preferences"])

        # DB 写入校验：anniversaries 表
        anns = db.query(Anniversary).filter(
            Anniversary.user_id == user_id,
            Anniversary.diary_id == diary_id,
        ).all()
        assert len(anns) == 1
        assert anns[0].title == "和小明聚餐"
        assert anns[0].date == "03-25"
        assert anns[0].related_person == "小明"
        assert anns[0].source == "ai_extracted"

        # DB 写入校验：user_profiles 表
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        assert profile is not None
        relations = json.loads(profile.relations) if profile.relations else {}
        interests = json.loads(profile.interests) if profile.interests else []
        assert relations.get("小明") == "室友"
        assert "日料" in interests
        assert "跑步" in interests

        # 跨模块读取校验：anniversary 模块
        ann_list_resp = client.get("/api/anniversaries", headers=headers)
        assert ann_list_resp.status_code == 200
        ann_items = ann_list_resp.json()["data"]
        assert any(item["title"] == "和小明聚餐" for item in ann_items)

        # 跨模块读取校验：user 模块
        portrait_resp = client.get("/api/user/portrait", headers=headers)
        assert portrait_resp.status_code == 200
        portrait_data = portrait_resp.json()["data"]
        assert any(r["name"] == "小明" and r["relation"] == "室友" for r in portrait_data["relations"])
        assert "日料" in portrait_data["interests"]
        assert "跑步" in portrait_data["interests"]

    def test_extract_diary_info_idempotent_on_repeated_calls(self, client: TestClient, db, monkeypatch):
        """重复调用 extract 不应重复写入同一条纪念日"""
        auth, headers = _create_user_with_material(client, "diary_ai3")
        user_id = auth["user"]["id"]

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        class FakeMiniMaxClient:
            async def extract_info(self, content: str):
                return {
                    "anniversaries": [
                        {"title": "和小明聚餐", "date": "03-25", "related_person": "小明"}
                    ],
                    "persons": [
                        {"name": "小明", "relation": "室友", "mentions": 2}
                    ],
                    "preferences": ["日料", {"item": "跑步", "sentiment": "positive"}],
                }

        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

        first = client.post(f"/api/diaries/{diary_id}/extract", headers=headers)
        second = client.post(f"/api/diaries/{diary_id}/extract", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200

        anns = db.query(Anniversary).filter(
            Anniversary.user_id == user_id,
            Anniversary.diary_id == diary_id,
            Anniversary.title == "和小明聚餐",
            Anniversary.date == "03-25",
            Anniversary.related_person == "小明",
        ).all()
        assert len(anns) == 1

        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        assert profile is not None
        interests = json.loads(profile.interests) if profile.interests else []
        assert interests.count("日料") == 1
        assert interests.count("跑步") == 1

        ann_list_resp = client.get("/api/anniversaries", headers=headers)
        assert ann_list_resp.status_code == 200
        ann_items = ann_list_resp.json()["data"]
        same_ann = [
            item for item in ann_items
            if item["title"] == "和小明聚餐" and item["date"] == "03-25" and item["relatedPerson"] == "小明"
        ]
        assert len(same_ann) == 1

    def test_extract_diary_info_parses_markdown_json_and_persists_anniversary(self, client: TestClient, db, monkeypatch):
        """extract_info 能解析 markdown 包裹 JSON，并将“周年”等纪念日正确写入数据库。"""
        auth, headers = _create_user_with_material(client, "diary_ai_anniversary")
        user_id = auth["user"]["id"]

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        class FakeMiniMaxClient(minimax_client.MiniMaxClient):
            def __init__(self):
                super().__init__(api_key="x", api_base="https://api.minimaxi.com", model="mock-model", mock=False)

            async def chat_completion(
                self,
                messages: list,
                system_prompt: str = "",
                temperature: float = 0.8,
                max_tokens: int = 2048,
            ):
                return """```json
{
  "anniversaries": [
    {"title": "恋爱一周年", "date": "03-25", "related_person": "小雨"}
  ],
  "persons": [
    {"name": "小雨", "relation": "恋人"}
  ],
  "preferences": ["散步", "拍照"]
}
```"""

        fake_client = FakeMiniMaxClient()
        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: fake_client)

        resp = client.post(f"/api/diaries/{diary_id}/extract", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert any(a["title"] == "恋爱一周年" for a in data["anniversaries"])
        assert any(p["name"] == "小雨" and p["relation"] == "恋人" for p in data["persons"])
        assert "散步" in data["preferences"]

        anns = db.query(Anniversary).filter(
            Anniversary.user_id == user_id,
            Anniversary.diary_id == diary_id,
            Anniversary.title == "恋爱一周年",
            Anniversary.date == "03-25",
            Anniversary.related_person == "小雨",
        ).all()
        assert len(anns) == 1

        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        assert profile is not None
        relations = json.loads(profile.relations) if profile.relations else {}
        interests = json.loads(profile.interests) if profile.interests else []
        assert relations.get("小雨") == "恋人"
        assert "散步" in interests

    @pytest.mark.parametrize(
        "dtype,expected_content,expected_media_url,expected_image_calls,expected_chat_calls",
        [
            ("comic", "", "https://mock.local/comic.png", 1, 0),
            ("novel", "这是小说版内容", "", 0, 1),
            ("share_card", "这是分享卡文案", "", 0, 1),
        ],
    )
    def test_generate_derivative_all_types_and_persist(
        self,
        client: TestClient,
        db,
        monkeypatch,
        dtype,
        expected_content,
        expected_media_url,
        expected_image_calls,
        expected_chat_calls,
    ):
        """三种衍生类型都可生成，且正确写入 diary_derivatives 表。"""
        auth, headers = _create_user_with_material(client, f"diary_der_{dtype}")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        call_counts = {"image": 0, "chat": 0}
        call_payloads = {"image_prompt": ""}

        class FakeMiniMaxClient:
            async def generate_image(self, prompt: str, aspect_ratio: str = "1:1"):
                call_counts["image"] += 1
                call_payloads["image_prompt"] = prompt
                return "https://mock.local/comic.png"

            async def chat_completion(
                self,
                messages: list,
                system_prompt: str = "",
                temperature: float = 0.8,
                max_tokens: int = 2048,
            ):
                call_counts["chat"] += 1
                user_prompt = messages[0].get("content", "") if messages else ""
                if "短篇小说" in user_prompt:
                    return "这是小说版内容"
                return "这是分享卡文案"

        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

        resp = client.post(f"/api/diaries/{diary_id}/derivative", json={"type": dtype}, headers=headers)
        assert resp.status_code == 200

        data = resp.json()["data"]
        assert data["type"] == dtype
        assert data["content"] == expected_content
        assert data["mediaUrl"] == expected_media_url
        assert data["shareScope"] == "private"

        assert call_counts["image"] == expected_image_calls
        assert call_counts["chat"] == expected_chat_calls
        if dtype == "comic":
            assert "多格剧情漫画" in call_payloads["image_prompt"]
            assert "至少四格" in call_payloads["image_prompt"]

        rows = db.query(DiaryDerivative).filter(
            DiaryDerivative.diary_id == diary_id,
            DiaryDerivative.type == dtype,
        ).all()
        assert len(rows) == 1

        row = rows[0]
        assert row.content == expected_content
        assert row.media_url == expected_media_url
        assert row.share_scope == "private"

    def test_generate_derivative_invalid_type_returns_param_error(self, client: TestClient, db):
        """非法衍生类型应返回参数错误，且不写入 diary_derivatives。"""
        auth, headers = _create_user_with_material(client, "diary_der_invalid")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        resp = client.post(
            f"/api/diaries/{diary_id}/derivative",
            json={"type": "video"},
            headers=headers,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == 40102
        assert "仅支持 comic/novel/share_card" in body["message"]

        rows = db.query(DiaryDerivative).filter(DiaryDerivative.diary_id == diary_id).all()
        assert rows == []

    def test_generate_derivative_route_alias_plural_path(self, client: TestClient, db, monkeypatch):
        """兼容路径 /diaries/{id}/derivatives 应与 /derivative 行为一致。"""
        auth, headers = _create_user_with_material(client, "diary_der_alias")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        class FakeMiniMaxClient:
            async def chat_completion(self, *args, **kwargs):
                return "别名路由生成成功"

        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

        resp = client.post(f"/api/diaries/{diary_id}/derivatives", json={"type": "novel"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "novel"
        assert data["content"] == "别名路由生成成功"

    def test_generate_derivative_novel_timeout_fallback(self, client: TestClient, monkeypatch):
        """小说生成在 AI 超时/失败时应返回可用兜底文案，而不是直接报错。"""
        auth, headers = _create_user_with_material(client, "diary_der_to")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        diary_id = gen_resp.json()["data"]["id"]

        class TimeoutMiniMaxClient:
            async def chat_completion(self, *args, **kwargs):
                raise TimeoutError("simulated-timeout")

        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: TimeoutMiniMaxClient())

        resp = client.post(f"/api/diaries/{diary_id}/derivative", json={"type": "novel"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "novel"
        assert isinstance(data["content"], str) and data["content"]

    def test_generate_derivative_preview_legacy_id_fallback(self, client: TestClient, monkeypatch):
        """兼容 preview 兜底 id=1：应自动回退到用户最近一篇日记。"""
        auth, headers = _create_user_with_material(client, "diary_der_legacy")

        gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
        assert gen_resp.status_code == 200
        real_diary_id = gen_resp.json()["data"]["id"]

        class FakeMiniMaxClient:
            async def chat_completion(self, *args, **kwargs):
                return "兜底ID成功生成小说"

        monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

        # 前端 diaryId 丢失时会退回 '1'，后端应兼容。
        resp = client.post("/api/diaries/1/derivative", json={"type": "novel"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["diaryId"] == real_diary_id
        assert data["content"] == "兜底ID成功生成小说"


class TestDiarySearch:
    """日记搜索测试：多维度组合（AND）+ 同维度 OR。"""

    def _seed_search_diaries(self, db, user_id: str):
        rows = [
            {
                "id": "search_d1",
                "title": "校园晨光",
                "content": "今天在图书馆复习算法，效率很高",
                "location": "南开大学图书馆",
                "weather": "晴",
                "date": "2026-03-05",
                "dominant": "开心",
                "tags": ["校园", "学习"],
                "created_at": 1000,
            },
            {
                "id": "search_d2",
                "title": "火锅夜谈",
                "content": "晚上和室友去吃火锅，聊到很晚",
                "location": "天津大学附近",
                "weather": "多云 18℃",
                "date": "2026-03-20",
                "dominant": "幸福",
                "tags": ["美食", "社交"],
                "created_at": 2000,
            },
            {
                "id": "search_d4",
                "title": "晨跑记录",
                "content": "清晨在海河边跑步，状态不错",
                "location": "海河公园",
                "weather": "晴",
                "date": "2026-03-28",
                "dominant": "开心",
                "tags": ["运动"],
                "created_at": 3000,
            },
            {
                "id": "search_d3",
                "title": "雨天随记",
                "content": "在宿舍看书整理笔记",
                "location": "宿舍",
                "weather": "雨",
                "date": "2026-04-01",
                "dominant": "平静",
                "tags": ["居家", "学习"],
                "created_at": 4000,
            },
        ]

        for row in rows:
            diary = Diary(
                id=f"{row['id']}_{uuid4().hex[:8]}",
                user_id=user_id,
                title=row["title"],
                content=row["content"],
                location=row["location"],
                weather=row["weather"],
                date=row["date"],
                emotion_summary=json.dumps({"dominant": row["dominant"], "trend": []}, ensure_ascii=False),
                emotion=json.dumps({"label": row["dominant"], "score": 80, "emoji": "😊"}, ensure_ascii=False),
                tags=json.dumps(row["tags"], ensure_ascii=False),
                images=json.dumps([], ensure_ascii=False),
                material_ids=json.dumps([], ensure_ascii=False),
                status="published",
                created_at=row["created_at"],
                updated_at=row["created_at"],
            )
            db.add(diary)

        db.commit()

    def _prepare(self, client, db, username="diary_search_user"):
        auth = create_test_user(client, username=username)
        headers = get_auth_header(auth["token"])
        self._seed_search_diaries(db, auth["user"]["id"])
        return headers

    def test_search_keyword_matches_title_content_location(self, client: TestClient, db):
        headers = self._prepare(client, db, "diary_search_kw")

        r1 = client.get("/api/diaries/search?q=晨光", headers=headers)
        r2 = client.get("/api/diaries/search?q=火锅", headers=headers)
        r3 = client.get("/api/diaries/search?q=海河公园", headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200

        assert r1.json()["data"]["total"] == 1
        assert r2.json()["data"]["total"] == 1
        assert r3.json()["data"]["total"] == 1

    def test_search_emotion_single_and_multiple(self, client: TestClient, db):
        headers = self._prepare(client, db, "diary_search_emotion")

        single = client.get("/api/diaries/search?emotion=开心", headers=headers)
        multi = client.get("/api/diaries/search?emotion=开心,幸福", headers=headers)

        assert single.status_code == 200
        assert multi.status_code == 200
        assert single.json()["data"]["total"] == 2
        assert multi.json()["data"]["total"] == 3

    def test_search_tag_single_and_multiple(self, client: TestClient, db):
        headers = self._prepare(client, db, "diary_search_tag")

        single = client.get("/api/diaries/search?tag=校园", headers=headers)
        multi = client.get("/api/diaries/search?tag=校园,美食", headers=headers)

        assert single.status_code == 200
        assert multi.status_code == 200
        assert single.json()["data"]["total"] == 1
        assert multi.json()["data"]["total"] == 2

    def test_search_weather_single_and_multiple(self, client: TestClient, db):
        headers = self._prepare(client, db, "diary_search_weather")

        single = client.get("/api/diaries/search?weather=晴", headers=headers)
        cloud = client.get("/api/diaries/search?weather=多云", headers=headers)
        multi = client.get("/api/diaries/search?weather=晴,多云", headers=headers)

        assert single.status_code == 200
        assert cloud.status_code == 200
        assert multi.status_code == 200
        assert single.json()["data"]["total"] == 2
        assert cloud.json()["data"]["total"] == 1
        assert multi.json()["data"]["total"] == 3

    def test_search_date_range_closed_interval(self, client: TestClient, db):
        headers = self._prepare(client, db, "diary_search_date")

        resp = client.get("/api/diaries/search?from=2026-03-01&to=2026-03-31", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 3

    def test_search_combined_conditions_and_relation(self, client: TestClient, db):
        headers = self._prepare(client, db, "diary_search_combo")

        resp = client.get(
            "/api/diaries/search?q=图书馆&emotion=开心&from=2026-03-01&to=2026-03-31",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert "图书馆" in item["content"] or "图书馆" in item["location"] or "图书馆" in item["title"]

    def test_search_pagination(self, client: TestClient, db):
        headers = self._prepare(client, db, "diary_search_page")

        resp = client.get("/api/diaries/search?page=2&page_size=2", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 4
        assert data["page"] == 2
        assert data["page_size"] == 2
        assert len(data["items"]) == 2

    def test_search_empty_params_returns_all_with_pagination(self, client: TestClient, db):
        headers = self._prepare(client, db, "diary_search_empty")

        resp = client.get("/api/diaries/search", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 4
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["items"]) == 4

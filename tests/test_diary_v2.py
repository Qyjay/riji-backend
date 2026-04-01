"""
日记 v2 模块测试
- 测试日记生成
- 测试修改次数限制
- 测试情绪趋势查询
"""
import json

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

    def test_generate_diary_same_day_updates_existing(self, client: TestClient):
        """同一天重复生成：应更新同一篇日记，不新增第二篇"""
        auth, headers = _create_user_with_material(client, "diary_gen4")

        first_resp = client.post(
            "/api/diaries/generate",
            json={"date": "2026-03-25", "weather": "晴"},
            headers=headers,
        )
        assert first_resp.status_code == 200
        first_data = first_resp.json()["data"]
        first_id = first_data["id"]

        # 补一条同日素材，二次生成应更新同一篇日记
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
        assert second_data["weather"] == "阴"
        assert second_data["editCount"] == 0
        assert second_data["maxEdits"] == DIARY_MAX_EDITS

        # 列表总数保持 1，说明是更新不是新建
        list_resp = client.get("/api/diaries", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["data"]["total"] == 1

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

        # 时间格式校验：hour 为 0-23 的数字，趋势按时间非降序
        hours = []
        for item in data["trend"]:
            assert isinstance(item["hour"], int)
            assert 0 <= item["hour"] <= 23
            assert isinstance(item["label"], str) and item["label"]
            assert isinstance(item["score"], int)
            assert 0 <= item["score"] <= 100
            hours.append(item["hour"])

        assert hours == sorted(hours)

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

        # 有效情绪素材
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
        assert item["score"] == 90
        assert isinstance(item["hour"], int)
        assert 0 <= item["hour"] <= 23


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

        class FakeMiniMaxClient:
            async def generate_image(self, prompt: str, aspect_ratio: str = "1:1"):
                call_counts["image"] += 1
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

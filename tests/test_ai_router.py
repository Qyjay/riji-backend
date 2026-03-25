"""
AI 路由接口测试
测试 GET /ai/fortune 和 POST /ai/comic /ai/share-card /ai/bgm /ai/tts /ai/novel-chapter
全部在 MINIMAX_MOCK=true 下运行，不消耗真实 API 额度
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from tests.conftest import create_test_user, get_auth_header


def _setup_user(client: TestClient, username: str):
    """创建用户并返回 (auth, headers)"""
    auth = create_test_user(client, username=username)
    headers = get_auth_header(auth["token"])
    return auth, headers


def _create_diary(client: TestClient, headers: dict) -> str:
    """创建一篇日记，返回 diary_id"""
    resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
    assert resp.status_code == 200
    return resp.json()["data"]["id"]


class TestFortune:
    """GET /ai/fortune — 今日运势"""

    def test_fortune_no_diaries(self, client: TestClient):
        """无日记时也能生成运势"""
        _, headers = _setup_user(client, "ai_fortune1")
        resp = client.get("/api/ai/fortune", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        result = data["data"]
        assert "fortune" in result
        assert "score" in result
        assert "advice" in result

    def test_fortune_with_diaries(self, client: TestClient):
        """有日记时生成运势，包含完整字段"""
        _, headers = _setup_user(client, "ai_fortune2")
        # 先创建一篇日记
        client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)

        resp = client.get("/api/ai/fortune", headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert "fortune" in result
        assert "score" in result
        assert "lucky_color" in result
        assert "lucky_number" in result

    def test_fortune_requires_auth(self, client: TestClient):
        """未认证访问应返回 401"""
        resp = client.get("/api/ai/fortune")
        assert resp.status_code == 401


class TestComic:
    """POST /ai/comic — 漫画生成"""

    def test_comic_basic(self, client: TestClient):
        """基本漫画生成"""
        _, headers = _setup_user(client, "ai_comic1")
        resp = client.post("/api/ai/comic", json={
            "diary_content": "今天在图书馆读书，阳光透过窗户照进来，很温暖。",
            "style": "可爱卡通",
        }, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        result = data["data"]
        assert "image_url" in result
        assert "prompt_used" in result
        assert result["image_url"].startswith("http")

    def test_comic_default_style(self, client: TestClient):
        """默认风格（不传 style）"""
        _, headers = _setup_user(client, "ai_comic2")
        resp = client.post("/api/ai/comic", json={
            "diary_content": "和朋友去吃火锅，热热闹闹的。",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["image_url"]

    def test_comic_requires_auth(self, client: TestClient):
        """未认证应返回 401"""
        resp = client.post("/api/ai/comic", json={
            "diary_content": "test",
        })
        assert resp.status_code == 401


class TestShareCard:
    """POST /ai/share-card — 分享卡片"""

    def test_share_card_success(self, client: TestClient):
        """正常生成分享卡片"""
        _, headers = _setup_user(client, "ai_card1")
        diary_id = _create_diary(client, headers)

        resp = client.post("/api/ai/share-card", json={"diary_id": diary_id}, headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert "image_url" in result
        assert "quote" in result
        assert "diary_title" in result
        assert result["image_url"].startswith("http")

    def test_share_card_not_found(self, client: TestClient):
        """不存在的日记应返回 404"""
        _, headers = _setup_user(client, "ai_card2")
        resp = client.post("/api/ai/share-card", json={"diary_id": "nonexistent-id"}, headers=headers)
        assert resp.status_code == 404

    def test_share_card_other_user_diary(self, client: TestClient):
        """不能访问其他用户的日记"""
        _, headers1 = _setup_user(client, "ai_card3")
        _, headers2 = _setup_user(client, "ai_card4")

        diary_id = _create_diary(client, headers1)
        # user2 访问 user1 的日记
        resp = client.post("/api/ai/share-card", json={"diary_id": diary_id}, headers=headers2)
        assert resp.status_code == 404

    def test_share_card_requires_auth(self, client: TestClient):
        """未认证应返回 401"""
        resp = client.post("/api/ai/share-card", json={"diary_id": "abc"})
        assert resp.status_code == 401


class TestBgm:
    """POST /ai/bgm — BGM 生成"""

    def test_bgm_happy_mood(self, client: TestClient):
        """开心情绪生成 BGM"""
        _, headers = _setup_user(client, "ai_bgm1")
        resp = client.post("/api/ai/bgm", json={"mood": "开心"}, headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert "audio_url" in result
        assert result["mood"] == "开心"
        assert "duration_hint" in result

    def test_bgm_unknown_mood(self, client: TestClient):
        """未知情绪也能处理（使用默认映射）"""
        _, headers = _setup_user(client, "ai_bgm2")
        resp = client.post("/api/ai/bgm", json={"mood": "迷茫"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["audio_url"]

    def test_bgm_all_moods(self, client: TestClient):
        """所有预设情绪都能正确映射"""
        _, headers = _setup_user(client, "ai_bgm3")
        moods = ["开心", "悲伤", "平静", "感动", "焦虑", "期待", "愤怒", "无聊"]
        for mood in moods:
            resp = client.post("/api/ai/bgm", json={"mood": mood}, headers=headers)
            assert resp.status_code == 200, f"mood={mood} 失败"

    def test_bgm_requires_auth(self, client: TestClient):
        """未认证应返回 401"""
        resp = client.post("/api/ai/bgm", json={"mood": "开心"})
        assert resp.status_code == 401


class TestTts:
    """POST /ai/tts — 文字转语音"""

    def test_tts_basic(self, client: TestClient, tmp_path, monkeypatch):
        """基本 TTS 功能（Mock 模式）"""
        _, headers = _setup_user(client, "ai_tts1")
        # Mock 文件保存路径使用 tmp_path
        monkeypatch.setattr(
            "app.config.settings.UPLOAD_DIR", str(tmp_path)
        )
        resp = client.post("/api/ai/tts", json={
            "text": "今天是美好的一天",
            "voice": "male-qn-qingse",
        }, headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert "audio_url" in result
        assert result["audio_url"].startswith("/uploads/tts/")
        assert result["audio_url"].endswith(".mp3")
        assert "duration_hint" in result

    def test_tts_default_voice(self, client: TestClient, tmp_path, monkeypatch):
        """不传 voice 使用默认音色"""
        _, headers = _setup_user(client, "ai_tts2")
        monkeypatch.setattr("app.config.settings.UPLOAD_DIR", str(tmp_path))
        resp = client.post("/api/ai/tts", json={"text": "测试文本"}, headers=headers)
        assert resp.status_code == 200
        assert "/uploads/tts/" in resp.json()["data"]["audio_url"]

    def test_tts_duration_hint(self, client: TestClient, tmp_path, monkeypatch):
        """duration_hint 根据文本长度变化"""
        _, headers = _setup_user(client, "ai_tts3")
        monkeypatch.setattr("app.config.settings.UPLOAD_DIR", str(tmp_path))
        resp = client.post("/api/ai/tts", json={"text": "短文本"}, headers=headers)
        assert resp.status_code == 200
        assert "秒" in resp.json()["data"]["duration_hint"]

    def test_tts_requires_auth(self, client: TestClient):
        """未认证应返回 401"""
        resp = client.post("/api/ai/tts", json={"text": "test"})
        assert resp.status_code == 401


class TestNovelChapter:
    """POST /ai/novel-chapter — 小说章节"""

    def test_novel_basic(self, client: TestClient):
        """基本小说章节生成"""
        _, headers = _setup_user(client, "ai_novel1")
        resp = client.post("/api/ai/novel-chapter", json={
            "diary_content": "今天和朋友在校园里散步，聊了很多关于未来的事情。",
            "genre": "青春",
        }, headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert "chapter_title" in result
        assert "content" in result
        assert result["genre"] == "青春"
        assert len(result["content"]) > 0

    def test_novel_with_previous_chapter(self, client: TestClient):
        """传入上一章结尾时正常生成"""
        _, headers = _setup_user(client, "ai_novel2")
        resp = client.post("/api/ai/novel-chapter", json={
            "diary_content": "今天去了图书馆，发现了一本有趣的书。",
            "genre": "悬疑",
            "previous_chapter": "上一章：主角发现了一封神秘的信...",
        }, headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["genre"] == "悬疑"

    def test_novel_default_genre(self, client: TestClient):
        """不传 genre 使用默认值"""
        _, headers = _setup_user(client, "ai_novel3")
        resp = client.post("/api/ai/novel-chapter", json={
            "diary_content": "平凡的一天。",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["genre"] == "青春"

    def test_novel_requires_auth(self, client: TestClient):
        """未认证应返回 401"""
        resp = client.post("/api/ai/novel-chapter", json={
            "diary_content": "test",
        })
        assert resp.status_code == 401


class TestDeletedEndpoints:
    """确认旧的重复接口已删除"""

    def test_no_ai_chat_endpoint(self, client: TestClient):
        """POST /ai/chat 接口应已删除（404）"""
        _, headers = _setup_user(client, "ai_del1")
        resp = client.post("/api/ai/chat", json={"message": "hello"}, headers=headers)
        assert resp.status_code == 404

    def test_no_ai_generate_diary_endpoint(self, client: TestClient):
        """POST /ai/generate-diary 接口应已删除（404）"""
        _, headers = _setup_user(client, "ai_del2")
        resp = client.post("/api/ai/generate-diary", json={"draft": "test"}, headers=headers)
        assert resp.status_code == 404

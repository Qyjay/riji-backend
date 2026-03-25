"""
OpenClaw Gateway 集成测试

测试范围：
1. OpenClawClient.chat()       — 非流式
2. OpenClawClient.stream_chat() — 流式 SSE
3. chat router 三层降级逻辑
4. build_chat_system_prompt()
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import Response

from tests.conftest import create_test_user, get_auth_header


# ==================== OpenClawClient 单元测试 ====================


class TestOpenClawClient:
    """测试 OpenClawClient HTTP 调用"""

    def _make_client(self):
        from app.openclaw.client import OpenClawClient
        return OpenClawClient(
            gateway_url="http://localhost:18789",
            token="test-token",
            agent_id="riji",
        )

    @pytest.mark.asyncio
    async def test_chat_success(self):
        """非流式 chat 正常返回"""
        client = self._make_client()
        mock_response = {
            "choices": [{"message": {"content": "你好！很高兴认识你。"}}]
        }

        async def mock_post(url, headers, json):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = mock_response
            return mock_resp

        import httpx
        with patch.object(httpx.AsyncClient, "post", side_effect=mock_post):
            result = await client.chat(
                messages=[{"role": "user", "content": "你好"}],
                user_id="user-123",
            )
        assert result == "你好！很高兴认识你。"

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self):
        """system_prompt 应该被插入到 messages 最前面"""
        client = self._make_client()

        captured_payload = {}

        async def mock_post(url, headers, json):
            captured_payload.update(json)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}}]
            }
            return mock_resp

        import httpx
        with patch.object(httpx.AsyncClient, "post", side_effect=mock_post):
            await client.chat(
                messages=[{"role": "user", "content": "test"}],
                user_id="u1",
                system_prompt="你是测试助手",
            )

        msgs = captured_payload.get("messages", [])
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "你是测试助手"

    @pytest.mark.asyncio
    async def test_chat_user_field(self):
        """user 字段应为 riji-{user_id}"""
        client = self._make_client()
        captured = {}

        async def mock_post(url, headers, json):
            captured.update(json)
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "hi"}}]
            }
            return mock_resp

        import httpx
        with patch.object(httpx.AsyncClient, "post", side_effect=mock_post):
            await client.chat(
                messages=[{"role": "user", "content": "test"}],
                user_id="abc123",
            )

        assert captured.get("user") == "riji-abc123"
        assert captured.get("model") == "openclaw:riji"

    @pytest.mark.asyncio
    async def test_stream_chat_parses_sse(self):
        """stream_chat 能正确解析 SSE delta.content"""
        client = self._make_client()

        sse_lines = [
            'data: {"choices":[{"delta":{"content":"你"}}]}',
            'data: {"choices":[{"delta":{"content":"好"}}]}',
            'data: {"choices":[{"delta":{"content":"！"}}]}',
            "data: [DONE]",
        ]

        async def aiter_lines():
            for line in sse_lines:
                yield line

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = aiter_lines

        # Mock httpx.AsyncClient.stream context manager
        import httpx
        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(httpx.AsyncClient, "stream", return_value=mock_stream_cm):
            chunks = []
            async for chunk in client.stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                user_id="u1",
            ):
                chunks.append(chunk)

        assert chunks == ["你", "好", "！"]

    @pytest.mark.asyncio
    async def test_stream_chat_skips_malformed_json(self):
        """stream_chat 应跳过无法解析的 JSON 行"""
        client = self._make_client()

        sse_lines = [
            "data: not-json",
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            "data: [DONE]",
        ]

        async def aiter_lines():
            for line in sse_lines:
                yield line

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = aiter_lines

        import httpx
        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        with patch.object(httpx.AsyncClient, "stream", return_value=mock_stream_cm):
            chunks = []
            async for chunk in client.stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                user_id="u1",
            ):
                chunks.append(chunk)

        assert chunks == ["ok"]

    def test_get_openclaw_client_singleton(self):
        """get_openclaw_client 返回同一个实例"""
        import app.openclaw.client as mod
        # 重置单例
        mod._openclaw_client = None

        from app.openclaw.client import get_openclaw_client
        c1 = get_openclaw_client()
        c2 = get_openclaw_client()
        assert c1 is c2

        # 清理
        mod._openclaw_client = None


# ==================== prompt_builder 单元测试 ====================


class TestPromptBuilder:
    """测试 build_chat_system_prompt"""

    def _make_user(self, **kwargs):
        from app.models.user import User
        defaults = {
            "id": "u-test",
            "name": "小明",
            "school": "南开大学",
            "major": "软件工程",
            "signature": "记录每一天",
            "style_tags": '["文艺", "温暖"]',
            "custom_style_prompt": "喜欢细节描写",
        }
        defaults.update(kwargs)
        user = MagicMock(spec=User)
        for k, v in defaults.items():
            setattr(user, k, v)
        return user

    def test_contains_user_name(self, db):
        """prompt 包含用户昵称"""
        from app.openclaw.prompt_builder import build_chat_system_prompt
        user = self._make_user()
        prompt = build_chat_system_prompt(user, db)
        assert "小明" in prompt

    def test_contains_style_tags(self, db):
        """prompt 包含写作风格标签"""
        from app.openclaw.prompt_builder import build_chat_system_prompt
        user = self._make_user()
        prompt = build_chat_system_prompt(user, db)
        assert "文艺" in prompt
        assert "温暖" in prompt

    def test_contains_custom_style(self, db):
        """prompt 包含自定义风格 prompt"""
        from app.openclaw.prompt_builder import build_chat_system_prompt
        user = self._make_user()
        prompt = build_chat_system_prompt(user, db)
        assert "喜欢细节描写" in prompt

    def test_contains_today_materials(self, db):
        """prompt 包含今日素材内容"""
        import time
        from datetime import datetime
        from app.models.material import RawMaterial
        from app.openclaw.prompt_builder import build_chat_system_prompt

        user = self._make_user(id="u-mat-test")
        today = datetime.now().strftime("%Y-%m-%d")
        mat = RawMaterial(
            id="mat-1",
            user_id="u-mat-test",
            type="text",
            content="今天去图书馆看书了",
            date=today,
            created_at=int(time.time() * 1000),
        )
        db.add(mat)
        db.commit()

        prompt = build_chat_system_prompt(user, db)
        assert "今天去图书馆看书了" in prompt

    def test_contains_recent_diary(self, db):
        """prompt 包含最近日记标题"""
        import time
        from app.models.diary import Diary
        from app.openclaw.prompt_builder import build_chat_system_prompt

        user = self._make_user(id="u-diary-test")
        diary = Diary(
            id="d-1",
            user_id="u-diary-test",
            content="正文内容",
            title="阳光午后的碎碎念",
            date="2026-03-25",
            emotion_summary='{"dominant":"开心","distribution":{}}',
            created_at=int(time.time() * 1000),
            updated_at=int(time.time() * 1000),
        )
        db.add(diary)
        db.commit()

        prompt = build_chat_system_prompt(user, db)
        assert "阳光午后的碎碎念" in prompt
        assert "开心" in prompt

    def test_no_style_tags_skip_section(self, db):
        """无风格标签时不输出【写作风格偏好】段落"""
        from app.openclaw.prompt_builder import build_chat_system_prompt
        user = self._make_user(style_tags="[]", custom_style_prompt="")
        prompt = build_chat_system_prompt(user, db)
        assert "写作风格偏好" not in prompt


# ==================== 降级逻辑集成测试 ====================


class TestChatRouterFallback:
    """通过 TestClient 测试 chat 路由的三层降级"""

    def _setup(self, client):
        data = create_test_user(client, username="chatuser", password="pass123")
        return data["token"]

    def test_mock_mode_no_openclaw(self, client):
        """MINIMAX_MOCK=True 时，即使 OPENCLAW_ENABLED=True，也不调 OpenClaw"""
        token = self._setup(client)
        headers = get_auth_header(token)

        with patch("app.config.settings.OPENCLAW_ENABLED", True), \
             patch("app.config.settings.OPENCLAW_GATEWAY_TOKEN", "tok"), \
             patch("app.config.settings.MINIMAX_MOCK", True):
            resp = client.post(
                "/api/chat",
                json={"message": "你好"},
                headers=headers,
            )

        assert resp.status_code == 200
        # SSE 流式响应，内容包含 [DONE]
        assert "[DONE]" in resp.text

    def test_openclaw_disabled_uses_minimax(self, client):
        """OPENCLAW_ENABLED=False 时走 MiniMax（Mock 模式）"""
        token = self._setup(client)
        headers = get_auth_header(token)

        with patch("app.config.settings.OPENCLAW_ENABLED", False), \
             patch("app.config.settings.MINIMAX_MOCK", True):
            resp = client.post(
                "/api/chat",
                json={"message": "你好"},
                headers=headers,
            )

        assert resp.status_code == 200
        assert "[DONE]" in resp.text

    def test_openclaw_error_fallback_to_minimax(self, client):
        """OpenClaw 抛异常时降级到 MiniMax"""
        token = self._setup(client)
        headers = get_auth_header(token)

        async def broken_stream_chat(*args, **kwargs):
            raise RuntimeError("gateway unreachable")
            yield  # make it an async generator

        with patch("app.config.settings.OPENCLAW_ENABLED", True), \
             patch("app.config.settings.OPENCLAW_GATEWAY_TOKEN", "tok"), \
             patch("app.config.settings.MINIMAX_MOCK", True), \
             patch("app.openclaw.client.OpenClawClient.stream_chat", broken_stream_chat):
            resp = client.post(
                "/api/chat",
                json={"message": "你好"},
                headers=headers,
            )

        assert resp.status_code == 200
        assert "[DONE]" in resp.text

    def test_chat_saves_messages(self, client):
        """聊天后历史记录中应有 user + assistant 各 1 条"""
        token = self._setup(client)
        headers = get_auth_header(token)

        with patch("app.config.settings.MINIMAX_MOCK", True):
            client.post(
                "/api/chat",
                json={"message": "测试消息"},
                headers=headers,
            )
            history_resp = client.get("/api/chat/history", headers=headers)

        assert history_resp.status_code == 200
        data = history_resp.json()["data"]
        roles = [m["role"] for m in data["items"]]
        assert "user" in roles
        assert "assistant" in roles

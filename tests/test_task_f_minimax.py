"""
TASK-F 对话摘要（mock / 非mock）测试
"""

import asyncio

from app.ai.minimax_client import MiniMaxClient


def _build_client(mock: bool) -> MiniMaxClient:
    return MiniMaxClient(
        api_key="test-key",
        api_base="https://example.com",
        model="test-model",
        mock=mock,
    )


def _messages() -> list[dict]:
    return [
        {"role": "user", "content": "今天学习状态不错"},
        {"role": "assistant", "content": "太好了，最满意的是哪一段学习？"},
        {"role": "user", "content": "算法题复盘很顺"},
    ]


def test_task_f_summarize_chat_session_mock_returns_structured_payload():
    client = _build_client(mock=True)

    result = asyncio.run(client.summarize_chat_session(_messages()))

    assert set(result.keys()) == {"title", "summary", "mood", "mood_emoji", "tags"}
    assert isinstance(result["title"], str) and result["title"]
    assert isinstance(result["summary"], str) and result["summary"]
    assert isinstance(result["mood"], str) and result["mood"]
    assert isinstance(result["mood_emoji"], str) and result["mood_emoji"]
    assert isinstance(result["tags"], list)


def test_task_f_summarize_chat_session_non_mock_parses_json(monkeypatch):
    client = _build_client(mock=False)

    async def fake_chat_completion(*_args, **_kwargs):
        return (
            '{"title":"学习复盘","summary":"用户和AI讨论了学习进展，并总结了今天有效的方法。",'
            '"mood":"开心","mood_emoji":"😊","tags":["学习","复盘"]}'
        )

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    result = asyncio.run(client.summarize_chat_session(_messages()))

    assert result["title"] == "学习复盘"
    assert result["mood"] == "开心"
    assert result["mood_emoji"] == "😊"
    assert result["tags"] == ["学习", "复盘"]


def test_task_f_summarize_chat_session_non_mock_fallback_on_invalid_json(monkeypatch):
    client = _build_client(mock=False)

    async def fake_chat_completion(*_args, **_kwargs):
        return "not-a-json-payload"

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    result = asyncio.run(client.summarize_chat_session(_messages()))

    assert result["title"] == "对话记录"
    assert result["mood"] == "平静"
    assert result["mood_emoji"] == "😐"
    assert result["tags"] == ["对话"]


def test_task_f_detect_duplicate_chat_material_mock_detects_exact_match():
    client = _build_client(mock=True)

    existing = [
        {"id": "m1", "type": "text", "content": "下午骑车去了海河边，顺便吃了点小吃。"},
        {"id": "m2", "type": "text", "content": "晚上回宿舍复盘了今天计划。"},
    ]

    result = asyncio.run(
        client.detect_duplicate_chat_material(
            candidate_summary="下午骑车去了海河边，顺便吃了点小吃。",
            existing_materials=existing,
        )
    )

    assert result["is_duplicate"] is True
    assert result["duplicate_material_id"] == "m1"
    assert result["confidence"] == 1.0


def test_task_f_detect_duplicate_chat_material_non_mock_parses_json(monkeypatch):
    client = _build_client(mock=False)

    async def fake_chat_completion(*_args, **_kwargs):
        return (
            '{"is_duplicate":true,"duplicate_material_id":"m2",'
            '"reason":"same-event","confidence":0.87}'
        )

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    result = asyncio.run(
        client.detect_duplicate_chat_material(
            candidate_summary="今天在海河边骑车并吃了小吃。",
            existing_materials=[
                {"id": "m1", "type": "text", "content": "去了图书馆"},
                {"id": "m2", "type": "text", "content": "海河骑车+小吃"},
            ],
        )
    )

    assert result["is_duplicate"] is True
    assert result["duplicate_material_id"] == "m2"
    assert result["reason"] == "same-event"
    assert result["confidence"] == 0.87


def test_task_f_detect_duplicate_chat_material_non_mock_fallback_on_invalid_json(monkeypatch):
    client = _build_client(mock=False)

    async def fake_chat_completion(*_args, **_kwargs):
        return "not-a-json-payload"

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    result = asyncio.run(
        client.detect_duplicate_chat_material(
            candidate_summary="今天和朋友吃饭聊天。",
            existing_materials=[
                {"id": "m1", "type": "text", "content": "和朋友吃饭"},
            ],
        )
    )

    assert result["is_duplicate"] is False
    assert result["duplicate_material_id"] is None
    assert result["reason"] == "json-parse-failed"
    assert result["confidence"] == 0.0

"""小 V 语音指令意图识别：AI 判定、关键词兜底、deeplink 构造与接口鉴权。"""
import asyncio
import json

import pytest

from app.ai import minimax_client
from app.ai import voice_intent
from tests.conftest import create_test_user, get_auth_header


def _run(coro):
    return asyncio.run(coro)


class _FakeClient:
    """替掉真实 LLM 客户端，单测不打外部 API。"""

    mock = False

    def __init__(self, reply):
        self.reply = reply

    async def chat_completion(self, *_args, **_kwargs):
        if isinstance(self.reply, Exception):
            raise self.reply
        if callable(self.reply):
            return await self.reply()
        return self.reply


def _stub_chat(monkeypatch, reply):
    fake = _FakeClient(reply)
    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: fake)
    return fake


def _llm_json(action, target="", text="", requirement="", confidence=0.9):
    return json.dumps(
        {
            "action": action,
            "confidence": confidence,
            "slots": {"target": target, "text": text, "requirement": requirement},
        },
        ensure_ascii=False,
    )


UTTERANCES = {
    "quick_snap": "小v小v，我想在avalin发个快拍",
    "generate_diary": "小v小v，我想在avalin生成日记",
    "generate_comic": "小v小v，我想在avalin生成当日漫画",
    "find_friend": "小v小v，我想在avalin找个朋友",
    "find_friend_with_req": "小v小v，我想在avalin找个朋友，要求周末能一起看电影",
    "send_message": "小v小v，我想在avalin跟我的搭子小明说晚上一起吃饭",
}


# ==================== AI 判定 ====================

@pytest.mark.parametrize("action", list(UTTERANCES))
def test_ai_covers_six_intents(monkeypatch, action):
    _stub_chat(monkeypatch, _llm_json(action))
    result = _run(voice_intent.parse_voice_intent(UTTERANCES[action]))
    assert result["action"] == action
    assert result["source"] == "llm"


def test_ai_slots_are_passed_through(monkeypatch):
    _stub_chat(monkeypatch, _llm_json("send_message", target="小明", text="晚上一起吃饭"))
    result = _run(voice_intent.parse_voice_intent(UTTERANCES["send_message"]))
    assert result["slots"]["target"] == "小明"
    assert result["slots"]["text"] == "晚上一起吃饭"


def test_ai_output_tolerates_code_fence(monkeypatch):
    _stub_chat(monkeypatch, "```json\n" + _llm_json("generate_comic") + "\n```")
    assert _run(voice_intent.parse_voice_intent(UTTERANCES["generate_comic"]))["action"] == "generate_comic"


def test_missing_slots_are_filled_from_keywords(monkeypatch):
    _stub_chat(monkeypatch, _llm_json("send_message"))
    result = _run(voice_intent.parse_voice_intent(UTTERANCES["send_message"]))
    assert result["slots"]["target"] == "小明"
    assert result["slots"]["text"] == "晚上一起吃饭"


def test_find_friend_upgrades_when_requirement_recovered(monkeypatch):
    _stub_chat(monkeypatch, _llm_json("find_friend"))
    result = _run(voice_intent.parse_voice_intent(UTTERANCES["find_friend_with_req"]))
    assert result["action"] == "find_friend_with_req"
    assert result["slots"]["requirement"] == "周末能一起看电影"


# ==================== 兜底链路 ====================

def test_ai_timeout_falls_back_to_keywords(monkeypatch):
    async def slow_reply():
        await asyncio.sleep(1)
        return _llm_json("unknown")

    _stub_chat(monkeypatch, slow_reply)
    monkeypatch.setattr(voice_intent.settings, "VOICE_INTENT_TIMEOUT_SEC", 0.05)

    result = _run(voice_intent.parse_voice_intent(UTTERANCES["quick_snap"]))
    assert result["action"] == "quick_snap"
    assert result["source"] == "keywords"


def test_ai_error_falls_back_to_keywords(monkeypatch):
    _stub_chat(monkeypatch, RuntimeError("boom"))
    result = _run(voice_intent.parse_voice_intent(UTTERANCES["generate_diary"]))
    assert result["action"] == "generate_diary"
    assert result["source"] == "keywords"


@pytest.mark.parametrize(
    "reply",
    [
        "",
        "随便一段解释文字",
        "{不是合法 json}",
        '{"action": "do_something"}',
        '{"confidence": 0.9}',
        '{"action": "unknown", "confidence": 0.9, "slots": {}}',
    ],
)
def test_illegal_structure_falls_back_to_keywords(monkeypatch, reply):
    _stub_chat(monkeypatch, reply)
    result = _run(voice_intent.parse_voice_intent(UTTERANCES["send_message"]))
    assert result["action"] == "send_message"
    assert result["slots"]["target"] == "小明"


def test_keyword_rules_cover_six_intents():
    for action, utterance in UTTERANCES.items():
        assert voice_intent.parse_by_keywords(utterance)["action"] == action


def test_result_is_always_structurally_valid(monkeypatch):
    _stub_chat(monkeypatch, "完全不相关的输出")
    for text in ["", "   ", "今天天气怎么样", "12345", "###", None]:
        result = _run(voice_intent.parse_voice_intent(text))
        assert result["action"] in voice_intent.VOICE_INTENT_ACTIONS
        assert set(result["slots"]) == {"target", "text", "requirement"}
        assert all(isinstance(value, str) for value in result["slots"].values())
        assert 0.0 <= result["confidence"] <= 1.0


def test_unrecognized_utterance_is_unknown(monkeypatch):
    _stub_chat(monkeypatch, "完全不相关的输出")
    result = _run(voice_intent.parse_voice_intent("今天天气怎么样"))
    assert result["action"] == "unknown"


def test_mock_client_skips_network(monkeypatch):
    class MockClient(_FakeClient):
        mock = True

        async def chat_completion(self, *_args, **_kwargs):
            raise AssertionError("mock 客户端不应该发起 LLM 调用")

    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: MockClient(""))
    assert _run(voice_intent.parse_voice_intent(UTTERANCES["find_friend"]))["action"] == "find_friend"


# ==================== deeplink 构造 ====================

def test_deeplink_matches_frontend_routes():
    assert voice_intent.build_deeplink("quick_snap", {}) == "avalin://snap"
    assert voice_intent.build_deeplink("generate_diary", {}) == "avalin://memory/generate"
    assert voice_intent.build_deeplink("generate_comic", {}) == "avalin://comic/today"
    assert voice_intent.build_deeplink("find_friend", {}) == "avalin://social/find"
    assert voice_intent.build_deeplink("unknown", {}) == "avalin://home"
    assert voice_intent.build_deeplink("send_message", {"target": ""}) == "avalin://messages"
    assert voice_intent.build_deeplink("find_friend_with_req", {"requirement": ""}) == "avalin://social/find"


def test_deeplink_encodes_chinese_free_text():
    from urllib.parse import parse_qs, urlparse

    link = voice_intent.build_deeplink("send_message", {"target": "小明", "text": "晚上一起吃饭"})
    assert "小明" not in link
    query = parse_qs(urlparse(link).query)
    assert query["to"] == ["小明"]
    assert query["text"] == ["晚上一起吃饭"]

    find_link = voice_intent.build_deeplink("find_friend_with_req", {"requirement": "周末看电影"})
    assert parse_qs(urlparse(find_link).query)["intent"] == ["周末看电影"]


# ==================== 接口 ====================

def test_voice_intent_endpoint_returns_contract(client, monkeypatch):
    _stub_chat(monkeypatch, _llm_json("send_message", target="小明", text="晚上一起吃饭"))
    user = create_test_user(client, username="voice_intent_user")
    headers = get_auth_header(user["token"])

    resp = client.post(
        "/api/ai/voice-intent",
        json={"utterance": UTTERANCES["send_message"]},
        headers=headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["action"] == "send_message"
    assert data["slots"]["target"] == "小明"
    assert data["deeplink"].startswith("avalin://say?")
    assert data["speech"]
    assert data["source"] in {"llm", "keywords"}


def test_voice_intent_endpoint_survives_ai_failure(client, monkeypatch):
    _stub_chat(monkeypatch, RuntimeError("boom"))
    user = create_test_user(client, username="voice_intent_fb")
    headers = get_auth_header(user["token"])

    resp = client.post(
        "/api/ai/voice-intent",
        json={"utterance": UTTERANCES["quick_snap"]},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["action"] == "quick_snap"
    assert data["deeplink"] == "avalin://snap"


def test_voice_intent_endpoint_accepts_empty_utterance(client, monkeypatch):
    _stub_chat(monkeypatch, _llm_json("quick_snap"))
    user = create_test_user(client, username="voice_intent_empty")
    headers = get_auth_header(user["token"])

    resp = client.post("/api/ai/voice-intent", json={"utterance": "   "}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["action"] == "unknown"
    assert data["deeplink"] == "avalin://home"


def test_voice_intent_no_auth(client):
    """无 token 访问语音意图接口返回 401"""
    resp = client.post("/api/ai/voice-intent", json={"utterance": "发个快拍"})
    assert resp.status_code == 401 or resp.json().get("code", 0) != 0

"""
TASK-F 对话摘要（mock / 非mock）测试
"""

import asyncio
from contextlib import asynccontextmanager
import io
import wave

import pytest

from app.ai.minimax_client import MiniMaxClient
from app.response import ApiException


def _build_client(mock: bool) -> MiniMaxClient:
    return MiniMaxClient(
        api_key="test-key",
        api_base="https://example.com",
        model="test-model",
        mock=mock,
    )


def _build_vivo_client(mock: bool) -> MiniMaxClient:
    return MiniMaxClient(
        api_key="unused-minimax-key",
        api_base="https://example.com",
        model="test-model",
        mock=mock,
        provider="vivo",
        vivo_app_id="test-app-id",
        vivo_app_key="test-vivo-app-key",
        vivo_api_base="https://api-ai.vivo.com.cn",
        vivo_model="Doubao-Seed-2.0-mini",
    )


def _messages() -> list[dict]:
    return [
        {"role": "user", "content": "今天学习状态不错"},
        {"role": "assistant", "content": "太好了，最满意的是哪一段学习？"},
        {"role": "user", "content": "算法题复盘很顺"},
    ]


def _build_pcm_wav_16k_mono(pcm_data: bytes) -> bytes:
    io_fd = io.BytesIO()
    with wave.open(io_fd, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(pcm_data)
    return io_fd.getvalue()


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
    assert isinstance(result["summary"], str) and result["summary"]
    assert "我" in result["summary"]
    assert "用户:" not in result["summary"]
    assert result["mood"] == "平静"
    assert result["mood_emoji"] == "😐"
    assert result["tags"] == ["对话"]


def test_task_f_summarize_chat_session_fallback_covers_multiple_turns(monkeypatch):
    client = _build_client(mock=False)

    async def fake_chat_completion(*_args, **_kwargs):
        return "not-a-json-payload"

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    messages = [
        {"role": "user", "content": "第一件事是早上去跑步。"},
        {"role": "assistant", "content": "听起来很棒，后面还做了什么？"},
        {"role": "user", "content": "第二件事是中午和同学复盘项目。"},
        {"role": "assistant", "content": "复盘后有什么收获？"},
        {"role": "user", "content": "第三件事是晚上把关键改动都提交了。"},
    ]

    result = asyncio.run(client.summarize_chat_session(messages))

    assert "第三件事" in result["summary"]
    assert "用户:" not in result["summary"]
    assert "AI:" not in result["summary"]


def test_task_f_generate_diary_non_mock_fallback_returns_polished_text(monkeypatch):
    client = _build_client(mock=False)

    async def fake_chat_completion(*_args, **_kwargs):
        raise RuntimeError("upstream-failed")

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    materials_text = (
        "[08:00] [文字] 早上去图书馆复习算法\n"
        "[对话记录] (09:00~09:25) 用户和AI讨论了今天的学习进展，并总结了复习计划"
    )

    result = asyncio.run(
        client.generate_diary(
            materials_text,
            weather="晴",
            daily_emotion_summary={"dominant": "平静", "trend": []},
        )
    )

    assert result["title"] == "今日记录"
    assert isinstance(result["content"], str) and result["content"]
    assert result["content"] != materials_text
    assert "用户和AI" not in result["content"]
    assert "我和AI" in result["content"]


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


def test_task_f_detect_duplicate_chat_material_mock_prefers_vivo_similarity(monkeypatch):
    client = _build_client(mock=True)

    async def fake_vivo_batch_similarity(target, candidates):
        assert target == "今天在图书馆复盘算法题"
        assert candidates == [
            "下午和同学在食堂吃饭",
            "我在图书馆复盘了今天的算法题",
        ]
        return [0.22, 0.86]

    monkeypatch.setattr(client, "_vivo_batch_text_similarity", fake_vivo_batch_similarity)

    result = asyncio.run(
        client.detect_duplicate_chat_material(
            candidate_summary="今天在图书馆复盘算法题",
            existing_materials=[
                {"id": "m1", "type": "text", "content": "下午和同学在食堂吃饭"},
                {"id": "m2", "type": "text", "content": "我在图书馆复盘了今天的算法题"},
            ],
        )
    )

    assert result["is_duplicate"] is True
    assert result["duplicate_material_id"] == "m2"
    assert result["reason"] == "high-semantic-overlap-in-vivo-similarity"
    assert result["confidence"] == 0.86


def test_task_f_detect_duplicate_chat_material_mock_vivo_similarity_not_duplicate(monkeypatch):
    client = _build_client(mock=True)

    async def fake_vivo_batch_similarity(_target, _candidates):
        return [0.31, 0.45]

    monkeypatch.setattr(client, "_vivo_batch_text_similarity", fake_vivo_batch_similarity)

    result = asyncio.run(
        client.detect_duplicate_chat_material(
            candidate_summary="今天在操场散步",
            existing_materials=[
                {"id": "m1", "type": "text", "content": "下午和同学在食堂吃饭"},
                {"id": "m2", "type": "text", "content": "晚饭后回宿舍看电影"},
            ],
        )
    )

    assert result["is_duplicate"] is False
    assert result["duplicate_material_id"] is None
    assert result["reason"] == "vivo-similarity-not-duplicate"
    assert result["confidence"] == 0.45


def test_stream_chat_non_mock_char_mode_splits_chunk(monkeypatch):
    client = _build_client(mock=False)

    monkeypatch.setenv("CHAT_STREAM_CHAR_MODE", "true")
    monkeypatch.setenv("CHAT_STREAM_CHAR_DELAY_SEC", "0")

    class _FakeStreamResp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "你好"}}]}'
            yield 'data: {"choices": [{"delta": {"content": "世界"}}]}'
            yield "data: [DONE]"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *_args, **_kwargs):
            return _FakeStreamResp()

    monkeypatch.setattr("app.ai.minimax_client.httpx.AsyncClient", _FakeAsyncClient)

    async def _collect() -> list[str]:
        parts: list[str] = []
        async for part in client.stream_chat([{"role": "user", "content": "hi"}]):
            parts.append(part)
        return parts

    chunks = asyncio.run(_collect())
    assert chunks == ["你", "好", "世", "界"]


def test_stream_chat_non_mock_raw_mode_keeps_chunk(monkeypatch):
    client = _build_client(mock=False)

    monkeypatch.setenv("CHAT_STREAM_CHAR_MODE", "false")
    monkeypatch.setenv("CHAT_STREAM_CHAR_DELAY_SEC", "0")

    class _FakeStreamResp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "你好"}}]}'
            yield 'data: {"choices": [{"delta": {"content": "世界"}}]}'
            yield "data: [DONE]"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *_args, **_kwargs):
            return _FakeStreamResp()

    monkeypatch.setattr("app.ai.minimax_client.httpx.AsyncClient", _FakeAsyncClient)

    async def _collect() -> list[str]:
        parts: list[str] = []
        async for part in client.stream_chat([{"role": "user", "content": "hi"}]):
            parts.append(part)
        return parts

    chunks = asyncio.run(_collect())
    assert chunks == ["你好", "世界"]


def test_chat_completion_vivo_non_mock_parses_response(monkeypatch):
    client = _build_vivo_client(mock=False)

    class _FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "你好，来自 VIVO"}}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_args, **kwargs):
            assert kwargs.get("params", {}).get("request_id")
            return _FakeResponse()

    monkeypatch.setattr("app.ai.minimax_client.httpx.AsyncClient", _FakeAsyncClient)

    result = asyncio.run(client.chat_completion([{"role": "user", "content": "hi"}]))
    assert result == "你好，来自 VIVO"


def test_stream_chat_vivo_non_mock_raw_mode_keeps_chunk(monkeypatch):
    client = _build_vivo_client(mock=False)

    monkeypatch.setenv("CHAT_STREAM_CHAR_MODE", "false")
    monkeypatch.setenv("CHAT_STREAM_CHAR_DELAY_SEC", "0")

    class _FakeStreamResp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "你好"}}]}'
            yield 'data: {"choices": [{"delta": {"content": "，VIVO"}}]}'
            yield "data: [DONE]"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *_args, **kwargs):
            assert kwargs.get("params", {}).get("request_id")
            return _FakeStreamResp()

    monkeypatch.setattr("app.ai.minimax_client.httpx.AsyncClient", _FakeAsyncClient)

    async def _collect() -> list[str]:
        parts: list[str] = []
        async for part in client.stream_chat([{"role": "user", "content": "hi"}]):
            parts.append(part)
        return parts

    chunks = asyncio.run(_collect())
    assert chunks == ["你好", "，VIVO"]


def test_generate_image_vivo_non_mock_parses_images_list(monkeypatch):
    client = _build_vivo_client(mock=False)

    class _FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 0,
                "message": "success",
                "trace_id": "trace-x",
                "data": {
                    "images": [
                        {"url": "https://img.example.com/a.png", "size": "2048x2048"},
                    ],
                },
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            assert url.endswith("/api/v1/image_generation")
            params = kwargs.get("params", {})
            assert params.get("module") == "aigc"
            assert params.get("request_id")
            assert params.get("system_time")
            payload = kwargs.get("json", {})
            assert payload.get("model") == "Doubao-Seedream-4.5"
            assert payload.get("parameters", {}).get("size") == "2048x2048"
            return _FakeResponse()

    monkeypatch.setattr("app.ai.minimax_client.httpx.AsyncClient", _FakeAsyncClient)

    result = asyncio.run(client.generate_image("一张日落海边照片", aspect_ratio="1:1"))
    assert result == "https://img.example.com/a.png"


def test_generate_image_vivo_non_mock_raises_when_code_is_not_zero(monkeypatch):
    client = _build_vivo_client(mock=False)

    class _FakeResponse:
        status_code = 200
        text = "ok"

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 1003,
                "message": "Rate limit exceeded",
                "trace_id": "trace-limit",
                "data": {},
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *_args, **_kwargs):
            return _FakeResponse()

    monkeypatch.setattr("app.ai.minimax_client.httpx.AsyncClient", _FakeAsyncClient)

    with pytest.raises(ApiException, match="code=1003"):
        asyncio.run(client.generate_image("测试限流"))


def test_text_to_speech_vivo_non_mock_converts_pcm_to_wav(monkeypatch):
    client = _build_vivo_client(mock=False)

    captured = {"voice_id": "", "user_id": ""}

    async def fake_synthesize_pcm(**kwargs):
        captured["voice_id"] = kwargs.get("voice_id", "")
        captured["user_id"] = kwargs.get("user_id", "")
        return b"\x00\x01" * 512

    monkeypatch.setattr(client, "_vivo_tts_synthesize_pcm", fake_synthesize_pcm)

    wav_bytes = asyncio.run(
        client.text_to_speech(
            text="你好，语音测试",
            voice_id="male-qn-qingse",
            user_id="user-abc",
        )
    )

    assert captured["voice_id"] == "male-qn-qingse"
    assert captured["user_id"] == "user-abc"
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"


def test_text_to_speech_vivo_non_mock_requires_app_key():
    client = MiniMaxClient(
        api_key="unused",
        api_base="https://example.com",
        model="test-model",
        mock=False,
        provider="vivo",
        vivo_app_key="",
    )

    with pytest.raises(ApiException, match="VIVO_APP_KEY"):
        asyncio.run(client.text_to_speech("你好", user_id="user1"))


def test_text_to_speech_prefers_vivo_when_app_key_exists(monkeypatch):
    client = MiniMaxClient(
        api_key="minimax-key",
        api_base="https://example.com",
        model="test-model",
        mock=False,
        provider="minimax",
        vivo_app_key="vivo-key",
    )

    captured = {"called": False}

    async def fake_synthesize_pcm(**_kwargs):
        captured["called"] = True
        return b"\x00\x01" * 256

    monkeypatch.setattr(client, "_vivo_tts_synthesize_pcm", fake_synthesize_pcm)

    wav_bytes = asyncio.run(client.text_to_speech("hello", user_id="u1"))
    assert captured["called"] is True
    assert wav_bytes[:4] == b"RIFF"


def test_speech_to_text_short_vivo_non_mock_recognizes_pcm(monkeypatch):
    client = _build_vivo_client(mock=False)

    captured = {
        "pcm_length": 0,
        "user_id": "",
        "punctuation": -1,
        "chinese2digital": -1,
        "end_vad_time": -1,
    }

    async def fake_recognize_pcm(**kwargs):
        captured["pcm_length"] = len(kwargs.get("pcm_data", b""))
        captured["user_id"] = kwargs.get("user_id", "")
        captured["punctuation"] = kwargs.get("punctuation", -1)
        captured["chinese2digital"] = kwargs.get("chinese2digital", -1)
        captured["end_vad_time"] = kwargs.get("end_vad_time", -1)
        return {
            "text": "你好，世界",
            "sid": "sid-1",
            "requestId": "req-1",
            "segments": [{"text": "你好，世界", "isLast": True, "reformation": 0}],
        }

    monkeypatch.setattr(client, "_vivo_asr_recognize_pcm", fake_recognize_pcm)

    pcm = (b"\x00\x01" * 800)
    wav_bytes = _build_pcm_wav_16k_mono(pcm)
    result = asyncio.run(
        client.speech_to_text_short(
            audio_bytes=wav_bytes,
            audio_format="wav",
            user_id="user-xyz",
            punctuation=1,
            chinese2digital=1,
            end_vad_time=1800,
        )
    )

    assert result["text"] == "你好，世界"
    assert captured["pcm_length"] == len(pcm)
    assert captured["user_id"] == "user-xyz"
    assert captured["punctuation"] == 1
    assert captured["chinese2digital"] == 1
    assert captured["end_vad_time"] == 1800


def test_speech_to_text_short_rejects_mp3_format():
    client = _build_vivo_client(mock=False)

    with pytest.raises(ApiException, match="仅支持 wav/pcm"):
        asyncio.run(
            client.speech_to_text_short(
                audio_bytes=b"fake-mp3-bytes",
                audio_format="mp3",
                user_id="u1",
            )
        )


def test_websocket_connect_fallback_supports_extra_headers_only():
    client = _build_vivo_client(mock=False)

    class FakeSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeWebsocketsModule:
        @staticmethod
        def connect(_url, **kwargs):
            if "extra_headers" in kwargs:
                return FakeSocket()
            raise TypeError("BaseEventLoop.create_connection() got an unexpected keyword argument 'additional_headers'")

    async def _run_open():
        async with client._websocket_connect(  # type: ignore[attr-defined]
            FakeWebsocketsModule,
            "wss://example.com/asr",
            {"Authorization": "Bearer test"},
            10.0,
        ) as ws:
            assert isinstance(ws, FakeSocket)

    asyncio.run(_run_open())


def test_build_vivo_ws_headers_contains_vaid_when_app_id_exists():
    client = _build_vivo_client(mock=False)
    headers = client._build_vivo_ws_headers()  # type: ignore[attr-defined]
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["vaid"] == "test-app-id"


def test_tts_http_400_fallback_to_ws_client(monkeypatch):
    client = _build_vivo_client(mock=False)

    class FakeHttp400Error(Exception):
        status_code = 400

    @asynccontextmanager
    async def fake_ws_connect(*_args, **_kwargs):
        raise FakeHttp400Error("server rejected WebSocket connection: HTTP 400")
        yield

    async def fake_to_thread(func, *args):
        return func(*args)

    def fake_ws_client(*_args, **_kwargs):
        return b"\x00\x01" * 128

    monkeypatch.setattr(client, "_websocket_connect", fake_ws_connect)
    monkeypatch.setattr(client, "_vivo_tts_synthesize_pcm_with_ws_client", fake_ws_client)
    monkeypatch.setattr("app.ai.minimax_client.asyncio.to_thread", fake_to_thread)

    pcm = asyncio.run(client._vivo_tts_synthesize_pcm("你好", "xiaofu", "u1"))
    assert isinstance(pcm, bytes)
    assert len(pcm) == 256

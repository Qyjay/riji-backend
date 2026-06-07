"""
AI + 聊天模块测试
"""
import asyncio
from pathlib import Path

import pytest

from tests.conftest import create_test_user, get_auth_header
from app.ai.minimax_client import MiniMaxClient


@pytest.fixture(autouse=True)
def mock_chat_route_model(monkeypatch):
    class FakeChatClient:
        async def chat_completion(self, *_args, **_kwargs):
            return "测试回复"

        async def stream_chat(self, *_args, **_kwargs):
            for chunk in ["这", "是", "流式", "回复"]:
                yield chunk

    def fake_resolve_chat_client(*_args, **_kwargs):
        return FakeChatClient(), "test-auto-model"

    monkeypatch.setattr("app.ai.model_service.resolve_chat_client", fake_resolve_chat_client)


def test_chat_returns_text_contract(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/chat", json={"message": "你好，请介绍一下自己"}, headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert isinstance(payload["data"], str)
    assert payload["data"].strip()
    assert "meta" not in payload


def test_chat_stream_supports_attachments(client, monkeypatch):
    user_data = create_test_user(client, username="chat_stream_user")
    headers = get_auth_header(user_data["token"])

    class FakeStreamClient:
        async def stream_chat(self, *_args, **_kwargs):
            for chunk in ["这", "是", "流式", "回复"]:
                yield chunk

    def fake_get_minimax_client():
        return FakeStreamClient()

    monkeypatch.setattr("app.ai.minimax_client.get_minimax_client", fake_get_minimax_client)

    chunks = []
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "message": "帮我看看这份资料",
            "clientMessageId": "cmsg_test_1",
            "attachments": [
                {
                    "type": "file",
                    "name": "notes.pdf",
                    "url": "/uploads/test/chat-file/notes.pdf",
                    "mimeType": "application/pdf",
                    "size": 1024,
                }
            ],
        },
        headers=headers,
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line:
                chunks.append(line)

    joined = "\n".join(chunks)
    assert '"type": "session"' in joined
    assert '"type": "ack"' in joined
    assert '"type": "done"' in joined
    assert '"clientMessageId": "cmsg_test_1"' in joined


def test_chat_history_returns_complete_messages(client):
    user_data = create_test_user(client, username="chat_history_user")
    headers = get_auth_header(user_data["token"])

    client.post(
        "/api/chat",
        json={
            "message": "你好",
            "clientMessageId": "history_msg_1",
            "attachments": [
                {
                    "type": "image",
                    "name": "sunset.jpg",
                    "url": "/uploads/test/diary-image/sunset.jpg",
                    "thumbnailUrl": "/uploads/test/diary-image/thumb_sunset.jpg",
                }
            ],
        },
        headers=headers,
    )

    resp = client.get("/api/chat/history?limit=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "items" in data and "total" in data
    assert data["total"] >= 2
    first_user = next(item for item in data["items"] if item["role"] == "user")
    assert first_user["id"]
    assert first_user["clientMessageId"] == "history_msg_1"
    assert first_user["sessionId"]
    assert isinstance(first_user["attachments"], list)
    assert first_user["attachments"][0]["type"] == "image"


def test_session_messages_returns_complete_messages(client):
    user_data = create_test_user(client, username="chat_session_user")
    headers = get_auth_header(user_data["token"])

    send_resp = client.post("/api/chat", json={"message": "今天天气不错"}, headers=headers)
    assert send_resp.status_code == 200

    history_resp = client.get("/api/chat/history?limit=20", headers=headers)
    assert history_resp.status_code == 200
    history_items = history_resp.json()["data"]["items"]
    session_id = next(
        item["sessionId"]
        for item in history_items
        if item["role"] == "user" and item["content"] == "今天天气不错"
    )

    resp = client.get(f"/api/chat/session/{session_id}/messages", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["session"]["id"] == session_id
    assert len(payload["messages"]) >= 2
    first = payload["messages"][0]
    assert set(first.keys()) == {"role", "content", "timestamp"}


def test_new_session_id_can_be_reused_in_chat(client):
    user_data = create_test_user(client, username="chat_new_sess_u")
    headers = get_auth_header(user_data["token"])

    session_resp = client.post("/api/chat/sessions", headers=headers)
    assert session_resp.status_code == 200
    session_payload = session_resp.json()["data"]
    session_id = session_payload["session"]["id"]
    assert session_id

    send_resp = client.post(
        "/api/chat",
        json={"message": "使用新会话 ID 发消息", "sessionId": session_id},
        headers=headers,
    )
    assert send_resp.status_code == 200

    detail_resp = client.get(f"/api/chat/session/{session_id}/messages", headers=headers)
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["session"]["id"] == session_id
    assert any(item["content"] == "使用新会话 ID 发消息" for item in payload["messages"])


def test_fortune(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/ai/fortune", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    f = data["data"]
    assert "overall" in f
    assert "study" in f
    assert "social" in f
    assert "health" in f
    assert "tip" in f
    assert "luckyColor" in f
    assert "luckyNumber" in f


def test_tts(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/ai/tts", json={"text": "你好，这是测试语音"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], str)


def test_asr_short(client, monkeypatch):
    user_data = create_test_user(client, username="ai_asr_user")
    headers = get_auth_header(user_data["token"])

    async def fake_asr_service(user_id, file, punctuation, chinese2digital, end_vad_time):
        assert user_id == user_data["user"]["id"]
        assert file.filename == "sample.wav"
        assert punctuation == 1
        assert chinese2digital == 1
        assert end_vad_time == 2000
        return {
            "text": "这是识别结果",
            "sid": "sid-123",
            "requestId": "req-123",
            "segments": [{"text": "这是识别结果", "isLast": True, "reformation": 0}],
        }

    monkeypatch.setattr("app.ai.service.speech_to_text_short_service", fake_asr_service)

    resp = client.post(
        "/api/ai/asr?punctuation=1&chinese2digital=1&end_vad_time=2000",
        files={"file": ("sample.wav", b"RIFF....WAVE", "audio/wav")},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["text"] == "这是识别结果"
    assert data["data"]["requestId"] == "req-123"


def test_resolve_asr_audio_format_detects_mp3_magic_header():
    from app.ai import service as ai_service

    class FakeUpload:
        filename = "voice.bin"
        content_type = "application/octet-stream"

    detected = ai_service._resolve_asr_audio_format(
        FakeUpload(),
        b"ID3\x04\x00\x00\x00\x00\x00\x21fake-mp3-payload",
    )

    assert detected == "mp3"


def test_speech_to_text_short_service_auto_converts_mp3(monkeypatch):
    from app.ai import service as ai_service

    class FakeUpload:
        filename = "voice.mp3"
        content_type = "audio/mpeg"

        async def read(self):
            return b"ID3\x04\x00\x00\x00\x00\x00\x21fake-mp3-payload"

    def fake_convert(audio_bytes: bytes, source_format: str) -> bytes:
        assert source_format == "mp3"
        assert audio_bytes.startswith(b"ID3")
        return b"RIFF1234WAVE5678"

    class FakeClient:
        async def speech_to_text_short(
            self,
            audio_bytes,
            audio_format,
            user_id,
            punctuation,
            chinese2digital,
            end_vad_time,
        ):
            assert audio_format == "wav"
            assert audio_bytes[:4] == b"RIFF"
            assert audio_bytes[8:12] == b"WAVE"
            assert user_id == "u1"
            assert punctuation == 1
            assert chinese2digital == 1
            assert end_vad_time == 1800
            return {"text": "转换后识别", "sid": "sid-1", "requestId": "req-1", "segments": []}

    monkeypatch.setattr(ai_service, "_convert_audio_to_wav_16k_mono", fake_convert)
    monkeypatch.setattr(ai_service, "get_minimax_client", lambda: FakeClient())

    result = asyncio.run(
        ai_service.speech_to_text_short_service(
            user_id="u1",
            file=FakeUpload(),
            punctuation=1,
            chinese2digital=1,
            end_vad_time=1800,
        )
    )

    assert result["text"] == "转换后识别"


def test_speech_to_text_short_service_rejects_unknown_octet_stream():
    from app.ai import service as ai_service

    class FakeUpload:
        filename = "voice.bin"
        content_type = "application/octet-stream"

        async def read(self):
            return b"\x00\x11\x22\x33\x44\x55\x66\x77"

    with pytest.raises(Exception, match="仅支持 wav/pcm"):
        asyncio.run(
            ai_service.speech_to_text_short_service(
                user_id="u1",
                file=FakeUpload(),
            )
        )


def test_understand_image_text_with_local_upload_url(monkeypatch):
    from app.ai import service as ai_service

    monkeypatch.setattr(ai_service.settings, "VIVO_VISION_ENABLED", True)
    monkeypatch.setattr(ai_service.settings, "VIVO_APP_KEY", "test-key")
    monkeypatch.setattr(ai_service.settings, "VIVO_VISION_TIMEOUT_SEC", 5)

    upload_root = Path(ai_service.settings.UPLOAD_DIR)
    image_path = upload_root / "test-user" / "diary-image" / "ark-local-path.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"fake-image-bytes")

    captured = {"image_input": ""}

    async def fake_call(image_input: str, _prompt: str):
        captured["image_input"] = image_input
        return {"output_text": "识别结果"}

    monkeypatch.setattr(ai_service, "_call_ark_vision_async", fake_call)

    result = asyncio.run(
        ai_service.understand_image_text(
            image_url="/uploads/test-user/diary-image/ark-local-path.jpg",
            prompt="请描述图片",
        )
    )

    assert result == "识别结果"
    assert captured["image_input"].startswith("data:image/jpeg;base64,")
    assert captured["image_input"].endswith("ZmFrZS1pbWFnZS1ieXRlcw==")


def test_understand_images_batch_uses_multi_image_input(monkeypatch):
    from app.ai import service as ai_service

    monkeypatch.setattr(ai_service.settings, "VIVO_VISION_ENABLED", True)
    monkeypatch.setattr(ai_service.settings, "VIVO_APP_KEY", "test-key")
    monkeypatch.setattr(ai_service.settings, "VIVO_VISION_TIMEOUT_SEC", 5)
    monkeypatch.setattr(ai_service.settings, "VIVO_VISION_PROMPT", "请客观描述图片")

    ai_service.clear_image_understand_cache()

    captured = {"image_inputs": [], "prompt": ""}

    async def fake_multi(image_inputs, prompt):
        captured["image_inputs"] = list(image_inputs)
        captured["prompt"] = prompt
        return {"output_text": '["多图结果A", "多图结果B"]'}

    async def fail_single(*_args, **_kwargs):
        raise AssertionError("multi-image path should not fallback to single-image call")

    monkeypatch.setattr(ai_service, "_call_ark_vision_multi_async", fake_multi)
    monkeypatch.setattr(ai_service, "understand_image_text", fail_single)

    results = asyncio.run(
        ai_service.understand_images_batch(
            image_urls=[
                "https://example.com/multi-1.jpg",
                "https://example.com/multi-2.jpg",
            ],
            prompt="请描述每张图",
            timeout_sec=5,
            max_images=5,
        )
    )

    assert len(captured["image_inputs"]) == 2
    assert captured["image_inputs"][0] == "https://example.com/multi-1.jpg"
    assert captured["image_inputs"][1] == "https://example.com/multi-2.jpg"
    assert "JSON 数组" in captured["prompt"]

    assert results == ["多图结果A", "多图结果B"]


def test_extract_emotion_mock_prefers_keyword_signal():
    client = MiniMaxClient(
        api_key="test-key",
        api_base="https://example.com",
        model="mock-model",
        mock=True,
    )

    result = asyncio.run(client.extract_emotion("今天真的很想哭，感觉好难受"))
    assert result["label"] == "难过"
    assert result["emoji"] == "😢"
    assert 0 <= float(result["score"]) <= 1


def test_extract_emotion_non_mock_normalizes_json_and_label(monkeypatch):
    client = MiniMaxClient(
        api_key="test-key",
        api_base="https://example.com",
        model="test-model",
        mock=False,
    )

    async def fake_chat_completion(*_args, **_kwargs):
        return """```json
{\"label\": \"悲伤\", \"score\": 85}
```"""

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)

    result = asyncio.run(client.extract_emotion("想哭"))
    assert result["label"] == "难过"
    assert result["emoji"] == "😢"
    assert result["score"] == 0.85

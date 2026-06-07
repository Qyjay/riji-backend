import asyncio
import json

from tests.conftest import create_test_user, get_auth_header


def test_llm_model_crud_and_default_setting(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/ai/models", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {item["id"] for item in data["items"]} >= {
        "builtin:vivo",
        "builtin:minimax",
        "builtin:ark:deepseekv4-flash",
        "builtin:ark:deepseekv4-pro",
        "builtin:ark:doubao-mini",
        "builtin:ark:glm-4.7",
    }

    create_resp = client.post(
        "/api/ai/models",
        json={
            "name": "My GPT",
            "providerType": "openai_compatible",
            "baseUrl": "https://example.com/v1",
            "model": "gpt-test",
            "apiKey": "sk-secret",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    created = create_resp.json()["data"]
    assert created["name"] == "My GPT"
    assert created["hasApiKey"] is True
    assert "apiKey" not in created

    update_resp = client.put(
        f"/api/ai/models/{created['id']}",
        json={"name": "My GPT Updated", "model": "gpt-test-2"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["name"] == "My GPT Updated"
    assert updated["hasApiKey"] is True

    settings_resp = client.post(
        "/api/user/settings",
        json={"chat_model_id": created["id"]},
        headers=headers,
    )
    assert settings_resp.status_code == 200
    assert settings_resp.json()["data"]["chatModelId"] == created["id"]

    delete_resp = client.delete(f"/api/ai/models/{created['id']}", headers=headers)
    assert delete_resp.status_code == 200
    after_delete = client.get("/api/ai/models", headers=headers).json()["data"]
    assert created["id"] not in {item["id"] for item in after_delete["items"]}


def test_chat_non_stream_uses_auto_routed_model(client, monkeypatch):
    from app.ai import model_service

    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])
    captured = {}

    class FakeClient:
        async def chat_completion(self, messages, system_prompt="", temperature=0.8, max_tokens=2048):
            captured["messages"] = messages
            return "ok from selected model"

    def fake_resolve(db, user_id, model_id):
        captured["model_id"] = model_id
        return FakeClient(), model_id

    monkeypatch.setattr(model_service, "resolve_chat_client", fake_resolve)
    monkeypatch.setattr("app.chat.router.ingest_session_memory_snapshot", lambda *_args, **_kwargs: None)

    resp = client.post(
        "/api/chat",
        json={"message": "hello", "modelId": "custom-model-id"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == "ok from selected model"
    assert captured["model_id"] == model_service.BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID


def test_chat_queue_status_contract(client):
    user_data = create_test_user(client, username="chat_queue_status")
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/chat/queue-status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["globalLimit"] == 20
    assert data["queuedCount"] >= 0
    assert data["modelLimits"]["builtin:ark:deepseekv4-flash"] == 5
    assert data["modelLimits"]["builtin:ark:doubao-mini"] == 10
    assert data["modelLimits"]["builtin:ark:glm-4.7"] == 5


def test_chat_model_queue_routes_by_priority_and_fifo():
    from app.chat.ai_queue import ChatModelQueue

    async def run_case():
        queue = ChatModelQueue((("flash", 1), ("doubao", 2), ("glm", 1)), global_limit=4)
        lease1 = await queue.acquire()
        lease2 = await queue.acquire()
        lease3 = await queue.acquire()
        lease4 = await queue.acquire()
        assert [lease1.model_id, lease2.model_id, lease3.model_id, lease4.model_id] == [
            "flash",
            "doubao",
            "doubao",
            "glm",
        ]

        pending = asyncio.create_task(queue.acquire())
        await asyncio.sleep(0)
        snapshot = await queue.snapshot()
        assert snapshot.queued_count == 1
        assert snapshot.active_total == 4

        await lease1.release()
        lease5 = await asyncio.wait_for(pending, timeout=1)
        assert lease5.model_id == "flash"
        snapshot = await queue.snapshot()
        assert snapshot.queued_count == 0
        assert snapshot.active_total == 4

        for lease in [lease2, lease3, lease4, lease5]:
            await lease.release()
        snapshot = await queue.snapshot()
        assert snapshot.active_total == 0

    asyncio.run(run_case())


def test_chat_model_queue_skips_deepseek_for_image_requests():
    from app.chat.ai_queue import ChatModelQueue

    async def run_case():
        queue = ChatModelQueue((("flash", 1), ("doubao", 1), ("glm", 0)), global_limit=2)

        image_lease = await queue.acquire(skip_model_ids={"flash"})
        assert image_lease.model_id == "doubao"

        text_lease = await queue.acquire()
        assert text_lease.model_id == "flash"

        pending_image = asyncio.create_task(queue.acquire(skip_model_ids={"flash"}))
        await asyncio.sleep(0)
        snapshot = await queue.snapshot()
        assert snapshot.queued_count == 1
        assert snapshot.active_total == 2

        await text_lease.release()
        await asyncio.sleep(0)
        snapshot = await queue.snapshot()
        assert snapshot.queued_count == 1
        assert snapshot.active_total == 1

        await image_lease.release()
        next_image_lease = await asyncio.wait_for(pending_image, timeout=1)
        assert next_image_lease.model_id == "doubao"

        await next_image_lease.release()
        snapshot = await queue.snapshot()
        assert snapshot.queued_count == 0
        assert snapshot.active_total == 0

    asyncio.run(run_case())


def test_chat_message_image_attachment_becomes_multimodal_payload(monkeypatch):
    from app.chat.service import message_to_ai_payload
    from app.models.chat import ChatMessage

    monkeypatch.setattr(
        "app.ai.service._resolve_ark_image_input",
        lambda url: "data:image/png;base64,ZmFrZQ==",
    )
    message = ChatMessage(
        id="msg-image",
        user_id="user-1",
        role="user",
        content="看看这张图",
        timestamp=1,
        session_id="session-1",
        attachments=json.dumps(
            [
                {
                    "type": "image",
                    "name": "test.png",
                    "url": "/uploads/user-1/diary-image/test.png",
                    "mime_type": "image/png",
                }
            ],
            ensure_ascii=False,
        ),
    )

    payload = message_to_ai_payload(message, multimodal=True)

    assert payload["role"] == "user"
    assert payload["content"] == [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
        },
        {"type": "text", "text": "看看这张图"},
    ]

    text_payload = message_to_ai_payload(message)
    assert text_payload["content"] == "[用户上传了图片：test.png]\n看看这张图"


def test_custom_openai_payload(monkeypatch):
    from app.ai.model_service import CustomChatModelClient

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "openai ok"}}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.ai.model_service.httpx.AsyncClient", FakeAsyncClient)

    client = CustomChatModelClient(
        provider_type="openai_compatible",
        base_url="https://example.com/v1",
        model="gpt-test",
        api_key="sk-test",
    )
    result = asyncio.run(client.chat_completion([{"role": "user", "content": "hi"}], system_prompt="sys"))
    assert result == "openai ok"
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["json"]["model"] == "gpt-test"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["json"]["stream"] is False


def test_builtin_ark_deepseek_flash_uses_openai_compatible_payload(monkeypatch):
    from app.ai import model_service

    captured = {}
    monkeypatch.setattr(model_service.settings, "ARK_API_KEY", "ark-test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ark ok"}}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.ai.model_service.httpx.AsyncClient", FakeAsyncClient)

    client = model_service._builtin_client(model_service.BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID)
    result = asyncio.run(client.chat_completion([{"role": "user", "content": "hi"}], system_prompt="sys"))

    assert result == "ark ok"
    assert captured["url"] == "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer ark-test-key"
    assert captured["json"]["model"] == "ep-20260603141535-z2l7c"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "sys"}


def test_builtin_ark_new_models_use_configured_endpoints(monkeypatch):
    from app.ai import model_service

    captured = []
    monkeypatch.setattr(model_service.settings, "ARK_API_KEY", "ark-test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ark ok"}}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            captured.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("app.ai.model_service.httpx.AsyncClient", FakeAsyncClient)

    cases = [
        (model_service.BUILTIN_ARK_DOUBAO_MINI_ID, "ep-20260607122404-2m67p"),
        (model_service.BUILTIN_ARK_GLM_4_7_ID, "ep-20260607122957-8jtq2"),
    ]
    for model_id, endpoint in cases:
        client = model_service._builtin_client(model_id)
        result = asyncio.run(client.chat_completion([{"role": "user", "content": "hi"}]))
        assert result == "ark ok"
        assert captured[-1]["url"] == "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        assert captured[-1]["headers"]["Authorization"] == "Bearer ark-test-key"
        assert captured[-1]["json"]["model"] == endpoint


def test_custom_anthropic_payload(monkeypatch):
    from app.ai.model_service import CustomChatModelClient

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"content": [{"type": "text", "text": "anthropic ok"}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.ai.model_service.httpx.AsyncClient", FakeAsyncClient)

    client = CustomChatModelClient(
        provider_type="anthropic_compatible",
        base_url="https://example.com/v1",
        model="claude-test",
        api_key="sk-ant",
    )
    result = asyncio.run(client.chat_completion([{"role": "user", "content": "hi"}], system_prompt="sys"))
    assert result == "anthropic ok"
    assert captured["url"] == "https://example.com/v1/messages"
    assert captured["json"]["model"] == "claude-test"
    assert captured["json"]["system"] == "sys"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["json"]["stream"] is False

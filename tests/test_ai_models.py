import asyncio

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


def test_chat_non_stream_passes_model_id(client, monkeypatch):
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
    assert captured["model_id"] == "custom-model-id"


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

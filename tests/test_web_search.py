import asyncio


def test_volcengine_web_search_payload_and_parse(monkeypatch):
    from app.chat.web_search import search_web_for_chat
    from app.config import settings

    captured = {}
    originals = {
        "WEB_SEARCH_PROVIDER": settings.WEB_SEARCH_PROVIDER,
        "VOLC_SEARCH_ENABLED": settings.VOLC_SEARCH_ENABLED,
        "VOLC_SEARCH_API_KEY": settings.VOLC_SEARCH_API_KEY,
        "VOLC_SEARCH_API_BASE": settings.VOLC_SEARCH_API_BASE,
        "VOLC_SEARCH_NUM_RESULTS": settings.VOLC_SEARCH_NUM_RESULTS,
        "VOLC_SEARCH_TIME_RANGE": settings.VOLC_SEARCH_TIME_RANGE,
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "ResponseMetadata": {"Error": None},
                "Result": {
                    "WebResults": [
                        {
                            "Title": "火山搜索文档",
                            "Url": "https://www.volcengine.com/docs/87772/2272953",
                            "Summary": "联网搜索 API Key 接入说明",
                            "PublishTime": "2026-05-01",
                        }
                    ]
                },
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.chat.web_search.httpx.AsyncClient", FakeAsyncClient)
    settings.WEB_SEARCH_PROVIDER = "volcengine"
    settings.VOLC_SEARCH_ENABLED = True
    settings.VOLC_SEARCH_API_KEY = "test-key"
    settings.VOLC_SEARCH_API_BASE = "https://open.feedcoopapi.com/search_api/web_search"
    settings.VOLC_SEARCH_NUM_RESULTS = 3
    settings.VOLC_SEARCH_TIME_RANGE = "OneYear"
    try:
        attachments, context = asyncio.run(search_web_for_chat("北京周末去哪玩"))
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)

    assert captured["url"] == "https://open.feedcoopapi.com/search_api/web_search"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["Query"] == "北京周末去哪玩"
    assert captured["json"]["SearchType"] == "web"
    assert captured["json"]["Count"] == 3
    assert captured["json"]["NeedSummary"] is True
    assert attachments[0]["source"] == "volcengine"
    assert attachments[0]["name"] == "火山搜索文档"
    assert attachments[0]["url"] == "https://www.volcengine.com/docs/87772/2272953"
    assert "联网搜索 API Key 接入说明" in context


def test_volcengine_web_search_missing_key_skips(monkeypatch):
    from app.chat.web_search import search_web_for_chat
    from app.config import settings

    originals = {
        "WEB_SEARCH_PROVIDER": settings.WEB_SEARCH_PROVIDER,
        "VOLC_SEARCH_ENABLED": settings.VOLC_SEARCH_ENABLED,
        "VOLC_SEARCH_API_KEY": settings.VOLC_SEARCH_API_KEY,
    }
    settings.WEB_SEARCH_PROVIDER = "volcengine"
    settings.VOLC_SEARCH_ENABLED = True
    settings.VOLC_SEARCH_API_KEY = ""
    try:
        attachments, context = asyncio.run(search_web_for_chat("不会实际请求"))
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)

    assert attachments == []
    assert context == ""

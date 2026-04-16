"""记忆向量索引 provider 测试。"""

from app.config import settings
from app.memory import indexer


def test_dashscope_embedding_uses_openai_compatible_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": [
                        {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                        {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    ]
                }

        return FakeResponse()

    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_PROVIDER", "dashscope")
    monkeypatch.setattr(settings, "DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "DASHSCOPE_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setattr(settings, "DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_DIMENSIONS", 1024)
    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_TIMEOUT_SEC", 12)
    monkeypatch.setattr(indexer.httpx, "post", fake_post)

    embeddings = indexer._embed_texts(["第一条记忆", "第二条记忆"])

    assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert captured["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"] == {
        "model": "text-embedding-v4",
        "input": ["第一条记忆", "第二条记忆"],
        "encoding_format": "float",
        "dimensions": 1024,
    }
    assert captured["timeout"] == 12


def test_hash_embedding_remains_default(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_PROVIDER", "hash")

    first = indexer._embed_texts(["夜跑让我开心"])[0]
    second = indexer._embed_texts(["夜跑让我开心"])[0]

    assert first == second
    assert len(first) == 64

"""记忆向量索引 provider 测试。"""
from pathlib import Path

from app.config import settings
from app.memory import indexer
from app.memory.service import create_memory_document


def _reset_indexer_cache():
    indexer._COLLECTION = None
    indexer._COLLECTION_KEY = ""


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


def test_vivo_embedding_uses_batch_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, params, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["json"] = json
        captured["timeout"] = timeout

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": [
                        [0.11, 0.22, 0.33],
                        [0.44, 0.55, 0.66],
                    ]
                }

        return FakeResponse()

    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_PROVIDER", "vivo")
    monkeypatch.setattr(settings, "VIVO_APP_KEY", "test-vivo-key")
    monkeypatch.setattr(settings, "VIVO_EMBEDDING_BASE_URL", "https://api-ai.vivo.com.cn")
    monkeypatch.setattr(settings, "VIVO_EMBEDDING_MODEL", "m3e-base")
    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_TIMEOUT_SEC", 15)
    monkeypatch.setattr(indexer.httpx, "post", fake_post)

    embeddings = indexer._embed_texts(["第一条记忆", "第二条记忆"], mode="document")

    assert embeddings == [[0.11, 0.22, 0.33], [0.44, 0.55, 0.66]]
    assert captured["url"] == "https://api-ai.vivo.com.cn/embedding-model-api/predict/batch"
    assert captured["headers"]["Authorization"] == "Bearer test-vivo-key"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert isinstance(captured["params"].get("requestId"), str)
    assert captured["json"] == {
        "model_name": "m3e-base",
        "sentences": ["第一条记忆", "第二条记忆"],
    }
    assert captured["timeout"] == 15


def test_vivo_embedding_bge_query_auto_adds_instruction(monkeypatch):
    captured = {}

    def fake_post(_url, *, headers, params, json, timeout):
        captured["headers"] = headers
        captured["params"] = params
        captured["json"] = json
        captured["timeout"] = timeout

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [[0.1, 0.2, 0.3]]}

        return FakeResponse()

    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_PROVIDER", "vivo")
    monkeypatch.setattr(settings, "VIVO_APP_KEY", "test-vivo-key")
    monkeypatch.setattr(settings, "VIVO_EMBEDDING_MODEL", "bge-base-zh-v1.5")
    monkeypatch.setattr(settings, "VIVO_EMBEDDING_QUERY_INSTRUCTION", "为这个句子生成表示以用于检索相关文章：")
    monkeypatch.setattr(indexer.httpx, "post", fake_post)

    embeddings = indexer._embed_texts(["地铁交通"], mode="query")

    assert embeddings == [[0.1, 0.2, 0.3]]
    assert captured["json"] == {
        "model_name": "bge-base-zh-v1.5",
        "sentences": ["为这个句子生成表示以用于检索相关文章：地铁交通"],
    }


def test_real_vector_index_roundtrip_with_hash_provider(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_VECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setattr(settings, "MEMORY_DIR", str(Path(tmp_path) / "memory_store"))
    _reset_indexer_cache()

    try:
        create_memory_document(
            db,
            user_id="user-1",
            source_type="diary",
            source_id="diary-vector-1",
            title="夜跑日记",
            content="我最近喜欢晚上夜跑，跑完会去操场散步。",
            visibility="private",
        )
        db.commit()

        hits = indexer.search_index("user-1", "夜跑 散步", top_k=3)
        status = indexer.get_vector_backend_status()

        assert hits, "真实向量索引写入后应能检索到结果"
        assert hits[0]["metadata"]["source_type"] == "diary"
        assert "夜跑" in hits[0]["content"]
        assert status["collectionReady"] is True
        assert status["indexedCount"] >= 1
    finally:
        _reset_indexer_cache()

"""向量索引抽象。

默认 no-op；当 MEMORY_VECTOR_ENABLED=true 且安装 chromadb 时使用本地 ChromaDB。
Embedding provider 可配置：
- hash：deterministic hash，方便本地开发和回归测试。
- dashscope：通过阿里云百炼 OpenAI-compatible 接口调用 text-embedding-v4。
- vivo：通过 VIVO embedding-model-api/predict/batch 接口调用 m3e-base / bge-base-zh-v1.5。
"""
import hashlib
import os
import re
from typing import TypedDict
from uuid import uuid4

import httpx

from app.config import settings
from app.models.memory import MemoryChunk


class MemoryIndexHit(TypedDict):
    chunk_id: str
    document_id: str
    content: str
    score: float
    metadata: dict


_COLLECTION = None
_COLLECTION_KEY = ""
_VECTOR_DIM = 64
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}")


def _vector_enabled() -> bool:
    return bool(getattr(settings, "MEMORY_VECTOR_ENABLED", False))


def _embedding_provider() -> str:
    return str(getattr(settings, "MEMORY_EMBEDDING_PROVIDER", "hash") or "hash").strip().lower()


def _embedding_dimensions() -> int:
    raw = int(getattr(settings, "MEMORY_EMBEDDING_DIMENSIONS", 1024) or 1024)
    allowed = {64, 128, 256, 512, 768, 1024, 1536, 2048}
    return raw if raw in allowed else 1024


def _embedding_batch_size() -> int:
    # 为外部 embedding provider 统一限制批量，避免一次请求过大。
    raw = int(getattr(settings, "MEMORY_EMBEDDING_BATCH_SIZE", 10) or 10)
    return max(1, min(raw, 10))


def _hash_embedding(text: str) -> list[float]:
    values = [0.0] * _VECTOR_DIM
    raw_text = str(text or "").lower()
    tokens = _TOKEN_RE.findall(raw_text) or raw_text.split() or [raw_text]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for idx, byte in enumerate(digest):
            values[idx % _VECTOR_DIM] += (byte / 255.0) - 0.5
    norm = sum(value * value for value in values) ** 0.5 or 1.0
    return [value / norm for value in values]


def _dashscope_base_url() -> str:
    base_url = str(
        getattr(settings, "DASHSCOPE_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ).rstrip("/")
    return base_url


def _dashscope_embed_batch(texts: list[str]) -> list[list[float]]:
    api_key = str(getattr(settings, "DASHSCOPE_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is required when MEMORY_EMBEDDING_PROVIDER=dashscope")

    payload = {
        "model": getattr(settings, "DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4"),
        "input": texts,
        "encoding_format": "float",
        "dimensions": _embedding_dimensions(),
    }
    timeout = float(getattr(settings, "MEMORY_EMBEDDING_TIMEOUT_SEC", 30) or 30)
    response = httpx.post(
        f"{_dashscope_base_url()}/embeddings",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    embeddings = [None] * len(texts)
    for item in data.get("data", []):
        index = int(item.get("index", 0))
        if 0 <= index < len(embeddings):
            embeddings[index] = item.get("embedding")
    if any(embedding is None for embedding in embeddings):
        raise RuntimeError("DashScope embedding response is missing one or more embeddings")
    return embeddings  # type: ignore[return-value]


def _vivo_embedding_base_url() -> str:
    base_url = str(
        getattr(settings, "VIVO_EMBEDDING_BASE_URL", "https://api-ai.vivo.com.cn")
        or "https://api-ai.vivo.com.cn"
    ).rstrip("/")
    return base_url


def _vivo_embedding_model() -> str:
    return str(getattr(settings, "VIVO_EMBEDDING_MODEL", "m3e-base") or "m3e-base").strip()


def _vivo_query_instruction() -> str:
    return str(
        getattr(settings, "VIVO_EMBEDDING_QUERY_INSTRUCTION", "为这个句子生成表示以用于检索相关文章：")
        or "为这个句子生成表示以用于检索相关文章："
    )


def _vivo_prepare_texts(texts: list[str], mode: str) -> list[str]:
    model_name = _vivo_embedding_model().lower()
    if model_name != "bge-base-zh-v1.5" or mode != "query":
        return texts

    prefix = _vivo_query_instruction()
    prepared: list[str] = []
    for text in texts:
        sentence = str(text or "")
        if sentence.startswith(prefix):
            prepared.append(sentence)
        else:
            prepared.append(f"{prefix}{sentence}")
    return prepared


def _vivo_embed_batch(texts: list[str], mode: str = "document") -> list[list[float]]:
    api_key = str(getattr(settings, "VIVO_APP_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("VIVO_APP_KEY is required when MEMORY_EMBEDDING_PROVIDER=vivo")

    request_id = str(uuid4())
    payload = {
        "model_name": _vivo_embedding_model(),
        "sentences": _vivo_prepare_texts(texts, mode=mode),
    }
    timeout = float(getattr(settings, "MEMORY_EMBEDDING_TIMEOUT_SEC", 30) or 30)
    response = httpx.post(
        f"{_vivo_embedding_base_url()}/embedding-model-api/predict/batch",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        params={"requestId": request_id},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    embeddings = data.get("data", [])
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise RuntimeError("VIVO embedding response is missing one or more embeddings")
    return embeddings  # type: ignore[return-value]


def _embed_texts(texts: list[str], mode: str = "document") -> list[list[float]]:
    provider = _embedding_provider()
    if provider == "dashscope":
        embeddings: list[list[float]] = []
        batch_size = _embedding_batch_size()
        for idx in range(0, len(texts), batch_size):
            batch = texts[idx: idx + batch_size]
            embeddings.extend(_dashscope_embed_batch(batch))
        return embeddings
    if provider == "vivo":
        embeddings = []
        batch_size = _embedding_batch_size()
        for idx in range(0, len(texts), batch_size):
            batch = texts[idx: idx + batch_size]
            embeddings.extend(_vivo_embed_batch(batch, mode=mode))
        return embeddings
    return [_hash_embedding(text) for text in texts]


def _collection_name() -> str:
    provider = _embedding_provider()
    if provider == "dashscope":
        return f"riji_memory_chunks_dashscope_{_embedding_dimensions()}"
    if provider == "vivo":
        model_name = _vivo_embedding_model().lower().replace("-", "_").replace(".", "_")
        return f"riji_memory_chunks_vivo_{model_name}"
    return "riji_memory_chunks_hash"


def _collection_cache_key() -> str:
    memory_dir = os.path.abspath(str(getattr(settings, "MEMORY_DIR", ".memory") or ".memory"))
    return f"{memory_dir}::{_collection_name()}"


def _get_collection():
    global _COLLECTION, _COLLECTION_KEY
    collection_name = _collection_name()
    cache_key = _collection_cache_key()
    if _COLLECTION is not None and _COLLECTION_KEY == cache_key:
        return _COLLECTION
    if not _vector_enabled():
        return None
    try:
        import chromadb
    except Exception:
        return None
    base_dir = getattr(settings, "MEMORY_DIR", ".memory")
    os.makedirs(base_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=os.path.join(base_dir, "chroma"))
    _COLLECTION = client.get_or_create_collection(name=collection_name)
    _COLLECTION_KEY = cache_key
    return _COLLECTION


def index_chunks(user_id: str, chunks: list[MemoryChunk]) -> None:
    collection = _get_collection()
    if not collection or not chunks:
        return None
    texts = [chunk.content or "" for chunk in chunks]
    collection.upsert(
        ids=[chunk.id for chunk in chunks],
        documents=texts,
        embeddings=_embed_texts(texts, mode="document"),
        metadatas=[
            {
                "user_id": user_id,
                "document_id": chunk.document_id,
                "chunk_id": chunk.id,
                "source_type": chunk.source_type or "",
                "source_id": chunk.source_id or "",
                "visibility": chunk.visibility or "private",
            }
            for chunk in chunks
        ],
    )
    return None


def delete_document_index(user_id: str, document_id: str) -> None:
    collection = _get_collection()
    if not collection:
        return None
    collection.delete(where={"$and": [{"user_id": user_id}, {"document_id": document_id}]})
    return None


def search_index(user_id: str, query: str, top_k: int) -> list[MemoryIndexHit]:
    collection = _get_collection()
    if not collection:
        return []
    result = collection.query(
        query_embeddings=_embed_texts([query], mode="query"),
        n_results=max(1, top_k),
        where={"user_id": user_id},
    )
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    hits: list[MemoryIndexHit] = []
    for idx, chunk_id in enumerate(ids):
        metadata = metadatas[idx] or {}
        distance = float(distances[idx]) if idx < len(distances) else 1.0
        hits.append(
            {
                "chunk_id": chunk_id,
                "document_id": str(metadata.get("document_id") or ""),
                "content": documents[idx] if idx < len(documents) else "",
                "score": round(1.0 / (1.0 + max(distance, 0.0)), 4),
                "metadata": metadata,
            }
        )
    return hits


def get_vector_backend_status() -> dict:
    """检查向量索引后端是否可用（不触发真实 embedding 请求）。"""
    vector_enabled = _vector_enabled()
    chromadb_importable = False
    chromadb_error = ""
    collection_ready = False
    indexed_count = 0
    if vector_enabled:
        try:
            import chromadb  # noqa: F401

            chromadb_importable = True
        except Exception as exc:
            chromadb_error = str(exc)
    if vector_enabled and chromadb_importable:
        collection = _get_collection()
        collection_ready = collection is not None
        if collection_ready:
            try:
                indexed_count = int(collection.count() or 0)
            except Exception:
                indexed_count = 0

    memory_dir = os.path.abspath(getattr(settings, "MEMORY_DIR", ".memory"))
    return {
        "vectorEnabled": vector_enabled,
        "chromadbImportable": chromadb_importable,
        "chromadbError": chromadb_error,
        "collectionReady": collection_ready,
        "collectionName": _collection_name(),
        "memoryDir": memory_dir,
        "indexedCount": indexed_count,
    }


def get_embedding_status() -> dict:
    """检查 embedding provider 配置是否满足最低可用条件。"""
    provider = _embedding_provider()
    available = True
    reason = ""
    if provider == "dashscope":
        api_key = str(getattr(settings, "DASHSCOPE_API_KEY", "") or "").strip()
        available = bool(api_key)
        reason = "DASHSCOPE_API_KEY is missing" if not available else ""
    elif provider == "vivo":
        api_key = str(getattr(settings, "VIVO_APP_KEY", "") or "").strip()
        available = bool(api_key)
        reason = "VIVO_APP_KEY is missing" if not available else ""
    elif provider == "hash":
        available = True
    else:
        available = False
        reason = f"Unsupported embedding provider: {provider}"

    return {
        "provider": provider,
        "available": available,
        "reason": reason,
        "dimensions": _embedding_dimensions(),
        "batchSize": _embedding_batch_size(),
    }

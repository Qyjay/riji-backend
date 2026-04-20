"""记忆检索。第一阶段提供 SQLite fallback，后续可接向量库。"""
import re
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.memory.permissions import allowed_visibilities_for_scenario
from app.models.memory import MemoryChunk, MemoryDocument

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}")


def _tokens(text: str) -> list[str]:
    return list(dict.fromkeys(_TOKEN_RE.findall(str(text or "").lower())))[:12]


def _score_chunk(chunk: MemoryChunk, query_tokens: list[str]) -> float:
    content = (chunk.content or "").lower()
    if not query_tokens:
        return 0.1
    hits = sum(1 for token in query_tokens if token in content)
    return hits / max(len(query_tokens), 1)


def retrieve_memories(
    db: Session,
    *,
    user_id: str,
    query: str,
    scenario: str,
    top_k: Optional[int] = None,
    source_types: Optional[list[str]] = None,
) -> list[dict]:
    """检索当前场景可用的记忆片段。"""
    if not getattr(settings, "MEMORY_ENABLED", True):
        return []

    limit = top_k or getattr(settings, "MEMORY_TOP_K", 6)
    visibilities = allowed_visibilities_for_scenario(scenario)
    query_tokens = _tokens(query)

    if getattr(settings, "MEMORY_VECTOR_ENABLED", False):
        try:
            from app.memory.indexer import search_index

            vector_hits = search_index(user_id, query, max(limit * 4, limit))
            filtered_hits = []
            for hit in vector_hits:
                metadata = hit.get("metadata", {})
                visibility = metadata.get("visibility") or "private"
                source_type = metadata.get("source_type") or ""
                if visibility not in visibilities:
                    continue
                if source_types and source_type not in source_types:
                    continue
                filtered_hits.append(
                    {
                        "chunk_id": hit["chunk_id"],
                        "document_id": hit["document_id"],
                        "source_type": source_type,
                        "source_id": metadata.get("source_id") or "",
                        "title": "",
                        "content": hit["content"],
                        "summary": "",
                        "visibility": visibility,
                        "score": hit["score"],
                        "occurred_at": 0,
                    }
                )
            if filtered_hits:
                return filtered_hits[:limit]
        except Exception:
            pass

    chunk_query = (
        db.query(MemoryChunk, MemoryDocument)
        .join(MemoryDocument, MemoryChunk.document_id == MemoryDocument.id)
        .filter(
            MemoryChunk.user_id == user_id,
            MemoryChunk.visibility.in_(visibilities),
            MemoryDocument.is_deleted == False,  # noqa: E712
        )
    )
    if source_types:
        chunk_query = chunk_query.filter(MemoryChunk.source_type.in_(source_types))

    if query_tokens:
        filters = [MemoryChunk.content.ilike(f"%{token}%") for token in query_tokens[:6]]
        rows = chunk_query.filter(or_(*filters)).order_by(MemoryDocument.occurred_at.desc()).limit(limit * 5).all()
    else:
        rows = chunk_query.order_by(MemoryDocument.occurred_at.desc()).limit(limit).all()

    scored = []
    for chunk, document in rows:
        score = _score_chunk(chunk, query_tokens)
        recency_boost = 0.05 if document.occurred_at else 0.0
        scored.append((score + recency_boost, chunk, document))

    scored.sort(key=lambda item: (item[0], item[2].occurred_at), reverse=True)
    hits = []
    for score, chunk, document in scored[:limit]:
        hits.append(
            {
                "chunk_id": chunk.id,
                "document_id": document.id,
                "source_type": document.source_type,
                "source_id": document.source_id,
                "title": document.title or "",
                "content": chunk.content or "",
                "summary": document.summary or "",
                "visibility": chunk.visibility,
                "score": round(float(score), 4),
                "occurred_at": document.occurred_at,
            }
        )
    return hits


def retrieve_shared_memories(
    db: Session,
    *,
    owner_user_id: str,
    query: str,
    scenario: str,
    top_k: Optional[int] = None,
    source_types: Optional[list[str]] = None,
    viewer_school: Optional[str] = None,
    owner_school: Optional[str] = None,
) -> list[dict]:
    """检索某个用户允许共享给当前场景的记忆片段。"""
    visibilities = list(allowed_visibilities_for_scenario(scenario))
    if "school" in visibilities and (viewer_school or "") != (owner_school or ""):
        visibilities = [item for item in visibilities if item != "school"]
    if not visibilities:
        return []

    limit = top_k or getattr(settings, "MEMORY_TOP_K", 6)
    query_tokens = _tokens(query)
    chunk_query = (
        db.query(MemoryChunk, MemoryDocument)
        .join(MemoryDocument, MemoryChunk.document_id == MemoryDocument.id)
        .filter(
            MemoryChunk.user_id == owner_user_id,
            MemoryChunk.visibility.in_(visibilities),
            MemoryDocument.is_deleted == False,  # noqa: E712
        )
    )
    if source_types:
        chunk_query = chunk_query.filter(MemoryChunk.source_type.in_(source_types))

    if query_tokens:
        filters = [MemoryChunk.content.ilike(f"%{token}%") for token in query_tokens[:6]]
        rows = chunk_query.filter(or_(*filters)).order_by(MemoryDocument.occurred_at.desc()).limit(limit * 5).all()
    else:
        rows = chunk_query.order_by(MemoryDocument.occurred_at.desc()).limit(limit).all()

    scored = []
    for chunk, document in rows:
        score = _score_chunk(chunk, query_tokens)
        scored.append((score + (0.05 if document.occurred_at else 0.0), chunk, document))

    scored.sort(key=lambda item: (item[0], item[2].occurred_at), reverse=True)
    return [
        {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "source_type": document.source_type,
            "source_id": document.source_id,
            "title": document.title or "",
            "content": chunk.content or "",
            "summary": document.summary or "",
            "visibility": chunk.visibility,
            "score": round(float(score), 4),
            "occurred_at": document.occurred_at,
        }
        for score, chunk, document in scored[:limit]
    ]

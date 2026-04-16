"""记忆系统基础服务。"""
import hashlib
import json
import logging
import time
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.memory.chunker import chunk_text, normalize_text
from app.models.memory import MemoryChunk, MemoryDocument

logger = logging.getLogger("uvicorn.error")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _encode(obj, default="[]") -> str:
    if obj is None:
        return default
    return json.dumps(obj, ensure_ascii=False)


def _decode(raw, default=None):
    if default is None:
        default = []
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def _delete_document_chunks(db: Session, document_id: str) -> None:
    db.query(MemoryChunk).filter(MemoryChunk.document_id == document_id).delete()


def create_memory_document(
    db: Session,
    *,
    user_id: str,
    source_type: str,
    source_id: str,
    content: str,
    title: str = "",
    summary: str = "",
    visibility: str = "private",
    memory_scope: str = "self",
    emotion: Optional[dict] = None,
    tags: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
    occurred_at: Optional[int] = None,
    replace_existing: bool = True,
) -> Optional[MemoryDocument]:
    """创建或更新一条记忆文档，并同步生成 chunks。"""
    if not getattr(settings, "MEMORY_ENABLED", True):
        return None

    normalized = normalize_text(content)
    if not normalized:
        return None

    now = _now_ms()
    occurred = occurred_at or now
    digest = content_hash(normalized)

    document = (
        db.query(MemoryDocument)
        .filter(
            MemoryDocument.user_id == user_id,
            MemoryDocument.source_type == source_type,
            MemoryDocument.source_id == source_id,
        )
        .first()
    )

    if document and document.content_hash == digest and not document.is_deleted:
        return document

    if document and replace_existing:
        _delete_document_chunks(db, document.id)
        document.title = title or document.title or ""
        document.content = normalized
        document.summary = summary or ""
        document.visibility = visibility
        document.memory_scope = memory_scope
        document.emotion = _encode(emotion or {}, "{}")
        document.tags = _encode(tags or [], "[]")
        document.metadata_json = _encode(metadata or {}, "{}")
        document.occurred_at = occurred
        document.updated_at = now
        document.content_hash = digest
        document.is_deleted = False
    elif document:
        return document
    else:
        document = MemoryDocument(
            id=_uuid(),
            user_id=user_id,
            source_type=source_type,
            source_id=source_id,
            title=title or "",
            content=normalized,
            summary=summary or "",
            visibility=visibility,
            memory_scope=memory_scope,
            emotion=_encode(emotion or {}, "{}"),
            tags=_encode(tags or [], "[]"),
            metadata_json=_encode(metadata or {}, "{}"),
            occurred_at=occurred,
            created_at=now,
            updated_at=now,
            content_hash=digest,
            is_deleted=False,
        )
        db.add(document)
        db.flush()

    chunks = chunk_text(
        normalized,
        chunk_size=getattr(settings, "MEMORY_CHUNK_SIZE", 800),
        overlap=getattr(settings, "MEMORY_CHUNK_OVERLAP", 100),
    )
    chunk_rows = []
    for index, chunk in enumerate(chunks):
        chunk_row = MemoryChunk(
            id=_uuid(),
            user_id=user_id,
            document_id=document.id,
            chunk_index=index,
            content=chunk,
            source_type=source_type,
            source_id=source_id,
            visibility=visibility,
            tags=_encode(tags or [], "[]"),
            importance_score=0.5,
            embedding_ref="",
            created_at=now,
        )
        chunk_rows.append(chunk_row)
        db.add(chunk_row)

    try:
        from app.memory.indexer import index_chunks

        index_chunks(user_id, chunk_rows)
    except Exception as exc:
        # 向量索引失败不能阻塞主业务写入，但必须留下可排查日志。
        logger.warning(
            "[memory] vector indexing failed: user_id=%s document_id=%s source_type=%s "
            "source_id=%s chunks=%s provider=%s error=%s",
            user_id,
            document.id,
            source_type,
            source_id,
            len(chunk_rows),
            getattr(settings, "MEMORY_EMBEDDING_PROVIDER", "hash"),
            str(exc),
            exc_info=True,
        )

    return document


def list_memory_documents(
    db: Session,
    user_id: str,
    *,
    source_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[MemoryDocument]:
    query = db.query(MemoryDocument).filter(
        MemoryDocument.user_id == user_id,
        MemoryDocument.is_deleted == False,  # noqa: E712
    )
    if source_type:
        query = query.filter(MemoryDocument.source_type == source_type)
    return query.order_by(MemoryDocument.occurred_at.desc()).offset(offset).limit(limit).all()


def get_memory_document(db: Session, user_id: str, document_id: str) -> Optional[MemoryDocument]:
    return (
        db.query(MemoryDocument)
        .filter(
            MemoryDocument.id == document_id,
            MemoryDocument.user_id == user_id,
            MemoryDocument.is_deleted == False,  # noqa: E712
        )
        .first()
    )


def soft_delete_memory_document(db: Session, user_id: str, document_id: str) -> bool:
    document = get_memory_document(db, user_id, document_id)
    if not document:
        return False
    document.is_deleted = True
    document.updated_at = _now_ms()
    _delete_document_chunks(db, document.id)
    try:
        from app.memory.indexer import delete_document_index

        delete_document_index(user_id, document.id)
    except Exception:
        pass
    return True

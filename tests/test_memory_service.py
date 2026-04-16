"""记忆 service 测试。"""
import logging

from app.memory.service import (
    create_memory_document,
    get_memory_document,
    list_memory_documents,
    soft_delete_memory_document,
)
from app.models.memory import MemoryChunk, MemoryDocument


def test_create_memory_document_creates_document_and_chunks(db):
    document = create_memory_document(
        db,
        user_id="user-1",
        source_type="diary",
        source_id="diary-1",
        title="图书馆日记",
        content="今天在图书馆复习高数。\n\n晚上又整理了错题。",
        summary="复习高数和整理错题",
        tags=["学习", "高数"],
        metadata={"date": "2026-04-16"},
    )
    db.commit()

    saved = db.query(MemoryDocument).filter(MemoryDocument.id == document.id).first()
    chunks = db.query(MemoryChunk).filter(MemoryChunk.document_id == document.id).all()

    assert saved is not None
    assert saved.title == "图书馆日记"
    assert saved.source_type == "diary"
    assert len(chunks) >= 1


def test_create_memory_document_is_idempotent_for_same_content(db):
    first = create_memory_document(
        db,
        user_id="user-1",
        source_type="diary",
        source_id="diary-2",
        title="重复内容",
        content="今天心情不错，出去散步了。",
    )
    db.commit()
    first_chunk_ids = [chunk.id for chunk in db.query(MemoryChunk).filter(MemoryChunk.document_id == first.id).all()]

    second = create_memory_document(
        db,
        user_id="user-1",
        source_type="diary",
        source_id="diary-2",
        title="重复内容",
        content="今天心情不错，出去散步了。",
    )
    db.commit()
    second_chunk_ids = [chunk.id for chunk in db.query(MemoryChunk).filter(MemoryChunk.document_id == first.id).all()]

    assert second.id == first.id
    assert second_chunk_ids == first_chunk_ids
    assert db.query(MemoryDocument).count() == 1


def test_list_get_and_soft_delete_memory_document(db):
    doc1 = create_memory_document(
        db,
        user_id="user-1",
        source_type="diary",
        source_id="diary-3",
        title="第一篇",
        content="第一篇内容",
        occurred_at=1000,
    )
    doc2 = create_memory_document(
        db,
        user_id="user-1",
        source_type="chat_session",
        source_id="session-1",
        title="第二篇",
        content="第二篇内容",
        occurred_at=2000,
    )
    db.commit()

    items = list_memory_documents(db, "user-1")
    assert [item.id for item in items] == [doc2.id, doc1.id]

    fetched = get_memory_document(db, "user-1", doc1.id)
    assert fetched is not None
    assert fetched.title == "第一篇"

    deleted = soft_delete_memory_document(db, "user-1", doc1.id)
    db.commit()

    assert deleted is True
    assert get_memory_document(db, "user-1", doc1.id) is None
    assert db.query(MemoryChunk).filter(MemoryChunk.document_id == doc1.id).count() == 0


def test_create_memory_document_logs_vector_index_failure(db, monkeypatch, caplog):
    from app.memory import indexer

    def fail_index_chunks(user_id, chunks):
        raise RuntimeError("embedding api failed")

    monkeypatch.setattr(indexer, "index_chunks", fail_index_chunks)

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        document = create_memory_document(
            db,
            user_id="user-1",
            source_type="material",
            source_id="material-1",
            title="会失败的向量索引",
            content="这条记忆应该进入数据库，但向量索引会失败。",
        )

    assert document is not None
    assert db.query(MemoryDocument).filter(MemoryDocument.id == document.id).first() is not None
    assert "vector indexing failed" in caplog.text
    assert "source_type=material" in caplog.text
    assert "embedding api failed" in caplog.text

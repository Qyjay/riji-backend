"""记忆检索集成测试。"""
from pathlib import Path

from app.config import settings
from app.memory import indexer
from app.memory.retriever import retrieve_memories
from app.memory.service import create_memory_document


def _reset_indexer_cache():
    indexer._COLLECTION = None
    indexer._COLLECTION_KEY = ""


def test_retrieve_memories_for_chat_can_use_private_and_avatar_only(db):
    create_memory_document(
        db,
        user_id="user-1",
        source_type="diary",
        source_id="diary-1",
        title="夜跑",
        content="我最近喜欢晚上夜跑，跑完会心情很好。",
        visibility="private",
    )
    create_memory_document(
        db,
        user_id="user-1",
        source_type="plaza_post",
        source_id="post-1",
        title="广场分享",
        content="我也很喜欢夜跑和散步。",
        visibility="avatar_only",
    )
    db.commit()

    items = retrieve_memories(
        db,
        user_id="user-1",
        query="夜跑",
        scenario="chat",
        top_k=5,
    )

    assert len(items) == 2
    assert {item["visibility"] for item in items} == {"private", "avatar_only"}


def test_retrieve_memories_for_agent_to_agent_excludes_private(db):
    create_memory_document(
        db,
        user_id="user-1",
        source_type="diary",
        source_id="diary-2",
        title="私密日记",
        content="我有点社恐，但还是想认识新的朋友。",
        visibility="private",
    )
    create_memory_document(
        db,
        user_id="user-1",
        source_type="avatar_card",
        source_id="card-1",
        title="公开名片",
        content="喜欢摄影，也愿意认识新朋友。",
        visibility="match_card",
    )
    db.commit()

    items = retrieve_memories(
        db,
        user_id="user-1",
        query="朋友",
        scenario="agent_to_agent",
        top_k=5,
    )

    assert len(items) == 1
    assert items[0]["visibility"] == "match_card"
    assert "社恐" not in items[0]["content"]


def test_retrieve_memories_supports_source_type_filter(db):
    create_memory_document(
        db,
        user_id="user-1",
        source_type="diary",
        source_id="diary-3",
        title="日记",
        content="今天在图书馆学习。",
        visibility="private",
    )
    create_memory_document(
        db,
        user_id="user-1",
        source_type="chat_session",
        source_id="chat-1",
        title="聊天",
        content="我们聊到了图书馆和学习计划。",
        visibility="private",
    )
    db.commit()

    items = retrieve_memories(
        db,
        user_id="user-1",
        query="图书馆",
        scenario="chat",
        source_types=["chat_session"],
        top_k=5,
    )

    assert len(items) == 1
    assert items[0]["source_type"] == "chat_session"


def test_retrieve_memories_for_chat_prioritizes_life_sources_over_chat_session(db):
    create_memory_document(
        db,
        user_id="user-1",
        source_type="chat_session",
        source_id="chat-boost-1",
        title="聊天记录",
        content="我最近在准备考研，也在跑步。",
        visibility="private",
    )
    create_memory_document(
        db,
        user_id="user-1",
        source_type="diary",
        source_id="diary-boost-1",
        title="备考日记",
        content="我最近在准备考研，也在跑步。",
        visibility="private",
    )
    db.commit()

    items = retrieve_memories(
        db,
        user_id="user-1",
        query="考研 跑步",
        scenario="chat",
        top_k=5,
    )

    assert len(items) >= 2
    assert items[0]["source_type"] == "diary"
    assert "考研" in items[0]["content"]


def test_retrieve_memories_vector_path_prioritizes_life_sources_and_keeps_document_metadata(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_VECTOR_ENABLED", True)
    monkeypatch.setattr(settings, "MEMORY_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setattr(settings, "MEMORY_DIR", str(Path(tmp_path) / "memory_store"))
    _reset_indexer_cache()

    try:
        shared_content = "我最近喜欢夜跑，也常在校园里散步和拍照。"
        for source_type, source_id, title in [
            ("chat_session", "chat-vector-1", "聊天记录"),
            ("social_message", "social-vector-1", "私聊"),
            ("plaza_post", "post-vector-1", "广场帖子"),
            ("material", "material-vector-1", "文字素材"),
            ("diary", "diary-vector-1", "夜跑日记"),
        ]:
            create_memory_document(
                db,
                user_id="user-1",
                source_type=source_type,
                source_id=source_id,
                title=title,
                content=shared_content,
                visibility="private",
            )
        db.commit()

        items = retrieve_memories(
            db,
            user_id="user-1",
            query="夜跑 散步 拍照",
            scenario="chat",
            top_k=4,
            source_types=["diary", "material", "plaza_post", "social_message", "chat_session"],
        )

        assert len(items) == 4
        assert items[0]["source_type"] == "diary"
        assert {item["source_type"] for item in items} == {"diary", "material", "plaza_post", "social_message"}
        assert all(item["title"] for item in items)
        assert all(item["occurred_at"] > 0 for item in items)
    finally:
        _reset_indexer_cache()

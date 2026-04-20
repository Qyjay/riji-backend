"""记忆检索集成测试。"""

from app.memory.retriever import retrieve_memories
from app.memory.service import create_memory_document


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

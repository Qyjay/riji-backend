import asyncio
import json
import time

from app.memory.service import create_memory_document
from app.models.realtime_voice import RealtimeVoiceSession
from app.realtime_voice.provider import ProviderToolCall
from app.realtime_voice.tools import ToolRouter
from tests.conftest import TestingSessionLocal, create_test_user


def _voice_session(db, user_id: str) -> str:
    session_id = f"voice-memory-{user_id}"
    now = int(time.time() * 1000)
    db.add(
        RealtimeVoiceSession(
            id=session_id,
            user_id=user_id,
            status="active",
            started_at=now,
            last_active_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    return session_id


def _memory(db, *, user_id: str, source_id: str, title: str, content: str):
    document = create_memory_document(
        db,
        user_id=user_id,
        source_type="diary",
        source_id=source_id,
        title=title,
        content=content,
        visibility="private",
        memory_scope="self",
        occurred_at=int(time.time() * 1000),
    )
    db.commit()
    return document


def test_memory_tools_return_evidence_and_enforce_session_allowlist(client, db):
    owner = create_test_user(client, username="voice_memory_a")
    other = create_test_user(client, username="voice_memory_b")
    owner_id = owner["user"]["id"]
    other_id = other["user"]["id"]
    owner_doc = _memory(
        db,
        user_id=owner_id,
        source_id="diary-sunset",
        title="同一片晚霞",
        content="傍晚在大通湖拍到一片很低的橙色晚霞，湖面有细碎反光。",
    )
    other_doc = _memory(
        db,
        user_id=other_id,
        source_id="diary-secret",
        title="秘密会议",
        content="这是一条只属于另一个用户的秘密会议记录。",
    )
    voice_session_id = _voice_session(db, owner_id)
    router = ToolRouter(
        voice_session_id=voice_session_id,
        client_session_id=voice_session_id,
        user_id=owner_id,
        db_factory=TestingSessionLocal,
    )

    async def search():
        return await router.execute_calls(
            [
                ProviderToolCall(
                    "call-search",
                    "search_personal_memory",
                    '{"query":"大通湖 晚霞","sourceTypes":["diary"],"topK":4}',
                )
            ]
        )

    results, display = asyncio.run(search())
    envelope = json.loads(results[0].output)
    assert envelope["ok"] is True
    assert envelope["data"]["items"][0]["documentId"] == owner_doc.id
    assert envelope["data"]["items"][0]["deepLink"].endswith("diary-sunset")
    assert display[0]["type"] == "tool.result"
    assert display[0]["display"]["kind"] == "memory_evidence"

    async def get_documents():
        return await router.execute_calls(
            [
                ProviderToolCall(
                    "call-owner-doc",
                    "get_memory_document",
                    json.dumps({"documentId": owner_doc.id}),
                ),
                ProviderToolCall(
                    "call-other-doc",
                    "get_memory_document",
                    json.dumps({"documentId": other_doc.id}),
                ),
            ]
        )

    document_results, _ = asyncio.run(get_documents())
    own = json.loads(document_results[0].output)
    forbidden = json.loads(document_results[1].output)
    assert own["ok"] is True
    assert own["data"]["title"] == "同一片晚霞"
    assert len(own["data"]["content"]) <= 800
    assert forbidden["ok"] is False
    assert "未授权" in forbidden["error"]


def test_memory_search_never_returns_another_users_document(client, db):
    owner = create_test_user(client, username="voice_isolate_a")
    other = create_test_user(client, username="voice_isolate_b")
    owner_id = owner["user"]["id"]
    _memory(
        db,
        user_id=other["user"]["id"],
        source_id="other-only",
        title="另一个人的秘密",
        content="唯一关键词火星密会只存在于另一个用户的日记。",
    )
    voice_session_id = _voice_session(db, owner_id)
    router = ToolRouter(
        voice_session_id=voice_session_id,
        client_session_id=voice_session_id,
        user_id=owner_id,
        db_factory=TestingSessionLocal,
    )
    results, _ = asyncio.run(
        router.execute_calls(
            [
                ProviderToolCall(
                    "call-isolation",
                    "search_personal_memory",
                    '{"query":"火星密会","sourceTypes":["diary"],"topK":6}',
                )
            ]
        )
    )
    assert json.loads(results[0].output)["data"]["items"] == []

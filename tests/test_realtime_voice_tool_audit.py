import asyncio
import json
import time

from app.models.realtime_voice import RealtimeToolCall, RealtimeVoiceSession
from app.realtime_voice.provider import ProviderToolCall
from app.realtime_voice.tools import ToolRouter
from tests.conftest import TestingSessionLocal, create_test_user


def test_tool_call_is_idempotent_by_provider_call_id(client, db):
    auth = create_test_user(client, username="voice_audit")
    user_id = auth["user"]["id"]
    now = int(time.time() * 1000)
    db.add(
        RealtimeVoiceSession(
            id="voice-audit-session",
            user_id=user_id,
            status="active",
            started_at=now,
            last_active_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    router = ToolRouter(
        voice_session_id="voice-audit-session",
        client_session_id="voice-audit-session",
        user_id=user_id,
        db_factory=TestingSessionLocal,
    )
    call = ProviderToolCall(
        call_id="provider-call-stable",
        name="search_personal_memory",
        arguments='{"query":"不存在的内容","topK":2}',
    )

    first, _ = asyncio.run(router.execute_calls([call]))
    second, _ = asyncio.run(router.execute_calls([call]))

    assert first[0].output == second[0].output
    assert json.loads(first[0].output)["ok"] is True
    rows = (
        db.query(RealtimeToolCall)
        .filter(RealtimeToolCall.provider_call_id == "provider-call-stable")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "succeeded"
    assert rows[0].finished_at is not None


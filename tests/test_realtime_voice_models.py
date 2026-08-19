import time

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.realtime_voice import RealtimeToolCall, RealtimeVoiceSession
from tests.conftest import create_test_user


def test_realtime_voice_models_and_provider_call_uniqueness(client, db):
    user = create_test_user(client, username="voice_models")
    now = int(time.time() * 1000)
    voice_session = RealtimeVoiceSession(
        id="voice-session-1",
        user_id=user["user"]["id"],
        status="active",
        started_at=now,
        last_active_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(voice_session)
    db.flush()
    db.add(
        RealtimeToolCall(
            id="tool-call-1",
            voice_session_id=voice_session.id,
            user_id=user["user"]["id"],
            provider_call_id="provider-call-1",
            tool_name="search_personal_memory",
            idempotency_key="idem-1",
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()

    db.add(
        RealtimeToolCall(
            id="tool-call-2",
            voice_session_id=voice_session.id,
            user_id=user["user"]["id"],
            provider_call_id="provider-call-1",
            tool_name="search_personal_memory",
            idempotency_key="idem-2",
            created_at=now,
            updated_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


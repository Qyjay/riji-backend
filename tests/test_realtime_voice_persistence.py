import asyncio

from app.models.chat import ChatMessage, ChatSession
from app.models.realtime_voice import RealtimeVoiceSession
from app.realtime_voice.persistence import (
    close_voice_session,
    create_voice_session,
    mark_session_ready,
    save_transcript_message,
)
from tests.conftest import create_test_user


def test_voice_transcript_is_idempotent_and_audio_is_not_stored(client, db):
    auth = create_test_user(client, username="voice_persist")
    user_id = auth["user"]["id"]

    row = asyncio.run(
        create_voice_session(
            db,
            session_id="voice-persist-1",
            user_id=user_id,
            client_platform="h5",
            voice="voice",
        )
    )
    assert row.chat_session_id
    mark_session_ready(
        db,
        session_id=row.id,
        provider_session_id="dialog-1",
        provider_log_id="log-1",
    )
    first = save_transcript_message(
        db,
        voice_session_id=row.id,
        user_id=user_id,
        role="user",
        content="我想起了大通湖的晚霞",
        provider_item_id="question-1",
    )
    duplicate = save_transcript_message(
        db,
        voice_session_id=row.id,
        user_id=user_id,
        role="user",
        content="我想起了大通湖的晚霞",
        provider_item_id="question-1",
    )
    assert first.id == duplicate.id
    assert (
        db.query(ChatMessage)
        .filter(ChatMessage.client_message_id == "realtime:user:question-1")
        .count()
        == 1
    )
    assert "audio" not in first.attachments.lower()

    asyncio.run(close_voice_session(db, session_id=row.id, reason="user"))
    refreshed = db.query(RealtimeVoiceSession).filter_by(id=row.id).one()
    chat = db.query(ChatSession).filter_by(id=row.chat_session_id).one()
    assert refreshed.status == "closed"
    assert refreshed.close_reason == "user"
    assert chat.status == "closed"

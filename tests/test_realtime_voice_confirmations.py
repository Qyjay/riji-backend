import time

import pytest

from app.realtime_voice.confirmations import ConfirmationError, ConfirmationManager


def _manager():
    return ConfirmationManager(
        user_id="user-confirm",
        voice_session_id="voice-confirm",
    )


def test_confirmation_token_binds_action_resource_hash_and_next_turn():
    manager = _manager()
    record = manager.create(
        action="start_social_mission",
        resource_id="mission-1",
        resource_hash="hash-1",
        title="开始寻找电影搭子？",
        summary=["活动：看科幻电影"],
        created_turn=2,
    )

    with pytest.raises(ConfirmationError, match="下一句话"):
        manager.resolve_voice(
            token=record.token,
            action="start_social_mission",
            resource_id="mission-1",
            resource_hash="hash-1",
            current_turn=2,
        )

    with pytest.raises(ConfirmationError, match="不匹配"):
        manager.resolve_voice(
            token=record.token,
            action="start_social_mission",
            resource_id="mission-2",
            resource_hash="hash-1",
            current_turn=3,
        )

    approved, should_execute = manager.resolve_voice(
        token=record.token,
        action="start_social_mission",
        resource_id="mission-1",
        resource_hash="hash-1",
        current_turn=3,
    )
    assert approved.channel == "voice"
    assert should_execute is True

    duplicate, should_execute_again = manager.resolve_voice(
        token=record.token,
        action="start_social_mission",
        resource_id="mission-1",
        resource_hash="hash-1",
        current_turn=4,
    )
    assert duplicate.id == record.id
    assert should_execute_again is False


def test_confirmation_reject_is_idempotent_and_cannot_flip():
    manager = _manager()
    record = manager.create(
        action="start_social_mission",
        resource_id="mission-2",
        resource_hash="hash-2",
        title="开始寻找？",
        summary=[],
        created_turn=1,
    )

    rejected, should_execute = manager.resolve_screen(
        confirmation_id=record.id,
        decision="reject",
    )
    assert rejected.channel == "screen"
    assert should_execute is False

    duplicate, should_execute_again = manager.resolve_screen(
        confirmation_id=record.id,
        decision="reject",
    )
    assert duplicate.id == record.id
    assert should_execute_again is False

    with pytest.raises(ConfirmationError, match="不能更改"):
        manager.resolve_screen(
            confirmation_id=record.id,
            decision="approve",
        )


def test_confirmation_expiry_and_token_tampering_are_rejected():
    manager = _manager()
    expired = manager.create(
        action="start_social_mission",
        resource_id="mission-expired",
        resource_hash="hash-expired",
        title="开始寻找？",
        summary=[],
        created_turn=1,
    )
    expired.expires_at = int(time.time() * 1000) - 1
    with pytest.raises(ConfirmationError, match="已过期"):
        manager.resolve_screen(
            confirmation_id=expired.id,
            decision="approve",
        )

    active = manager.create(
        action="start_social_mission",
        resource_id="mission-active",
        resource_hash="hash-active",
        title="开始寻找？",
        summary=[],
        created_turn=1,
    )
    tampered = f"{active.token[:-2]}xx"
    with pytest.raises(ConfirmationError, match="无效"):
        manager.resolve_voice(
            token=tampered,
            action="start_social_mission",
            resource_id="mission-active",
            resource_hash="hash-active",
            current_turn=2,
        )


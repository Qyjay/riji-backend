import asyncio
import json
import time

from app.models.realtime_voice import RealtimeToolCall, RealtimeVoiceSession
from app.models.social import SocialMission
from app.realtime_voice.provider import ProviderToolCall
from app.realtime_voice.tools import ToolRouter
from app.social.mission_service import update_mission
from tests.conftest import TestingSessionLocal, create_test_user


def _router(client, db, username="voice_mission"):
    auth = create_test_user(client, username=username)
    now = int(time.time() * 1000)
    session_id = f"voice-{username}"
    db.add(
        RealtimeVoiceSession(
            id=session_id,
            user_id=auth["user"]["id"],
            status="active",
            started_at=now,
            last_active_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    return auth, ToolRouter(
        voice_session_id=session_id,
        client_session_id=session_id,
        user_id=auth["user"]["id"],
        db_factory=TestingSessionLocal,
    )


def _call(router, call_id, name, arguments):
    results, events = asyncio.run(
        router.execute_calls(
            [
                ProviderToolCall(
                    call_id=call_id,
                    name=name,
                    arguments=json.dumps(arguments, ensure_ascii=False),
                )
            ]
        )
    )
    return json.loads(results[0].output), events


def _complete_draft(router, prefix="mission"):
    draft_result, draft_events = _call(
        router,
        f"{prefix}-draft",
        "draft_social_mission",
        {"text": "今晚想找一个人看科幻电影"},
    )
    assert draft_result["ok"] is True
    data = draft_result["data"]
    assert data["questions"] == []
    assert draft_events[0]["display"]["kind"] == "mission_draft"

    created, create_events = _call(
        router,
        f"{prefix}-create",
        "create_social_mission_draft",
        {"draftId": data["draftId"], "draftHash": data["draftHash"]},
    )
    assert created["ok"] is True
    assert {event["type"] for event in create_events} == {
        "tool.result",
        "confirmation.required",
    }
    return created["data"], create_events


def test_mission_draft_is_session_scoped_and_ambiguous_text_stays_read_only(
    client,
    db,
):
    _, router = _router(client, db, "voice_ambiguous")
    result, events = _call(
        router,
        "ambiguous-draft",
        "draft_social_mission",
        {"text": "我每天想去看电影，帮我找搭子"},
    )

    assert result["ok"] is True
    assert result["data"]["questions"][0].startswith("你是想今天去一次")
    assert events[0]["display"]["readyForConfirmation"] is False
    assert db.query(SocialMission).count() == 0

    create, _ = _call(
        router,
        "ambiguous-create",
        "create_social_mission_draft",
        {
            "draftId": result["data"]["draftId"],
            "draftHash": result["data"]["draftHash"],
        },
    )
    assert create["ok"] is False
    assert "待确认问题" in create["error"]
    assert db.query(SocialMission).count() == 0

    _, other_router = _router(client, db, "voice_other")
    cross_session, _ = _call(
        other_router,
        "cross-session-create",
        "create_social_mission_draft",
        {
            "draftId": result["data"]["draftId"],
            "draftHash": result["data"]["draftHash"],
        },
    )
    assert cross_session["ok"] is False


def test_voice_confirmation_requires_next_turn_and_is_idempotent(client, db):
    auth, router = _router(client, db, "voice_confirm")
    router.note_user_turn()
    created, _ = _complete_draft(router, "voice-confirm")
    mission_id = created["mission"]["id"]
    token = created["confirmationToken"]

    mission = db.query(SocialMission).filter_by(id=mission_id).one()
    assert mission.status == "draft"
    assert mission.source == "realtime_voice"
    permissions = json.loads(mission.permissions)
    assert permissions["autoPublish"] is False
    assert permissions["autoConnect"] is False

    same_turn, _ = _call(
        router,
        "start-same-turn",
        "start_social_mission",
        {"missionId": mission_id, "confirmationToken": token},
    )
    assert same_turn["ok"] is False
    assert "下一句话" in same_turn["error"]
    db.expire_all()
    assert db.query(SocialMission).filter_by(id=mission_id).one().status == "draft"

    router.note_user_turn()
    started, events = _call(
        router,
        "start-next-turn",
        "start_social_mission",
        {"missionId": mission_id, "confirmationToken": token},
    )
    assert started["ok"] is True
    assert started["data"]["mission"]["status"] in {"searching", "awaiting_user"}
    assert started["data"]["mission"]["deepLink"].endswith(mission_id)
    assert "navigation.suggested" in {event["type"] for event in events}

    duplicate, _ = _call(
        router,
        "start-idempotent-confirmation",
        "start_social_mission",
        {"missionId": mission_id, "confirmationToken": token},
    )
    assert duplicate["ok"] is True
    assert duplicate["data"] == started["data"]
    assert db.query(SocialMission).filter_by(user_id=auth["user"]["id"]).count() == 1


def test_screen_confirmation_executes_or_rejects_once_and_audits_channel(
    client,
    db,
):
    _, router = _router(client, db, "voice_screen")
    router.note_user_turn()
    created, create_events = _complete_draft(router, "screen-approve")
    confirmation = next(
        event["confirmation"]
        for event in create_events
        if event["type"] == "confirmation.required"
    )

    provider_result, events = asyncio.run(
        router.resolve_confirmation(
            confirmation_id=confirmation["id"],
            decision="approve",
        )
    )
    assert provider_result is not None
    assert "confirmation.resolved" in {event["type"] for event in events}
    assert "tool.result" in {event["type"] for event in events}
    mission_id = created["mission"]["id"]
    db.expire_all()
    assert db.query(SocialMission).filter_by(id=mission_id).one().status in {
        "searching",
        "awaiting_user",
    }

    duplicate, _ = asyncio.run(
        router.resolve_confirmation(
            confirmation_id=confirmation["id"],
            decision="approve",
        )
    )
    assert duplicate is not None

    created_reject, reject_events = _complete_draft(router, "screen-reject")
    reject_confirmation = next(
        event["confirmation"]
        for event in reject_events
        if event["type"] == "confirmation.required"
    )
    rejected, resolved_events = asyncio.run(
        router.resolve_confirmation(
            confirmation_id=reject_confirmation["id"],
            decision="reject",
        )
    )
    assert rejected is None
    assert resolved_events[0]["decision"] == "reject"
    db.expire_all()
    assert (
        db.query(SocialMission)
        .filter_by(id=created_reject["mission"]["id"])
        .one()
        .status
        == "draft"
    )
    screen_rows = (
        db.query(RealtimeToolCall)
        .filter(RealtimeToolCall.provider_call_id.like("screen:%"))
        .all()
    )
    assert {json.loads(row.arguments_json)["channel"] for row in screen_rows} == {
        "screen"
    }
    assert {row.status for row in screen_rows} == {"succeeded", "rejected"}


def test_changed_summary_and_cross_user_navigation_are_rejected(client, db):
    auth, router = _router(client, db, "voice_changed")
    router.note_user_turn()
    created, _ = _complete_draft(router, "changed")
    mission_id = created["mission"]["id"]
    token = created["confirmationToken"]

    from app.models.user import User

    owner = db.query(User).filter_by(id=auth["user"]["id"]).one()
    update_mission(
        db,
        owner,
        mission_id,
        {"title": "已修改的电影任务"},
    )
    router.note_user_turn()
    changed, _ = _call(
        router,
        "changed-start",
        "start_social_mission",
        {"missionId": mission_id, "confirmationToken": token},
    )
    assert changed["ok"] is False
    assert "不匹配" in changed["error"] or "变化" in changed["error"]
    db.expire_all()
    assert db.query(SocialMission).filter_by(id=mission_id).one().status == "draft"

    _, other_router = _router(client, db, "voice_intruder")
    progress, _ = _call(
        other_router,
        "cross-user-progress",
        "get_social_mission_progress",
        {"missionId": mission_id},
    )
    assert progress["ok"] is False
    navigation, _ = _call(
        other_router,
        "cross-user-nav",
        "open_app_page",
        {"page": "mission", "resourceId": mission_id},
    )
    assert navigation["ok"] is False

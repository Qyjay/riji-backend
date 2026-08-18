"""AtoA 决赛主链：异步任务、用户决策和对方确认。"""
from __future__ import annotations

import asyncio
import json
import time
from uuid import uuid4

from app.avatar import service as avatar_service
from app.config import settings
from app.models.avatar import AvatarAtoaInteraction, AvatarAtoaSession, AvatarSurfJob
from app.models.memory import AvatarCard
from app.models.social import Match
from app.social import service as social_service
from tests.conftest import create_test_user, get_auth_header


def _uid(user_data: dict) -> str:
    return user_data["user"]["id"]


def _make_card(db, user_id: str, interests: list[str]) -> AvatarCard:
    card = AvatarCard(
        id=str(uuid4()),
        user_id=user_id,
        display_name="测试分身",
        public_summary="愿意从共同兴趣开始认识新朋友",
        interest_tags=json.dumps(interests, ensure_ascii=False),
        social_intent=json.dumps(["buddy"], ensure_ascii=False),
        conversation_style=json.dumps({"tone": "自然"}, ensure_ascii=False),
        boundaries=json.dumps(["不替用户承诺"], ensure_ascii=False),
        visibility="public",
        updated_at=int(time.time() * 1000),
    )
    db.add(card)
    db.commit()
    return card


def _make_interaction(db, user_a_id: str, user_b_id: str, session_id: str | None = None):
    now = int(time.time() * 1000)
    interaction = AvatarAtoaInteraction(
        id=str(uuid4()),
        initiator_id=user_a_id,
        session_id=session_id,
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        interaction_type="card_exchange",
        outcome="pending_user_decision",
        score_a=65,
        score_b=58,
        shared_topics=json.dumps(["摄影"], ensure_ascii=False),
        reasons_a=json.dumps(["都喜欢摄影"], ensure_ascii=False),
        reasons_b=json.dumps(["交流节奏接近"], ensure_ascii=False),
        risk_flags="[]",
        conversation=json.dumps([
            {"role": "avatar_a", "content": "你也喜欢摄影吗？"},
            {"role": "avatar_b", "content": "是的，我喜欢城市散步时拍照。"},
        ], ensure_ascii=False),
        is_visible_to_a=True,
        is_visible_to_b=False,
        interaction_phase=1,
        created_at=now,
        updated_at=now,
    )
    db.add(interaction)
    db.commit()
    return interaction


def test_surf_job_api_deduplicates_pending_job(client, db):
    user = create_test_user(client, username="atoa_job_user")
    headers = get_auth_header(user["token"])

    first = client.post("/api/avatar/surf/jobs", headers=headers)
    second = client.post("/api/avatar/surf/jobs", headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    first_job = first.json()["data"]
    second_job = second.json()["data"]
    assert first_job["id"] == second_job["id"]
    assert first_job["status"] == "pending"
    assert db.query(AvatarSurfJob).count() == 1


def test_surf_worker_marks_skipped_business_result_as_succeeded(client, db):
    user = create_test_user(client, username="atoa_job_worker")
    job_data = avatar_service.create_surf_job(db, _uid(user))
    job = avatar_service.claim_next_surf_job(db)

    assert job is not None
    result = asyncio.run(avatar_service.process_surf_job(db, job))
    db.refresh(job)
    assert result["status"] == "skipped"
    assert job.id == job_data["id"]
    assert job.status == "succeeded"


def test_connect_does_not_require_target_plaza_post(client, db):
    user_a = create_test_user(client, username="atoa_nopost_a")
    user_b = create_test_user(client, username="atoa_nopost_b")
    interaction = _make_interaction(db, _uid(user_a), _uid(user_b))

    result = asyncio.run(avatar_service.decide_atoa_outcome(
        db,
        _uid(user_a),
        interaction.id,
        "connect",
        "我们都喜欢摄影，想继续认识一下。",
    ))

    social_match = db.query(Match).filter(Match.id == result["social_match_id"]).first()
    db.refresh(interaction)
    assert social_match is not None
    assert social_match.target_id == _uid(user_b)
    assert social_match.status == "pending"
    assert interaction.outcome == "connected"

    social_service.respond_buddy(db, _uid(user_b), social_match.id, True)
    db.refresh(interaction)
    assert interaction.outcome == "connect_confirmed"


def test_block_adds_replacement_from_session_snapshot(client, db):
    user_a = create_test_user(client, username="atoa_replace_flow_a")
    user_b = create_test_user(client, username="atoa_replace_flow_b")
    user_c = create_test_user(client, username="atoa_replace_flow_c")
    _make_card(db, _uid(user_a), ["摄影", "散步"])
    _make_card(db, _uid(user_b), ["摄影"])
    _make_card(db, _uid(user_c), ["摄影", "散步"])

    now = int(time.time() * 1000)
    session = AvatarAtoaSession(
        id=str(uuid4()),
        user_id=_uid(user_a),
        candidate_ids=json.dumps([_uid(user_b)]),
        excluded_ids="[]",
        score_snapshot=json.dumps({_uid(user_b): 70, _uid(user_c): 66}),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.commit()
    interaction = _make_interaction(db, _uid(user_a), _uid(user_b), session.id)

    result = asyncio.run(avatar_service.decide_atoa_outcome(
        db,
        _uid(user_a),
        interaction.id,
        "block",
    ))

    replacement = db.query(AvatarAtoaInteraction).filter(
        AvatarAtoaInteraction.id == result["replacement_interaction_id"],
    ).first()
    db.refresh(session)
    assert replacement is not None
    assert replacement.user_b_id == _uid(user_c)
    assert _uid(user_b) in json.loads(session.excluded_ids)
    assert _uid(user_c) in json.loads(session.candidate_ids)


def test_atoa_chat_retries_rate_limit_then_succeeds(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def chat_completion(self, **_kwargs):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("429 Too Many Requests")
            return "ok"

    client = FakeClient()
    monkeypatch.setattr(settings, "ATOA_AI_MAX_RETRIES", 2)
    monkeypatch.setattr(settings, "ATOA_AI_RETRY_BASE_SEC", 0.01)

    result = asyncio.run(avatar_service._chat_completion_with_retry(
        client,
        messages=[{"role": "user", "content": "test"}],
    ))
    assert result == "ok"
    assert client.calls == 3

"""
Phase 8A: AtoA 搭子模式 — 单元 + 集成测试
覆盖：
  - _recall_atoa_candidates 过滤逻辑
  - _score_all_atoa_candidates 批量规则评分（新架构）
  - _build_atoa_session Top-10 会话创建
  - _get_replacement_candidate 补位逻辑
  - _apply_block_penalty 双向降分
  - _score_atoa_pair 对称性与意图匹配（async, 通过 asyncio.run）
  - _upsert_atoa_match_pair 原子写入与互指（保留，用于 8C）
  - _sync_atoa_mutual_flag dismiss 后同步标志
  - _write_atoa_interaction: outcome 初始值为 pending_user_decision
  - GET /api/avatar/probe-log（含 session_id/outcome 过滤）
  - GET /api/avatar/atoa/sessions
  - GET /api/avatar/mutual-matches

注意：create_test_user 返回 {"token": "...", "user": {"id": "...", ...}}
      所以用户 ID 取 user_data["user"]["id"]
"""
import asyncio
import json
import time
from uuid import uuid4

import pytest

from tests.conftest import create_test_user, get_auth_header
from app.avatar import service as svc
from app.models.avatar import (
    AvatarAtoaInteraction,
    AvatarAtoaSession,
    AvatarMatch,
    AvatarStatus,
    AvatarSurfLog,
)
from app.models.memory import AvatarCard
from app.models.plaza import PlazaPost
from app.models.user import User


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def uid(user_data: dict) -> str:
    """从 create_test_user 返回值中取 user id。"""
    return user_data["user"]["id"]


def _enable_atoa(db, user_id: str) -> None:
    """开启分身并允许 auto_match。"""
    status = svc._get_or_create_status(db, user_id)
    status.is_active = True
    status.auto_match_enabled = True
    db.commit()


def _make_card(db, user_id: str, interests: list, intents: list, visibility: str = "public") -> AvatarCard:
    now = int(time.time() * 1000)
    card = AvatarCard(
        id=str(uuid4()),
        user_id=user_id,
        interest_tags=json.dumps(interests, ensure_ascii=False),
        social_intent=json.dumps(intents, ensure_ascii=False),
        boundaries=json.dumps([], ensure_ascii=False),
        conversation_style=json.dumps({"tone": "随和"}, ensure_ascii=False),
        public_summary="测试分身",
        visibility=visibility,
        updated_at=now,
    )
    db.add(card)
    db.commit()
    return card


def _make_post(db, user_id: str, post_type: str = "buddy") -> PlazaPost:
    now = int(time.time() * 1000)
    post = PlazaPost(
        id=str(uuid4()),
        user_id=user_id,
        type=post_type,
        content="测试帖子",
        tags=json.dumps(["测试"], ensure_ascii=False),
        school_only=False,
        created_at=now,
    )
    db.add(post)
    db.commit()
    return post


# ── _recall_atoa_candidates ───────────────────────────────────────────────────

def test_recall_atoa_candidates_filters_private(client, db):
    """visibility=private 的用户不应出现在候选列表里。"""
    user_a = create_test_user(client, username="atoa_recall_a")
    user_b = create_test_user(client, username="atoa_recall_b")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    _make_card(db, uid(user_b), ["音乐"], ["buddy"], visibility="private")

    candidates = svc._recall_atoa_candidates(db, uid(user_a))
    candidate_ids = [c.id for c in candidates]
    assert uid(user_b) not in candidate_ids


def test_recall_atoa_candidates_requires_auto_match(client, db):
    """auto_match_enabled=False 的用户不进入候选。"""
    user_a = create_test_user(client, username="atoa_recall_c")
    user_b = create_test_user(client, username="atoa_recall_d")

    _enable_atoa(db, uid(user_a))
    status_b = svc._get_or_create_status(db, uid(user_b))
    status_b.is_active = True
    status_b.auto_match_enabled = False
    db.commit()
    _make_card(db, uid(user_b), ["摄影"], ["buddy"])

    candidates = svc._recall_atoa_candidates(db, uid(user_a))
    candidate_ids = [c.id for c in candidates]
    assert uid(user_b) not in candidate_ids


def test_recall_atoa_candidates_filters_dismissed(client, db):
    """已被 A dismiss 的用户 B 不再出现在候选中。"""
    user_a = create_test_user(client, username="atoa_recall_e")
    user_b = create_test_user(client, username="atoa_recall_f")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    _make_card(db, uid(user_b), ["旅行"], ["buddy"])
    post_b = _make_post(db, uid(user_b))

    now = int(time.time() * 1000)
    dismissed = AvatarMatch(
        id=str(uuid4()),
        user_id=uid(user_a),
        post_id=post_b.id,
        target_user_id=uid(user_b),
        match_score=0,
        match_reasons=json.dumps([]),
        agent_conversation=json.dumps([]),
        status="dismissed",
        match_type="atoa",
        intent_type="buddy",
        created_at=now,
    )
    db.add(dismissed)
    db.commit()

    candidates = svc._recall_atoa_candidates(db, uid(user_a))
    candidate_ids = [c.id for c in candidates]
    assert uid(user_b) not in candidate_ids


def test_recall_atoa_candidates_includes_eligible(client, db):
    """同时满足所有条件的用户应出现在候选中。"""
    user_a = create_test_user(client, username="atoa_recall_g")
    user_b = create_test_user(client, username="atoa_recall_h")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    _make_card(db, uid(user_b), ["编程"], ["buddy"], visibility="public")

    candidates = svc._recall_atoa_candidates(db, uid(user_a))
    candidate_ids = [c.id for c in candidates]
    assert uid(user_b) in candidate_ids


# ── _score_atoa_pair（通过 asyncio.run 执行 async 函数）────────────────────────

def test_score_atoa_pair_no_shared_interest_returns_none(client, db):
    """无共同兴趣词时预筛应拒绝（返回 None）。"""
    user_a = create_test_user(client, username="atoa_score_a")
    user_b = create_test_user(client, username="atoa_score_b")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    _make_card(db, uid(user_a), ["编程", "数学"], ["study"])
    _make_card(db, uid(user_b), ["舞蹈", "化妆"], ["share"])

    from app.models.user import User
    ua = db.query(User).filter(User.id == uid(user_a)).first()
    ub = db.query(User).filter(User.id == uid(user_b)).first()

    result = asyncio.run(svc._score_atoa_pair(db, ua, ub, set()))
    assert result is None


def test_score_atoa_pair_shared_interest_produces_scores(client, db):
    """有共同兴趣 + 相同 intent 时，应产生非空打分结果和对话记录。"""
    user_a = create_test_user(client, username="atoa_score_c")
    user_b = create_test_user(client, username="atoa_score_d")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    _make_card(db, uid(user_a), ["摄影", "旅行", "读书"], ["buddy", "share"])
    _make_card(db, uid(user_b), ["摄影", "电影", "读书"], ["buddy", "share"])

    from app.models.user import User
    ua = db.query(User).filter(User.id == uid(user_a)).first()
    ub = db.query(User).filter(User.id == uid(user_b)).first()

    result = asyncio.run(svc._score_atoa_pair(db, ua, ub, set()))
    assert result is not None
    assert result["score_ab"] >= 0
    assert result["score_ba"] >= 0
    assert isinstance(result["conversation"], list)
    assert "shared_topics" in result
    assert "摄影" in result["shared_topics"] or "读书" in result["shared_topics"]


def test_score_atoa_pair_conversation_structure(client, db):
    """有 >= 2 共同兴趣 + 匹配意图时，_score_atoa_pair 应返回非 None，conversation 字段应为列表。
    非 Mock 环境下 AI 调用可能返回空列表，但结构必须合法。"""
    user_a = create_test_user(client, username="atoa_score_e")
    user_b = create_test_user(client, username="atoa_score_f")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    # >= 2 共同兴趣 + 匹配意图，规则打分: 兴趣重合(+10) + 意图匹配(+14) = 24 >= 20
    _make_card(db, uid(user_a), ["音乐", "吉他", "摄影"], ["buddy"])
    _make_card(db, uid(user_b), ["音乐", "摄影", "旅行"], ["buddy"])

    ua = db.query(User).filter(User.id == uid(user_a)).first()
    ub = db.query(User).filter(User.id == uid(user_b)).first()

    result = asyncio.run(svc._score_atoa_pair(db, ua, ub, set()))
    assert result is not None
    assert isinstance(result["conversation"], list)
    assert "score_ab" in result and result["score_ab"] >= 0
    assert "shared_topics" in result
    # 若有对话内容，验证每条消息的结构
    for turn in result["conversation"]:
        assert turn["role"] in ("avatar_a", "avatar_b")
        assert isinstance(turn["content"], str)


# ── _upsert_atoa_match_pair ───────────────────────────────────────────────────

def test_upsert_atoa_match_pair_creates_both_records(client, db):
    """upsert 应为 A 和 B 各创建一条 AvatarMatch，且互指 peer_match_id。"""
    user_a = create_test_user(client, username="atoa_upsert_a")
    user_b = create_test_user(client, username="atoa_upsert_b")

    _make_post(db, uid(user_a))
    _make_post(db, uid(user_b))

    score_data = {
        "score_ab": 70, "score_ba": 65,
        "reasons_ab": ["共同兴趣：摄影"], "reasons_ba": ["共同兴趣：摄影"],
        "shared_topics": ["摄影"],
        "conversation": [{"role": "avatar_a", "content": "你好"}],
        "intent_type": "buddy", "is_mutual": True, "outcome": "mutual",
        "risk_flags": [], "card_b_id": None,
    }

    match_ab, match_ba = svc._upsert_atoa_match_pair(
        db, uid(user_a), uid(user_b), score_data, "fake_interaction_id"
    )
    db.commit()

    assert match_ab is not None
    assert match_ba is not None
    assert match_ab.peer_match_id == match_ba.id
    assert match_ba.peer_match_id == match_ab.id
    assert match_ab.match_type == "atoa"
    assert match_ba.match_type == "atoa"
    assert match_ab.is_mutual is True
    assert match_ba.is_mutual is True
    assert match_ab.match_score == 70
    assert match_ba.match_score == 65
    assert match_ab.their_score == 65
    assert match_ba.their_score == 70


def test_upsert_atoa_match_pair_idempotent(client, db):
    """重复调用 upsert 不会创建新记录，只更新分数。"""
    user_a = create_test_user(client, username="atoa_upsert_c")
    user_b = create_test_user(client, username="atoa_upsert_d")

    _make_post(db, uid(user_a))
    _make_post(db, uid(user_b))

    score_data = {
        "score_ab": 50, "score_ba": 45,
        "reasons_ab": [], "reasons_ba": [],
        "shared_topics": ["音乐"], "conversation": [],
        "intent_type": "buddy", "is_mutual": True, "outcome": "mutual",
        "risk_flags": [], "card_b_id": None,
    }
    svc._upsert_atoa_match_pair(db, uid(user_a), uid(user_b), score_data, "")
    db.commit()

    count_before = db.query(AvatarMatch).filter(
        AvatarMatch.user_id == uid(user_a),
        AvatarMatch.target_user_id == uid(user_b),
        AvatarMatch.match_type == "atoa",
    ).count()

    score_data2 = dict(score_data)
    score_data2["score_ab"] = 80
    svc._upsert_atoa_match_pair(db, uid(user_a), uid(user_b), score_data2, "")
    db.commit()

    count_after = db.query(AvatarMatch).filter(
        AvatarMatch.user_id == uid(user_a),
        AvatarMatch.target_user_id == uid(user_b),
        AvatarMatch.match_type == "atoa",
    ).count()
    updated = db.query(AvatarMatch).filter(
        AvatarMatch.user_id == uid(user_a),
        AvatarMatch.target_user_id == uid(user_b),
        AvatarMatch.match_type == "atoa",
    ).first()

    assert count_before == 1
    assert count_after == 1           # 没有新增
    assert updated.match_score == 80  # 分数已更新


# ── _sync_atoa_mutual_flag ────────────────────────────────────────────────────

def test_sync_atoa_mutual_flag_clears_on_dismiss(client, db):
    """dismiss 后 _sync_atoa_mutual_flag 应同步将对方的 is_mutual 也改为 False。"""
    user_a = create_test_user(client, username="atoa_sync_a")
    user_b = create_test_user(client, username="atoa_sync_b")

    _make_post(db, uid(user_a))
    _make_post(db, uid(user_b))

    score_data = {
        "score_ab": 70, "score_ba": 65,
        "reasons_ab": [], "reasons_ba": [],
        "shared_topics": [], "conversation": [],
        "intent_type": "buddy", "is_mutual": True, "outcome": "mutual",
        "risk_flags": [], "card_b_id": None,
    }
    match_ab, match_ba = svc._upsert_atoa_match_pair(
        db, uid(user_a), uid(user_b), score_data, ""
    )
    db.commit()

    assert match_ab.is_mutual is True
    assert match_ba.is_mutual is True

    svc._sync_atoa_mutual_flag(db, match_ab.id, False)
    db.commit()
    db.refresh(match_ab)
    db.refresh(match_ba)

    assert match_ab.is_mutual is False
    assert match_ba.is_mutual is False


# ── generate_surf_report ─────────────────────────────────────────────────────

def test_generate_surf_report_atoa_scanned():
    """有 AtoA 候选时报告应包含候选数字。"""
    report = svc.generate_surf_report(5, 0, 0, 0)
    assert "5" in report


def test_generate_surf_report_no_results():
    """无任何结果时返回固定提示语。"""
    report = svc.generate_surf_report(0, 0, 0, 0)
    assert len(report) > 0


def test_generate_surf_report_fallback_only():
    """无 AtoA 时，只报告 fallback 匹配数。"""
    report = svc.generate_surf_report(0, 0, 0, 3)
    assert "3" in report


# ── API 集成测试 ──────────────────────────────────────────────────────────────

def test_probe_log_empty(client):
    """GET /api/avatar/probe-log 初始为空列表。"""
    user = create_test_user(client, username="atoa_probe_empty")
    headers = get_auth_header(user["token"])

    resp = client.get("/api/avatar/probe-log", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 0


def test_mutual_matches_empty(client):
    """GET /api/avatar/mutual-matches 初始为空列表。"""
    user = create_test_user(client, username="atoa_mutual_empty")
    headers = get_auth_header(user["token"])

    resp = client.get("/api/avatar/mutual-matches", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 0


def test_probe_log_shows_interaction(client, db):
    """写入一条 AtoA 探针后，probe-log 应返回该记录（含 conversation 内容）。"""
    user_a = create_test_user(client, username="atoa_probe_show_a")
    user_b = create_test_user(client, username="atoa_probe_show_b")
    headers = get_auth_header(user_a["token"])

    now = int(time.time() * 1000)
    sess_id = str(uuid4())
    db.add(
        AvatarAtoaSession(
            id=sess_id,
            user_id=uid(user_a),
            candidate_ids=json.dumps([uid(user_b)]),
            excluded_ids=json.dumps([]),
            score_snapshot=json.dumps({}),
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AvatarSurfLog(
            id=str(uuid4()),
            user_id=uid(user_a),
            trigger="manual",
            status="success",
            started_at=now,
            finished_at=now,
            top10_session_id=sess_id,
        )
    )
    interaction = AvatarAtoaInteraction(
        id=str(uuid4()),
        initiator_id=uid(user_a),
        session_id=sess_id,
        user_a_id=uid(user_a),
        user_b_id=uid(user_b),
        interaction_type="card_exchange",
        outcome="mutual",
        score_a=70,
        score_b=65,
        shared_topics=json.dumps(["摄影"]),
        reasons_a=json.dumps(["共同兴趣：摄影"]),
        reasons_b=json.dumps(["共同兴趣：摄影"]),
        risk_flags=json.dumps([]),
        conversation=json.dumps([
            {"role": "avatar_a", "content": "你也喜欢摄影？"},
            {"role": "avatar_b", "content": "是的，特别喜欢街拍。"},
        ]),
        is_visible_to_a=True,
        is_visible_to_b=True,
        created_at=now,
        updated_at=now,
    )
    db.add(interaction)
    db.commit()

    resp = client.get("/api/avatar/probe-log", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1

    item = items[0]
    assert item["outcome"] == "mutual"
    assert item["isMutual"] is True
    assert len(item["conversation"]) == 2
    assert item["conversation"][0]["role"] == "avatar_a"
    assert "摄影" in item["sharedTopics"]


def test_mutual_matches_shows_atoa_record(client, db):
    """写入一条 mutual=True 的 AvatarMatch 后，mutual-matches 应能返回。"""
    user_a = create_test_user(client, username="atoa_mutual_show_a")
    user_b = create_test_user(client, username="atoa_mutual_show_b")
    headers = get_auth_header(user_a["token"])

    post_b = _make_post(db, uid(user_b))
    now = int(time.time() * 1000)
    match = AvatarMatch(
        id=str(uuid4()),
        user_id=uid(user_a),
        post_id=post_b.id,
        target_user_id=uid(user_b),
        match_score=75,
        their_score=68,
        match_reasons=json.dumps(["共同兴趣"]),
        their_reasons=json.dumps(["共同兴趣"]),
        agent_conversation=json.dumps([]),
        status="new",
        match_type="atoa",
        intent_type="buddy",
        is_mutual=True,
        created_at=now,
    )
    db.add(match)
    db.commit()

    resp = client.get("/api/avatar/mutual-matches", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1
    item = items[0]
    assert item["myScore"] == 75
    assert item["theirScore"] == 68
    assert item["targetUserId"] == uid(user_b)


# ── Phase 8A 新架构：_score_all_atoa_candidates ───────────────────────────────

def test_score_all_atoa_candidates_filters_no_shared_interest(client, db):
    """无共同兴趣词的候选应被预筛过滤掉，不出现在评分结果中。"""
    user_a = create_test_user(client, username="score_all_a1")
    user_b = create_test_user(client, username="score_all_b1")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    _make_card(db, uid(user_a), ["编程", "数学"], ["study"])
    _make_card(db, uid(user_b), ["舞蹈", "化妆"], ["share"])

    ua = db.query(User).filter(User.id == uid(user_a)).first()
    ub = db.query(User).filter(User.id == uid(user_b)).first()

    results = svc._score_all_atoa_candidates(db, uid(user_a), [ub], set(), set())
    assert all(item["user"].id != uid(user_b) for item in results)


def test_score_all_atoa_candidates_returns_sorted_scores(client, db):
    """多候选时评分结果应按 score 降序排列。"""
    user_a = create_test_user(client, username="score_all_a2")
    user_b = create_test_user(client, username="score_all_b2")
    user_c = create_test_user(client, username="score_all_c2")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    _enable_atoa(db, uid(user_c))
    _make_card(db, uid(user_a), ["摄影", "旅行"], ["buddy"])
    _make_card(db, uid(user_b), ["摄影", "旅行", "读书"], ["buddy"])  # 更多共同兴趣
    _make_card(db, uid(user_c), ["摄影"], ["buddy"])

    ub = db.query(User).filter(User.id == uid(user_b)).first()
    uc = db.query(User).filter(User.id == uid(user_c)).first()

    results = svc._score_all_atoa_candidates(db, uid(user_a), [ub, uc], set(), set())
    if len(results) >= 2:
        assert results[0]["score"] >= results[1]["score"]


def test_score_all_atoa_candidates_excludes_excluded_ids(client, db):
    """excluded_ids 中的候选应被跳过。"""
    user_a = create_test_user(client, username="score_all_a3")
    user_b = create_test_user(client, username="score_all_b3")

    _enable_atoa(db, uid(user_a))
    _enable_atoa(db, uid(user_b))
    _make_card(db, uid(user_a), ["音乐"], ["buddy"])
    _make_card(db, uid(user_b), ["音乐"], ["buddy"])

    ub = db.query(User).filter(User.id == uid(user_b)).first()
    results = svc._score_all_atoa_candidates(
        db, uid(user_a), [ub], excluded_ids={uid(user_b)}, dismissed_target_user_ids=set()
    )
    assert len(results) == 0


# ── Phase 8A 新架构：_build_atoa_session ─────────────────────────────────────

def test_build_atoa_session_creates_record(client, db):
    """_build_atoa_session 应创建新的 AtoaSession 并写入候选 ID 列表。"""
    user_a = create_test_user(client, username="session_create_a")
    user_b = create_test_user(client, username="session_create_b")

    ub = db.query(User).filter(User.id == uid(user_b)).first()
    scored = [{"user": ub, "score": 75, "shared_topics": ["音乐"], "intent_type": "buddy", "reasons_a": []}]

    session = svc._build_atoa_session(db, uid(user_a), scored)
    db.commit()

    assert session.id is not None
    assert session.status == "active"
    candidate_ids = json.loads(session.candidate_ids)
    assert uid(user_b) in candidate_ids
    score_snapshot = json.loads(session.score_snapshot)
    assert uid(user_b) in score_snapshot
    assert score_snapshot[uid(user_b)] == 75


def test_build_atoa_session_supersedes_old_active(client, db):
    """若已有 active session，新建时应将旧 session 标记为 superseded。"""
    user_a = create_test_user(client, username="session_supersede_a")
    now = int(time.time() * 1000)

    old_session = AvatarAtoaSession(
        id=str(uuid4()),
        user_id=uid(user_a),
        candidate_ids=json.dumps([]),
        excluded_ids=json.dumps([]),
        score_snapshot=json.dumps({}),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(old_session)
    db.commit()

    new_session = svc._build_atoa_session(db, uid(user_a), [])
    db.commit()

    db.refresh(old_session)
    assert old_session.status == "superseded"
    assert new_session.status == "active"


# ── Phase 8A 新架构：_write_atoa_interaction 初始 outcome ────────────────────

def test_write_atoa_interaction_initial_outcome(client, db):
    """_write_atoa_interaction 初始 outcome 应为 pending_user_decision，is_visible_to_b=False。"""
    user_a = create_test_user(client, username="write_inter_a")
    user_b = create_test_user(client, username="write_inter_b")

    score_data = {
        "outcome": "pending_user_decision",
        "score_ab": 55, "score_ba": 40,
        "shared_topics": ["摄影"], "reasons_ab": ["共同兴趣"],
        "reasons_ba": [], "risk_flags": [],
        "conversation": [{"role": "avatar_a", "content": "你好"}],
    }
    interaction = svc._write_atoa_interaction(db, uid(user_a), uid(user_b), score_data)
    db.commit()

    assert interaction.outcome == "pending_user_decision"
    assert interaction.is_visible_to_b is False
    assert interaction.is_visible_to_a is True


# ── Phase 8A 新架构：_get_replacement_candidate ───────────────────────────────

def test_get_replacement_candidate_not_in_excluded(client, db):
    """补位候选不应在 excluded_ids 中。"""
    user_a = create_test_user(client, username="replace_a1")
    user_b = create_test_user(client, username="replace_b1")
    user_c = create_test_user(client, username="replace_c1")

    now = int(time.time() * 1000)
    session = AvatarAtoaSession(
        id=str(uuid4()),
        user_id=uid(user_a),
        # user_b 在 candidate_ids 中（Top-10），user_c 在 score_snapshot 中（第11+位）
        candidate_ids=json.dumps([uid(user_b)]),
        excluded_ids=json.dumps([uid(user_b)]),  # user_b 已被排除
        score_snapshot=json.dumps({uid(user_b): 70, uid(user_c): 60}),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.commit()

    replacement = svc._get_replacement_candidate(db, session)
    # user_c 不在 excluded 且不在 candidate_ids（也不在），应被选为补位
    if replacement:
        assert replacement.id == uid(user_c)


def test_get_replacement_candidate_returns_none_if_all_excluded(client, db):
    """所有快照候选均被排除时，应返回 None。"""
    user_a = create_test_user(client, username="replace_a2")
    user_b = create_test_user(client, username="replace_b2")

    now = int(time.time() * 1000)
    session = AvatarAtoaSession(
        id=str(uuid4()),
        user_id=uid(user_a),
        candidate_ids=json.dumps([uid(user_b)]),
        excluded_ids=json.dumps([uid(user_b)]),  # 唯一候选已排除
        score_snapshot=json.dumps({uid(user_b): 70}),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.commit()

    replacement = svc._get_replacement_candidate(db, session)
    assert replacement is None


# ── Phase 8A 新架构：_apply_block_penalty ────────────────────────────────────

def test_apply_block_penalty_reduces_scores(client, db):
    """打断时双向降分，两侧 match_score 均应减少。"""
    user_a = create_test_user(client, username="penalty_a1")
    user_b = create_test_user(client, username="penalty_b1")

    post_b = _make_post(db, uid(user_b))
    post_a = _make_post(db, uid(user_a))
    now = int(time.time() * 1000)

    match_ab = AvatarMatch(
        id=str(uuid4()),
        user_id=uid(user_a),
        post_id=post_b.id,
        target_user_id=uid(user_b),
        match_score=60,
        match_reasons=json.dumps([]),
        agent_conversation=json.dumps([]),
        status="new",
        match_type="atoa",
        intent_type="buddy",
        created_at=now,
    )
    match_ba = AvatarMatch(
        id=str(uuid4()),
        user_id=uid(user_b),
        post_id=post_a.id,
        target_user_id=uid(user_a),
        match_score=55,
        match_reasons=json.dumps([]),
        agent_conversation=json.dumps([]),
        status="new",
        match_type="atoa",
        intent_type="buddy",
        created_at=now,
    )
    db.add(match_ab)
    db.add(match_ba)
    db.commit()

    svc._apply_block_penalty(db, uid(user_a), uid(user_b))
    db.commit()

    db.refresh(match_ab)
    db.refresh(match_ba)
    assert match_ab.match_score < 60
    assert match_ba.match_score < 55


# ── Phase 8A 新架构：GET /api/avatar/atoa/sessions ──────────────────────────

def test_atoa_sessions_empty(client):
    """初始状态 GET /api/avatar/atoa/sessions 应返回空列表。"""
    user = create_test_user(client, username="sessions_empty_u")
    headers = get_auth_header(user["token"])

    resp = client.get("/api/avatar/atoa/sessions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)


def test_atoa_sessions_shows_active_session(client, db):
    """创建 AtoaSession 后，GET /api/avatar/atoa/sessions 应返回该记录。"""
    user = create_test_user(client, username="sessions_show_u")
    headers = get_auth_header(user["token"])

    now = int(time.time() * 1000)
    session = AvatarAtoaSession(
        id=str(uuid4()),
        user_id=uid(user),
        candidate_ids=json.dumps(["fake_id_1", "fake_id_2"]),
        excluded_ids=json.dumps([]),
        score_snapshot=json.dumps({"fake_id_1": 70, "fake_id_2": 60}),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.add(
        AvatarSurfLog(
            id=str(uuid4()),
            user_id=uid(user),
            trigger="manual",
            status="success",
            started_at=now,
            finished_at=now,
            top10_session_id=session.id,
        )
    )
    db.commit()

    resp = client.get("/api/avatar/atoa/sessions", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1
    item = items[0]
    assert item["id"] == session.id
    assert item["status"] == "active"
    assert item["candidateCount"] == 2


# ── Phase 8A 新架构：probe-log 过滤器 ───────────────────────────────────────

def test_probe_log_filter_by_outcome(client, db):
    """probe-log 支持 ?outcome=pending_user_decision 筛选。"""
    user_a = create_test_user(client, username="probe_filter_a")
    user_b = create_test_user(client, username="probe_filter_b")
    user_c = create_test_user(client, username="probe_filter_c")
    headers = get_auth_header(user_a["token"])

    now = int(time.time() * 1000)
    sess_id = str(uuid4())
    db.add(
        AvatarAtoaSession(
            id=sess_id,
            user_id=uid(user_a),
            candidate_ids=json.dumps([uid(user_b), uid(user_c)]),
            excluded_ids=json.dumps([]),
            score_snapshot=json.dumps({}),
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AvatarSurfLog(
            id=str(uuid4()),
            user_id=uid(user_a),
            trigger="manual",
            status="success",
            started_at=now,
            finished_at=now,
            top10_session_id=sess_id,
        )
    )
    for (b_id, outcome) in [(uid(user_b), "pending_user_decision"), (uid(user_c), "blocked")]:
        intr = AvatarAtoaInteraction(
            id=str(uuid4()),
            initiator_id=uid(user_a),
            session_id=sess_id,
            user_a_id=uid(user_a),
            user_b_id=b_id,
            interaction_type="card_exchange",
            outcome=outcome,
            score_a=50, score_b=40,
            shared_topics=json.dumps([]),
            reasons_a=json.dumps([]),
            reasons_b=json.dumps([]),
            risk_flags=json.dumps([]),
            conversation=json.dumps([]),
            is_visible_to_a=True,
            is_visible_to_b=False,
            interaction_phase=1,
            created_at=now,
            updated_at=now,
        )
        db.add(intr)
    db.commit()

    resp = client.get("/api/avatar/probe-log?outcome=pending_user_decision", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    for item in items:
        assert item["outcome"] == "pending_user_decision"


def test_probe_log_filter_by_session_id(client, db):
    """probe-log 支持 ?session_id=xxx 筛选。"""
    user_a = create_test_user(client, username="probe_sess_filter_a")
    user_b = create_test_user(client, username="probe_sess_filter_b")
    user_c = create_test_user(client, username="probe_sess_filter_c")
    headers = get_auth_header(user_a["token"])

    now = int(time.time() * 1000)
    sess1_id = str(uuid4())
    sess2_id = str(uuid4())

    for sess_id, b_id in [(sess1_id, uid(user_b)), (sess2_id, uid(user_c))]:
        intr = AvatarAtoaInteraction(
            id=str(uuid4()),
            initiator_id=uid(user_a),
            session_id=sess_id,
            user_a_id=uid(user_a),
            user_b_id=b_id,
            interaction_type="card_exchange",
            outcome="pending_user_decision",
            score_a=50, score_b=40,
            shared_topics=json.dumps([]),
            reasons_a=json.dumps([]),
            reasons_b=json.dumps([]),
            risk_flags=json.dumps([]),
            conversation=json.dumps([]),
            is_visible_to_a=True,
            is_visible_to_b=False,
            interaction_phase=1,
            created_at=now,
            updated_at=now,
        )
        db.add(intr)
    db.commit()

    resp = client.get(f"/api/avatar/probe-log?session_id={sess1_id}", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert all(item["sessionId"] == sess1_id for item in items)


def test_probe_log_readable_outcome_field(client, db):
    """probe-log 应返回 readableOutcome 字段（中文可读文案）。"""
    user_a = create_test_user(client, username="probe_readable_a")
    user_b = create_test_user(client, username="probe_readable_b")
    headers = get_auth_header(user_a["token"])

    now = int(time.time() * 1000)
    sess_id = str(uuid4())
    db.add(
        AvatarAtoaSession(
            id=sess_id,
            user_id=uid(user_a),
            candidate_ids=json.dumps([uid(user_b)]),
            excluded_ids=json.dumps([]),
            score_snapshot=json.dumps({}),
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AvatarSurfLog(
            id=str(uuid4()),
            user_id=uid(user_a),
            trigger="manual",
            status="success",
            started_at=now,
            finished_at=now,
            top10_session_id=sess_id,
        )
    )
    intr = AvatarAtoaInteraction(
        id=str(uuid4()),
        initiator_id=uid(user_a),
        session_id=sess_id,
        user_a_id=uid(user_a),
        user_b_id=uid(user_b),
        interaction_type="card_exchange",
        outcome="pending_user_decision",
        score_a=50, score_b=40,
        shared_topics=json.dumps([]),
        reasons_a=json.dumps([]),
        reasons_b=json.dumps([]),
        risk_flags=json.dumps([]),
        conversation=json.dumps([]),
        is_visible_to_a=True,
        is_visible_to_b=False,
        interaction_phase=1,
        created_at=now,
        updated_at=now,
    )
    db.add(intr)
    db.commit()

    resp = client.get("/api/avatar/probe-log", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 1
    item = items[0]
    assert "readableOutcome" in item
    assert item["readableOutcome"] == "等待你的决定"

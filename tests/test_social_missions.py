"""找人任务 P0 链路测试。"""
import time
from uuid import uuid4

from app.models.social import MissionCandidate
from tests.conftest import create_test_user, get_auth_header


def _create_short_mission(client, headers, **overrides):
    now = int(time.time() * 1000)
    start_at = now + 24 * 60 * 60 * 1000
    end_at = start_at + 2 * 24 * 60 * 60 * 1000
    payload = {
        "mode": "short_term",
        "purpose_type": "movie",
        "title": "本周末看电影",
        "description": "周末想找一个人一起看科幻电影",
        "source": "natural_language",
        "time_window": {
            "label": "本周末",
            "startAt": start_at,
            "endAt": end_at,
            "flexibilityMinutes": 120,
        },
        "location": {
            "label": "南开大学",
            "radiusKm": 5,
            "precision": "campus",
        },
        "headcount": {"current": 1, "wanted": 1, "allowWaitlist": True},
        "budget": {"type": "aa"},
        "must_haves": [],
        "preferences": ["科幻", "周末"],
        "boundaries": ["先由分身问清楚时间"],
        "public_memory_ids": [],
        "permissions": {
            "search": True,
            "atoaProbe": True,
            "draftPost": True,
            "draftReply": True,
            "autoPublish": False,
            "autoConnect": False,
        },
        "search_strategy": "search_then_draft",
        "expires_at": end_at,
    }
    payload.update(overrides)
    response = client.post("/api/social/missions", json=payload, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()["data"]


def test_parse_natural_language_mission(client):
    user = create_test_user(client, username="mission_parse")
    headers = get_auth_header(user["token"])

    response = client.post(
        "/api/social/missions/parse",
        json={"text": "周末想找一个人看科幻电影，最好是同校"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["draft"]["mode"] == "short_term"
    assert data["draft"]["purposeType"] == "movie"
    assert data["draft"]["permissions"]["autoPublish"] is False
    assert data["draft"]["permissions"]["autoConnect"] is False
    assert "周末" in data["draft"]["timeWindow"]["label"]


def test_short_mission_search_and_probe_existing_post(client):
    seeker = create_test_user(client, username="mission_seek")
    host = create_test_user(client, username="mission_host", name="电影发起人")
    seeker_headers = get_auth_header(seeker["token"])
    host_headers = get_auth_header(host["token"])

    post_response = client.post(
        "/api/plaza/posts",
        json={
            "type": "buddy",
            "content": "本周六想找一位同学一起看科幻电影，新朋友也欢迎。",
            "location": "南开大学",
            "tags": ["电影", "科幻", "周末"],
            "allow_agent_reply": True,
            "school_only": True,
        },
        headers=host_headers,
    )
    assert post_response.status_code == 200
    post_id = post_response.json()["data"]["id"]

    mission = _create_short_mission(client, seeker_headers)
    start_response = client.post(
        f"/api/social/missions/{mission['id']}/start",
        headers=seeker_headers,
    )
    assert start_response.status_code == 200, start_response.json()
    result = start_response.json()["data"]
    assert result["matchedCount"] >= 1
    candidate = next(
        item for item in result["candidates"] if item["targetPostId"] == post_id
    )
    assert candidate["hardConstraintResult"]["activity"] == "pass"
    assert candidate["targetUser"]["name"] == "电影发起人"

    probe_response = client.post(
        f"/api/social/missions/{mission['id']}/candidates/{candidate['id']}/probe",
        headers=seeker_headers,
    )
    assert probe_response.status_code == 200, probe_response.json()
    probe = probe_response.json()["data"]
    assert probe["interactionId"]
    assert probe["sessionId"]
    assert probe["candidate"]["status"] == "ready_for_user"

    probe_log = client.get(
        f"/api/avatar/probe-log?session_id={probe['sessionId']}",
        headers=seeker_headers,
    )
    assert probe_log.status_code == 200
    assert probe_log.json()["data"][0]["id"] == probe["interactionId"]

    connect_response = client.post(
        f"/api/avatar/atoa/{probe['interactionId']}/decide",
        json={
            "decision": "connect",
            "opening_message": "时间和活动内容都合适，想申请一起参加。",
        },
        headers=seeker_headers,
    )
    assert connect_response.status_code == 200, connect_response.json()
    match_id = connect_response.json()["data"]["socialMatchId"]

    accept_response = client.post(
        f"/api/social/buddy/{match_id}/respond",
        json={"accept": True},
        headers=host_headers,
    )
    assert accept_response.status_code == 200, accept_response.json()

    room_response = client.get(
        f"/api/social/activity-rooms/{match_id}",
        headers=seeker_headers,
    )
    assert room_response.status_code == 200, room_response.json()
    room = room_response.json()["data"]
    assert room["missionId"] == mission["id"]
    assert room["title"] == "本周末看电影"
    assert len(room["participants"]) == 2

    # 活动房间的匹配报告：双方拿到同一份，分数已规范化到 0~100
    seeker_report = client.get(
        f"/api/social/matches/{match_id}/report",
        headers=seeker_headers,
    )
    assert seeker_report.status_code == 200, seeker_report.json()
    score = seeker_report.json()["data"]["compatibility"]
    assert isinstance(score, int)
    assert 0 <= score <= 100
    host_report = client.get(
        f"/api/social/matches/{match_id}/report",
        headers=host_headers,
    )
    assert host_report.status_code == 200, host_report.json()
    assert host_report.json()["data"]["compatibility"] == score


def test_mission_post_draft_requires_user_publish(client):
    user = create_test_user(client, username="mission_publish")
    headers = get_auth_header(user["token"])
    mission = _create_short_mission(
        client,
        headers,
        purpose_type="murder_mystery",
        title="周六新手剧本杀",
        description="想组一个新手友好的欢乐本，不玩重恐",
        preferences=["新手友好", "欢乐本", "不玩重恐"],
        headcount={"current": 2, "wanted": 3, "allowWaitlist": True},
    )

    draft_response = client.post(
        f"/api/social/missions/{mission['id']}/post-draft",
        headers=headers,
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()["data"]
    assert "新手剧本杀" in draft["content"]
    assert "发布前已由本人确认" in draft["content"]

    mission_before = client.get(
        f"/api/social/missions/{mission['id']}",
        headers=headers,
    ).json()["data"]
    assert mission_before["linkedPostId"] is None

    publish_response = client.post(
        f"/api/social/missions/{mission['id']}/publish",
        json={
            "content": draft["content"],
            "location": draft["location"],
            "tags": draft["tags"],
            "school_only": draft["schoolOnly"],
            "allow_agent_reply": draft["allowAgentReply"],
        },
        headers=headers,
    )
    assert publish_response.status_code == 200, publish_response.json()
    post = publish_response.json()["data"]
    assert post["isFromAgent"] is True

    mission_after = client.get(
        f"/api/social/missions/{mission['id']}",
        headers=headers,
    ).json()["data"]
    assert mission_after["linkedPostId"] == post["id"]
    assert mission_after["status"] == "posting"


def test_agent_mission_post_is_public_by_default_and_keeps_explicit_school_scope(client):
    """校园地点不应暗改为仅本校；用户明确写同校时仍保留可见性边界。"""
    author = create_test_user(
        client,
        username="missionvisauthor",
        school="南开大学",
    )
    outsider = create_test_user(
        client,
        username="missionvisoutside",
        school="天津大学",
    )
    author_headers = get_auth_header(author["token"])
    outsider_headers = get_auth_header(outsider["token"])

    public_mission = _create_short_mission(client, author_headers)
    public_draft = client.post(
        f"/api/social/missions/{public_mission['id']}/post-draft",
        headers=author_headers,
    ).json()["data"]
    assert public_draft["schoolOnly"] is False
    public_post = client.post(
        f"/api/social/missions/{public_mission['id']}/publish",
        json={
            "content": public_draft["content"],
            "location": public_draft["location"],
            "tags": public_draft["tags"],
            "school_only": public_draft["schoolOnly"],
            "allow_agent_reply": public_draft["allowAgentReply"],
        },
        headers=author_headers,
    ).json()["data"]
    outsider_ids = [
        item["id"]
        for item in client.get("/api/plaza/posts", headers=outsider_headers).json()["data"]["items"]
    ]
    assert public_post["id"] in outsider_ids
    assert public_post["isFromAgent"] is True

    school_mission = _create_short_mission(
        client,
        author_headers,
        title="仅找同校电影搭子",
        preferences=["科幻", "同校"],
    )
    school_draft = client.post(
        f"/api/social/missions/{school_mission['id']}/post-draft",
        headers=author_headers,
    ).json()["data"]
    assert school_draft["schoolOnly"] is True
    school_post = client.post(
        f"/api/social/missions/{school_mission['id']}/publish",
        json={
            "content": school_draft["content"],
            "location": school_draft["location"],
            "tags": school_draft["tags"],
            "school_only": True,
            "allow_agent_reply": True,
        },
        headers=author_headers,
    ).json()["data"]
    outsider_ids = [
        item["id"]
        for item in client.get("/api/plaza/posts", headers=outsider_headers).json()["data"]["items"]
    ]
    assert school_post["id"] not in outsider_ids


def test_recent_candidates_dedupe_by_user_and_keep_actionable_record(client, db):
    owner = create_test_user(client, username="candidateowner")
    target = create_test_user(client, username="candidatetarget", name="同一个候选")
    headers = get_auth_header(owner["token"])
    mission = _create_short_mission(client, headers)
    now = int(time.time() * 1000)
    common = {
        "mission_id": mission["id"],
        "target_user_id": target["user"]["id"],
        "source": "plaza_post",
        "hard_constraint_result": "{}",
        "conflicts": "[]",
        "risk_flags": "[]",
        "internal_score": 80,
        "created_at": now,
    }
    db.add_all([
        MissionCandidate(
            id=str(uuid4()),
            status="ready_for_user",
            fit_reasons='[{"text":"报告完整"}]',
            questions='["时间合适吗？"]',
            interaction_id="interaction-existing",
            updated_at=now,
            **common,
        ),
        MissionCandidate(
            id=str(uuid4()),
            status="expired",
            fit_reasons="[]",
            questions="[]",
            interaction_id=None,
            updated_at=now + 1000,
            **common,
        ),
    ])
    db.commit()

    response = client.get(
        f"/api/social/missions/{mission['id']}/candidates",
        headers=headers,
    )
    assert response.status_code == 200
    candidates = response.json()["data"]
    assert len(candidates) == 1
    assert candidates[0]["status"] == "ready_for_user"
    assert candidates[0]["interactionId"] == "interaction-existing"


def test_candidates_and_recruitment_post_run_in_parallel_and_publish_is_idempotent(client):
    owner = create_test_user(client, username="parallelowner")
    candidate_user = create_test_user(client, username="parallelcandidate", name="候选用户")
    owner_headers = get_auth_header(owner["token"])
    candidate_headers = get_auth_header(candidate_user["token"])
    client.post(
        "/api/plaza/posts",
        json={
            "type": "buddy",
            "content": "周末一起看科幻电影",
            "location": "南开大学",
            "tags": ["电影", "科幻", "周末"],
        },
        headers=candidate_headers,
    )
    mission = _create_short_mission(client, owner_headers)
    search = client.post(
        f"/api/social/missions/{mission['id']}/start",
        headers=owner_headers,
    ).json()["data"]
    assert len(search["candidates"]) == 1

    draft = client.post(
        f"/api/social/missions/{mission['id']}/post-draft",
        headers=owner_headers,
    ).json()["data"]
    payload = {
        "content": draft["content"],
        "location": draft["location"],
        "tags": draft["tags"],
        "school_only": draft["schoolOnly"],
        "allow_agent_reply": draft["allowAgentReply"],
    }
    first = client.post(
        f"/api/social/missions/{mission['id']}/publish",
        json=payload,
        headers=owner_headers,
    ).json()["data"]
    second = client.post(
        f"/api/social/missions/{mission['id']}/publish",
        json={**payload, "content": "不应重复发布"},
        headers=owner_headers,
    ).json()["data"]
    assert first["id"] == second["id"]
    candidates = client.get(
        f"/api/social/missions/{mission['id']}/candidates",
        headers=owner_headers,
    ).json()["data"]
    assert len(candidates) == 1
    assert candidates[0]["targetUserId"] == candidate_user["user"]["id"]


def test_post_response_reuses_source_mission_probe_and_rejects_owner(client, db):
    owner = create_test_user(client, username="responseowner", name="招募者")
    responder = create_test_user(client, username="responder", name="响应者")
    owner_headers = get_auth_header(owner["token"])
    responder_headers = get_auth_header(responder["token"])
    mission = _create_short_mission(client, owner_headers)
    draft = client.post(
        f"/api/social/missions/{mission['id']}/post-draft",
        headers=owner_headers,
    ).json()["data"]
    post = client.post(
        f"/api/social/missions/{mission['id']}/publish",
        json={
            "content": draft["content"],
            "location": draft["location"],
            "tags": draft["tags"],
            "school_only": False,
            "allow_agent_reply": True,
        },
        headers=owner_headers,
    ).json()["data"]
    assert post["missionId"] == mission["id"]

    self_response = client.post(
        f"/api/social/mission-posts/{post['id']}/respond",
        headers=owner_headers,
    )
    assert self_response.status_code == 403
    assert client.get(
        f"/api/social/missions/{mission['id']}/candidates",
        headers=owner_headers,
    ).json()["data"] == []

    first = client.post(
        f"/api/social/mission-posts/{post['id']}/respond",
        headers=responder_headers,
    )
    assert first.status_code == 200, first.json()
    first_data = first.json()["data"]
    second = client.post(
        f"/api/social/mission-posts/{post['id']}/respond",
        headers=responder_headers,
    )
    assert second.status_code == 200, second.json()
    second_data = second.json()["data"]
    assert first_data["missionId"] == mission["id"]
    assert first_data["interactionId"] == second_data["interactionId"]
    assert first_data["sessionId"] == second_data["sessionId"]
    assert first_data["candidate"]["id"] == second_data["candidate"]["id"]
    assert second_data["candidate"]["status"] == "ready_for_user"

    candidates = client.get(
        f"/api/social/missions/{mission['id']}/candidates",
        headers=owner_headers,
    ).json()["data"]
    assert len(candidates) == 1
    assert candidates[0]["targetUserId"] == responder["user"]["id"]
    assert candidates[0]["interactionId"] == first_data["interactionId"]
    assert client.get("/api/social/missions", headers=responder_headers).json()["data"] == []

    responder_view = client.get(
        f"/api/avatar/probe-log?session_id={first_data['sessionId']}",
        headers=responder_headers,
    )
    assert responder_view.status_code == 200
    assert responder_view.json()["data"][0]["id"] == first_data["interactionId"]
    assert responder_view.json()["data"][0]["userBId"] == owner["user"]["id"]

    # 打开试聊不依赖 session_id（真机 query 丢 camelCase 时仍可打开）
    by_id_b = client.get(
        f"/api/avatar/atoa/{first_data['interactionId']}",
        headers=responder_headers,
    )
    assert by_id_b.status_code == 200, by_id_b.json()
    assert by_id_b.json()["data"]["id"] == first_data["interactionId"]
    assert by_id_b.json()["data"]["userBId"] == owner["user"]["id"]

    by_id_a = client.get(
        f"/api/avatar/atoa/{first_data['interactionId']}",
        headers=owner_headers,
    )
    assert by_id_a.status_code == 200, by_id_a.json()
    assert by_id_a.json()["data"]["id"] == first_data["interactionId"]
    assert by_id_a.json()["data"]["userBId"] == responder["user"]["id"]

    # 只有这段 AtoA 的双方能看，其他人一律拒绝
    outsider = create_test_user(client, username="atoaoutsider", name="旁观者")
    outsider_view = client.get(
        f"/api/avatar/atoa/{first_data['interactionId']}",
        headers=get_auth_header(outsider["token"]),
    )
    assert outsider_view.status_code == 403, outsider_view.json()

    # 旧 id 自动落到同会话同配对的最新可访问一轮
    from app.models.avatar import AvatarAtoaInteraction

    original = db.query(AvatarAtoaInteraction).filter(
        AvatarAtoaInteraction.id == first_data["interactionId"]
    ).first()
    assert original is not None
    stale = AvatarAtoaInteraction(
        id=str(uuid4()),
        initiator_id=original.user_a_id,
        session_id=original.session_id,
        user_a_id=original.user_a_id,
        user_b_id=original.user_b_id,
        interaction_type="card_exchange",
        outcome="pending_user_decision",
        score_a=10,
        score_b=10,
        shared_topics=original.shared_topics,
        reasons_a=original.reasons_a,
        reasons_b=original.reasons_b,
        risk_flags=original.risk_flags,
        conversation=original.conversation,
        is_visible_to_a=True,
        is_visible_to_b=True,
        interaction_phase=1,
        created_at=(original.created_at or 0) - 1000,
        updated_at=(original.updated_at or 0) - 1000,
    )
    db.add(stale)
    db.commit()

    resolved = client.get(
        f"/api/avatar/atoa/{stale.id}",
        headers=responder_headers,
    )
    assert resolved.status_code == 200, resolved.json()
    assert resolved.json()["data"]["id"] == first_data["interactionId"]


def test_pause_resume_and_close_mission(client):
    user = create_test_user(client, username="mission_state")
    headers = get_auth_header(user["token"])
    mission = _create_short_mission(client, headers)

    client.post(f"/api/social/missions/{mission['id']}/start", headers=headers)
    pause = client.post(
        f"/api/social/missions/{mission['id']}/pause",
        headers=headers,
    )
    assert pause.status_code == 200
    assert pause.json()["data"]["status"] == "paused"

    resume = client.post(
        f"/api/social/missions/{mission['id']}/resume",
        headers=headers,
    )
    assert resume.status_code == 200
    assert resume.json()["data"]["status"] == "searching"

    close = client.post(
        f"/api/social/missions/{mission['id']}/close",
        headers=headers,
    )
    assert close.status_code == 200
    assert close.json()["data"]["status"] == "cancelled"

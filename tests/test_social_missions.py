"""找人任务 P0 链路测试。"""
import time

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

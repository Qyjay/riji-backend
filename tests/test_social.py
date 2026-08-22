"""
社交模块测试
"""
import json

import pytest
from app.config import settings
from tests.conftest import create_test_user, get_auth_header


def test_list_matches_bare_array(client):
    """GET /social/matches 返回裸数组"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/social/matches", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)


def test_create_match_request(client):
    user1_data = create_test_user(client, username="user1social")
    user2_data = create_test_user(client, username="user2social")
    headers1 = get_auth_header(user1_data["token"])

    target_id = user2_data["user"]["id"]
    resp = client.post("/api/social/match-requests", json={
        "toUid": target_id,
    }, headers=headers1)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    req = data["data"]
    assert "fromUid" in req
    assert "toUid" in req
    assert req["status"] == "pending"


def test_respond_match_request(client):
    user1_data = create_test_user(client, username="matchreq1")
    user2_data = create_test_user(client, username="matchreq2")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])

    # user1 发请求给 user2
    target_id = user2_data["user"]["id"]
    req_resp = client.post("/api/social/match-requests", json={"toUid": target_id}, headers=headers1)
    request_id = req_resp.json()["data"]["id"]

    # user2 接受（accept: bool，不是 action: string）
    resp = client.post(f"/api/social/match-requests/{request_id}/respond", json={
        "accept": True
    }, headers=headers2)
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert resp.json()["data"] is None


def test_list_matches_include_pending_shows_buddy(client):
    """默认 GET /social/matches 不含 pending；include_pending=true 可核对搭子申请"""
    user1_data = create_test_user(client, username="pendmatch1")
    user2_data = create_test_user(client, username="pendmatch2")
    headers1 = get_auth_header(user1_data["token"])
    target_id = user2_data["user"]["id"]
    apply_resp = client.post(
        "/api/social/buddy",
        json={"target_user_id": target_id, "reason": "测 pending 列表"},
        headers=headers1,
    )
    assert apply_resp.status_code == 200
    request_id = apply_resp.json()["data"]["id"]

    default_resp = client.get("/api/social/matches", headers=headers1)
    assert default_resp.status_code == 200
    assert all(m["id"] != request_id for m in default_resp.json()["data"])

    pend_resp = client.get("/api/social/matches?include_pending=true", headers=headers1)
    assert pend_resp.status_code == 200
    pend_data = pend_resp.json()["data"]
    row = next((m for m in pend_data if m["id"] == request_id), None)
    assert row is not None
    assert row["status"] == "pending"
    assert row["matchType"] == "buddy"


def test_list_matches_exposes_other_user_id(client):
    """GET /social/matches 的 userId 必须是对方用户，两种 requestDirection 都不能返回自己的 id"""
    user1_data = create_test_user(client, username="matchuid1", name="发起方甲")
    user2_data = create_test_user(client, username="matchuid2", name="接收方乙")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])
    user1_id = user1_data["user"]["id"]
    user2_id = user2_data["user"]["id"]

    req_resp = client.post("/api/social/match-requests", json={"toUid": user2_id}, headers=headers1)
    request_id = req_resp.json()["data"]["id"]
    client.post(
        f"/api/social/match-requests/{request_id}/respond",
        json={"accept": True},
        headers=headers2,
    )

    outgoing = client.get("/api/social/matches", headers=headers1).json()["data"]
    assert outgoing
    assert all(item.get("userId") for item in outgoing)
    mine = next(item for item in outgoing if item["id"] == request_id)
    assert mine["requestDirection"] == "outgoing"
    assert mine["userId"] == user2_id
    assert mine["userId"] != user1_id
    # userId 与 nickname / school 必须指向同一条 User 记录
    assert mine["nickname"] == "接收方乙"
    assert mine["school"] == "南开大学"

    incoming = client.get("/api/social/matches", headers=headers2).json()["data"]
    assert incoming
    assert all(item.get("userId") for item in incoming)
    theirs = next(item for item in incoming if item["id"] == request_id)
    assert theirs["requestDirection"] == "incoming"
    assert theirs["userId"] == user1_id
    assert theirs["userId"] != user2_id
    assert theirs["nickname"] == "发起方甲"


def test_list_matches_exposes_other_user_id_for_pending_buddy(client):
    """待处理搭子申请也要带 userId，前端不必等接受后才能精确关联"""
    user1_data = create_test_user(client, username="buddyuid1", name="申请方甲")
    user2_data = create_test_user(client, username="buddyuid2", name="被申请乙")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])
    user1_id = user1_data["user"]["id"]
    user2_id = user2_data["user"]["id"]

    apply_resp = client.post(
        "/api/social/buddy",
        json={"target_user_id": user2_id, "reason": "测 userId"},
        headers=headers1,
    )
    request_id = apply_resp.json()["data"]["id"]

    sender_row = next(
        item
        for item in client.get("/api/social/matches?include_pending=true", headers=headers1).json()["data"]
        if item["id"] == request_id
    )
    assert sender_row["userId"] == user2_id

    receiver_row = next(
        item
        for item in client.get("/api/social/matches?include_pending=true", headers=headers2).json()["data"]
        if item["id"] == request_id
    )
    assert receiver_row["userId"] == user1_id


def test_list_matches_renders_json_report_as_readable_reason(client, db):
    """关系进度不应把结构化匹配报告的 JSON 原文直接展示给用户。"""
    from app.models.social import Match

    user1_data = create_test_user(client, username="reasonjson1")
    user2_data = create_test_user(client, username="reasonjson2")
    headers1 = get_auth_header(user1_data["token"])
    target_id = user2_data["user"]["id"]

    apply_resp = client.post(
        "/api/social/buddy",
        json={"target_user_id": target_id, "reason": "临时原因"},
        headers=headers1,
    )
    request_id = apply_resp.json()["data"]["id"]
    match = db.query(Match).filter(Match.id == request_id).one()
    match.match_report = json.dumps(
        {
            "compatibility": 83,
            "analysis": "双方表达方式互补，适合继续交流。",
            "common_points": ["摄影", "校园生活"],
            "differences": ["专业背景不同"],
        },
        ensure_ascii=False,
    )
    db.commit()

    response = client.get("/api/social/matches?include_pending=true", headers=headers1)
    row = next(item for item in response.json()["data"] if item["id"] == request_id)
    assert row["reason"] == "双方表达方式互补，适合继续交流。"
    assert not row["reason"].lstrip().startswith("{")


def test_buddy_request_uses_target_user_id(client):
    """POST /social/buddy 前端发的是 target_user_id"""
    user1_data = create_test_user(client, username="buddy1")
    user2_data = create_test_user(client, username="buddy2")
    headers1 = get_auth_header(user1_data["token"])

    target_id = user2_data["user"]["id"]
    resp = client.post("/api/social/buddy", json={
        "target_user_id": target_id,
    }, headers=headers1)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    buddy = data["data"]
    assert "fromUid" in buddy
    assert "toUid" in buddy
    assert buddy["status"] == "pending"


@pytest.mark.parametrize("accept, expected_status", [(True, "accepted"), (False, "rejected")])
def test_buddy_request_full_flow(client, accept, expected_status):
    """搭子申请完整链路：申请后可被接受或拒绝"""
    user1_data = create_test_user(client, username=f"buddyflowa{int(accept)}")
    user2_data = create_test_user(client, username=f"buddyflowb{int(accept)}")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])

    target_id = user2_data["user"]["id"]
    apply_resp = client.post(
        "/api/social/buddy",
        json={"target_user_id": target_id, "reason": "一起运动打卡"},
        headers=headers1,
    )
    assert apply_resp.status_code == 200
    apply_data = apply_resp.json()
    assert apply_data["code"] == 0
    request_id = apply_data["data"]["id"]
    assert apply_data["data"]["status"] == "pending"

    respond_resp = client.post(
        f"/api/social/buddy/{request_id}/respond",
        json={"accept": accept},
        headers=headers2,
    )
    assert respond_resp.status_code == 200
    respond_data = respond_resp.json()
    assert respond_data["code"] == 0
    assert respond_data["data"] is None

    # 同步复用匹配列表接口验证 accepted 分支能进入已匹配列表
    matches_resp = client.get("/api/social/matches", headers=headers1)
    assert matches_resp.status_code == 200
    matches_data = matches_resp.json()
    assert matches_data["code"] == 0
    if accept:
        assert any(item["id"] == request_id for item in matches_data["data"])
    else:
        assert all(item["id"] != request_id for item in matches_data["data"])


def test_messages_bare_array(client):
    """GET /social/messages/{matchId} 返回裸数组"""
    user1_data = create_test_user(client, username="msg1")
    user2_data = create_test_user(client, username="msg2")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])

    # 建立匹配
    target_id = user2_data["user"]["id"]
    req_resp = client.post("/api/social/match-requests", json={"toUid": target_id}, headers=headers1)
    request_id = req_resp.json()["data"]["id"]
    client.post(f"/api/social/match-requests/{request_id}/respond", json={"accept": True}, headers=headers2)

    # 注意：匹配 ID 和请求 ID 是同一个
    resp = client.get(f"/api/social/messages/{request_id}", headers=headers1)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)


def test_messages_are_aggregated_across_matches_with_same_user(client, db):
    """同一对用户跨事件的 match 均保留，但任一已接受会话能读取完整历史。"""
    import time
    from uuid import uuid4

    from app.models.social import Match, SocialMessage

    user1 = create_test_user(client, username="msgaggregate1")
    user2 = create_test_user(client, username="msgaggregate2")
    headers1 = get_auth_header(user1["token"])
    now = int(time.time() * 1000)
    old_match_id = str(uuid4())
    new_match_id = str(uuid4())
    db.add_all([
        Match(
            id=old_match_id,
            user_id=user1["user"]["id"],
            target_id=user2["user"]["id"],
            status="accepted",
            match_type="buddy",
            common_tags="[]",
            created_at=now - 1000,
        ),
        Match(
            id=new_match_id,
            user_id=user2["user"]["id"],
            target_id=user1["user"]["id"],
            status="accepted",
            match_type="buddy",
            common_tags="[]",
            created_at=now,
        ),
        SocialMessage(
            id=str(uuid4()),
            match_id=old_match_id,
            from_uid=user1["user"]["id"],
            content="上一事件的消息",
            timestamp=now - 900,
        ),
        SocialMessage(
            id=str(uuid4()),
            match_id=new_match_id,
            from_uid=user2["user"]["id"],
            content="本事件的消息",
            timestamp=now + 100,
        ),
    ])
    db.commit()

    response = client.get(f"/api/social/messages/{new_match_id}", headers=headers1)
    assert response.status_code == 200
    assert [item["content"] for item in response.json()["data"]] == [
        "上一事件的消息",
        "本事件的消息",
    ]
    assert db.query(Match).filter(
        Match.user_id.in_([user1["user"]["id"], user2["user"]["id"]]),
        Match.target_id.in_([user1["user"]["id"], user2["user"]["id"]]),
    ).count() == 2


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"score": 0.9}, 90),
        ({"compatibility": 0.9}, 90),
        ({"matchScore": 90}, 90),
        ({"match_score": 90}, 90),
        ({"compatibility": "0.9"}, 90),
        ({"compatibility": 120}, 100),
        ({"compatibility": -5}, 0),
        ({"compatibility": "不是数字"}, 75),
        ({"analysis": "缺少分数"}, 75),
        ({}, 75),
    ],
)
def test_match_report_score_normalization(payload, expected):
    """报告兼容多种分数字段和 0~1/0~100 两类量纲。"""
    from app.social.service import _normalize_match_report

    assert _normalize_match_report(payload)["compatibility"] == expected


def test_match_report_keeps_buddy_reason_in_list(client, db):
    """生成报告不能覆盖搭子申请理由：列表仍显示用户写的理由。"""
    from app.models.social import Match

    applicant = create_test_user(client, username="reasonkeep1")
    receiver = create_test_user(client, username="reasonkeep2")
    applicant_headers = get_auth_header(applicant["token"])
    receiver_headers = get_auth_header(receiver["token"])

    apply_resp = client.post(
        "/api/social/buddy",
        json={"target_user_id": receiver["user"]["id"], "reason": "周末一起看科幻电影"},
        headers=applicant_headers,
    )
    assert apply_resp.status_code == 200, apply_resp.json()
    match_id = apply_resp.json()["data"]["id"]
    client.post(
        f"/api/social/buddy/{match_id}/respond",
        json={"accept": True},
        headers=receiver_headers,
    )

    report = client.get(f"/api/social/matches/{match_id}/report", headers=applicant_headers)
    assert report.status_code == 200, report.json()
    assert 0 <= report.json()["data"]["compatibility"] <= 100

    db.expire_all()
    assert db.query(Match).filter(Match.id == match_id).first().match_report
    matches = client.get("/api/social/matches", headers=applicant_headers).json()["data"]
    entry = next(item for item in matches if item["id"] == match_id)
    assert entry["reason"] == "周末一起看科幻电影"


def test_match_report_uses_representative_match_across_events(client, db):
    """同一对用户跨事件多条 accepted match 时，报告统一取代表 match。"""
    import time
    from uuid import uuid4

    from app.models.social import Match
    from app.social.service import _representative_match_for_pair

    user1 = create_test_user(client, username="reportpair1")
    user2 = create_test_user(client, username="reportpair2")
    headers1 = get_auth_header(user1["token"])
    headers2 = get_auth_header(user2["token"])
    now = int(time.time() * 1000)

    old_match_id = str(uuid4())
    new_match_id = str(uuid4())
    db.add_all([
        Match(
            id=old_match_id,
            user_id=user1["user"]["id"],
            target_id=user2["user"]["id"],
            status="accepted",
            match_type="buddy",
            common_tags="[]",
            created_at=now - 1000,
        ),
        Match(
            id=new_match_id,
            user_id=user2["user"]["id"],
            target_id=user1["user"]["id"],
            status="accepted",
            match_type="buddy",
            common_tags="[]",
            created_at=now,
        ),
    ])
    db.commit()

    representative = _representative_match_for_pair(
        db, db.query(Match).filter(Match.id == old_match_id).first()
    )
    assert representative.id == new_match_id

    from_old = client.get(f"/api/social/matches/{old_match_id}/report", headers=headers1)
    from_new = client.get(f"/api/social/matches/{new_match_id}/report", headers=headers2)
    assert from_old.status_code == 200, from_old.json()
    assert from_new.status_code == 200, from_new.json()
    score = from_old.json()["data"]["compatibility"]
    assert 0 <= score <= 100
    assert from_new.json()["data"]["compatibility"] == score
    assert db.query(Match).filter(Match.id == old_match_id).first().match_report in (None, "")


def test_send_message_after_match_accepted(client):
    """POST /social/messages/{matchId} 在匹配通过后可发送消息"""
    user1_data = create_test_user(client, username="sendmsg1")
    user2_data = create_test_user(client, username="sendmsg2")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])

    target_id = user2_data["user"]["id"]
    req_resp = client.post("/api/social/match-requests", json={"toUid": target_id}, headers=headers1)
    request_id = req_resp.json()["data"]["id"]
    client.post(f"/api/social/match-requests/{request_id}/respond", json={"accept": True}, headers=headers2)

    resp = client.post(
        f"/api/social/messages/{request_id}",
        json={"content": "你好，很高兴认识你"},
        headers=headers1,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    message = data["data"]
    assert message["matchId"] == request_id
    assert message["fromUid"] == user1_data["user"]["id"]
    assert message["content"] == "你好，很高兴认识你"


def test_send_message_requires_accepted_match(client):
    """POST /social/messages/{matchId} 未接受匹配时禁止发送消息"""
    user1_data = create_test_user(client, username="sendmsgpending1")
    user2_data = create_test_user(client, username="sendmsgpending2")
    headers1 = get_auth_header(user1_data["token"])

    target_id = user2_data["user"]["id"]
    req_resp = client.post("/api/social/match-requests", json={"toUid": target_id}, headers=headers1)
    request_id = req_resp.json()["data"]["id"]

    resp = client.post(
        f"/api/social/messages/{request_id}",
        json={"content": "现在可以发吗"},
        headers=headers1,
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["code"] == 40102
    assert data["message"] == "匹配未通过，暂时不能发送消息"


def test_send_message_forbidden_for_non_member(client):
    """POST /social/messages/{matchId} 非匹配双方不能发送消息"""
    user1_data = create_test_user(client, username="sendmsga1")
    user2_data = create_test_user(client, username="sendmsga2")
    user3_data = create_test_user(client, username="sendmsga3")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])
    headers3 = get_auth_header(user3_data["token"])

    target_id = user2_data["user"]["id"]
    req_resp = client.post("/api/social/match-requests", json={"toUid": target_id}, headers=headers1)
    request_id = req_resp.json()["data"]["id"]
    client.post(f"/api/social/match-requests/{request_id}/respond", json={"accept": True}, headers=headers2)

    resp = client.post(
        f"/api/social/messages/{request_id}",
        json={"content": "我是第三方用户"},
        headers=headers3,
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == 40202
    assert data["message"] == "匹配不存在"


def test_create_match_request_rejects_duplicate(client):
    """POST /social/match-requests 重复请求会被拦截"""
    user1_data = create_test_user(client, username="dupsocial1")
    user2_data = create_test_user(client, username="dupsocial2")
    headers1 = get_auth_header(user1_data["token"])

    target_id = user2_data["user"]["id"]
    first_resp = client.post("/api/social/match-requests", json={"toUid": target_id}, headers=headers1)
    assert first_resp.status_code == 200

    resp = client.post("/api/social/match-requests", json={"toUid": target_id}, headers=headers1)
    assert resp.status_code == 400
    data = resp.json()
    assert data["code"] == 40102
    assert data["message"] == "已存在匹配请求"


def test_create_match_request_rejects_missing_user(client):
    """POST /social/match-requests 不允许向不存在用户发送请求"""
    user_data = create_test_user(client, username="missingsocial")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/social/match-requests", json={"toUid": "missing-user-id"}, headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == 40202
    assert data["message"] == "用户不存在"


def test_social_full_flow_with_messages_and_match_report(client, monkeypatch):
    """社交完整链路：匹配、接受、发消息、查消息、查匹配报告"""
    monkeypatch.setattr(settings, "MINIMAX_MOCK", True)
    from app.ai import minimax_client as _mc

    monkeypatch.setattr(_mc, "_minimax_client", None)
    user1_data = create_test_user(client, username="socialflow1")
    user2_data = create_test_user(client, username="socialflow2")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])

    # 1. 发送匹配请求
    target_id = user2_data["user"]["id"]
    req_resp = client.post("/api/social/match-requests", json={"toUid": target_id}, headers=headers1)
    assert req_resp.status_code == 200
    request_data = req_resp.json()
    assert request_data["code"] == 0
    request_id = request_data["data"]["id"]

    # 2. 对方接受请求
    respond_resp = client.post(
        f"/api/social/match-requests/{request_id}/respond",
        json={"accept": True},
        headers=headers2,
    )
    assert respond_resp.status_code == 200
    assert respond_resp.json()["code"] == 0

    # 3. 发送消息
    send_resp = client.post(
        f"/api/social/messages/{request_id}",
        json={"content": "你好，我们可以一起自习吗？"},
        headers=headers1,
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["code"] == 0
    sent_message = send_data["data"]
    assert sent_message["matchId"] == request_id
    assert sent_message["fromUid"] == user1_data["user"]["id"]
    assert sent_message["content"] == "你好，我们可以一起自习吗？"

    # 4. 获取消息列表
    messages_resp = client.get(f"/api/social/messages/{request_id}", headers=headers2)
    assert messages_resp.status_code == 200
    messages_data = messages_resp.json()
    assert messages_data["code"] == 0
    assert isinstance(messages_data["data"], list)
    assert len(messages_data["data"]) == 1
    assert messages_data["data"][0]["id"] == sent_message["id"]
    assert messages_data["data"][0]["content"] == "你好，我们可以一起自习吗？"

    # 5. 获取匹配报告（Mock 模式）
    report_resp = client.get(f"/api/social/matches/{request_id}/report", headers=headers1)
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["code"] == 0
    report = report_data["data"]
    assert report["compatibility"] == 85
    assert isinstance(report["commonPoints"], list)
    assert isinstance(report["differences"], list)
    assert report["analysis"]


def test_match_report_prefers_avatar_card_context(client, db, monkeypatch):
    """生成匹配报告时，应把 avatar_card 一并带入画像上下文。"""
    from app.models.memory import AvatarCard
    from app.social import service as social_service
    import time
    from uuid import uuid4

    captured = {}

    class FakeMiniMaxClient:
        mock = False

        async def chat_completion(self, messages, system_prompt="", **kwargs):
            captured["prompt"] = messages[-1]["content"]
            captured["system"] = system_prompt
            return '{"compatibility":88,"analysis":"你们可以慢慢熟起来。","common_points":["都喜欢夜跑"],"differences":["社交节奏不同"]}'

    monkeypatch.setattr(social_service, "get_minimax_client", lambda: FakeMiniMaxClient())

    user1_data = create_test_user(client, username="socialcard1")
    user2_data = create_test_user(client, username="socialcard2")
    headers1 = get_auth_header(user1_data["token"])
    headers2 = get_auth_header(user2_data["token"])
    now = int(time.time() * 1000)

    db.add(
        AvatarCard(
            id=str(uuid4()),
            user_id=user1_data["user"]["id"],
            display_name="一号分身",
            public_summary="喜欢夜跑，也偏爱低压力社交。",
            interest_tags='["夜跑"]',
            social_intent='["认识一起运动的人"]',
            conversation_style='{"tone":"自然"}',
            boundaries='["不喜欢高压社交"]',
            visibility="private",
            updated_at=now,
        )
    )
    db.add(
        AvatarCard(
            id=str(uuid4()),
            user_id=user2_data["user"]["id"],
            display_name="二号分身",
            public_summary="最近在恢复跑步习惯。",
            interest_tags='["夜跑","散步"]',
            social_intent='["想认识新朋友"]',
            conversation_style='{"tone":"温和"}',
            boundaries='[]',
            visibility="private",
            updated_at=now,
        )
    )
    db.commit()

    req_resp = client.post(
        "/api/social/match-requests",
        json={"toUid": user2_data["user"]["id"]},
        headers=headers1,
    )
    request_id = req_resp.json()["data"]["id"]
    client.post(
        f"/api/social/match-requests/{request_id}/respond",
        json={"accept": True},
        headers=headers2,
    )

    report_resp = client.get(f"/api/social/matches/{request_id}/report", headers=headers1)
    assert report_resp.status_code == 200
    assert report_resp.json()["data"]["compatibility"] == 88

    prompt = captured["prompt"]
    assert prompt.count("avatar_card") == 2
    assert "一号分身" in prompt and "二号分身" in prompt
    assert "json" in captured["system"].lower()


class FakeAiClient:
    """mock=False，走真实的解析链路，返回预设的模型原始输出。"""

    mock = False

    def __init__(self, raw: str = "", error: Exception | None = None):
        self.raw = raw
        self.error = error
        self.calls = 0

    async def chat_completion(self, messages, system_prompt="", **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.raw


def _accept_match(client, prefix: str) -> tuple[str, dict]:
    """建一对已互相确认的 match，返回 (match_id, 发起方请求头)。"""
    user1 = create_test_user(client, username=f"{prefix}1")
    user2 = create_test_user(client, username=f"{prefix}2")
    headers1 = get_auth_header(user1["token"])
    headers2 = get_auth_header(user2["token"])
    match_id = client.post(
        "/api/social/match-requests",
        json={"toUid": user2["user"]["id"]},
        headers=headers1,
    ).json()["data"]["id"]
    client.post(
        f"/api/social/match-requests/{match_id}/respond",
        json={"accept": True},
        headers=headers2,
    )
    return match_id, headers1


def _payload_to_report(raw: str) -> dict:
    from app.social.service import _match_report_payload_from_raw, _normalize_match_report

    return _normalize_match_report(_match_report_payload_from_raw(raw))


@pytest.mark.parametrize(
    "raw, score, analysis",
    [
        (
            '{"compatibility":91,"analysis":"你们的作息和兴趣都很接近。",'
            '"common_points":["都爱夜跑"],"differences":["社交节奏不同"]}',
            91,
            "你们的作息和兴趣都很接近。",
        ),
        (
            '```json\n{"compatibility":88,"analysis":"很聊得来。",'
            '"common_points":["都爱看电影"],"differences":["口味不同"]}\n```',
            88,
            "很聊得来。",
        ),
        (
            "好的，下面是分析结果：\n"
            '{"compatibility":77,"analysis":"可以先约一次饭。",'
            '"common_points":["都爱美食"],"differences":["预算不同"]}\n'
            "希望对你有帮助！",
            77,
            "可以先约一次饭。",
        ),
    ],
    ids=["clean_json", "fenced_json", "json_with_prose"],
)
def test_match_report_parses_structured_output(raw, score, analysis):
    """干净 JSON、代码块包裹、前后带解释文字三种输出都要解析出真实分数和正文。"""
    report = _payload_to_report(raw)

    assert report["compatibility"] == score
    assert report["analysis"] == analysis
    assert report["common_points"] and report["differences"]


def test_match_report_includes_extended_dimensions():
    """新 schema：多维度分数 + 建议/风险/摘要都要落进规范化结果。"""
    raw = (
        '{"compatibility":88,"summary":"夜跑搭子很合适",'
        '"analysis":"你们节奏接近，适合先从运动熟悉起来。",'
        '"dimensions":{'
        '"interest_fit":{"score":92,"reason":"都爱夜跑"},'
        '"rhythm_fit":{"score":80,"reason":"都偏晚间"},'
        '"communication_style":{"score":84,"reason":"说话直接"},'
        '"values_fit":{"score":86,"reason":"重视个人空间"},'
        '"social_boundary":{"score":90,"reason":"偏小范围社交"},'
        '"short_term_goal":{"score":87,"reason":"都想找运动搭子"}'
        '},'
        '"common_points":["都爱夜跑","都偏安静","都愿先线下活动"],'
        '"differences":["社交密度不同","话题偏好略异"],'
        '"suggestions":["先约 40 分钟夜跑","跑后确认下次节奏"],'
        '"risks":["别一上来安排全天"]}'
    )
    report = _payload_to_report(raw)

    assert report["compatibility"] == 88
    assert report["summary"] == "夜跑搭子很合适"
    assert len(report["dimensions"]) == 6
    assert report["dimensions"][0]["key"] == "interest_fit"
    assert report["dimensions"][0]["label"] == "兴趣契合"
    assert report["dimensions"][0]["score"] == 92
    assert len(report["common_points"]) >= 3
    assert len(report["differences"]) >= 2
    assert report["suggestions"]
    assert report["risks"] == ["别一上来安排全天"]


def test_match_report_parses_sloppy_json():
    """中文引号 + 全角标点 + 尾随逗号的近似 JSON 也要修好，不抛异常。"""
    raw = (
        "{“compatibility”：82，“analysis”：“你们都喜欢安静的相处方式。”，"
        "“common_points”：[“都爱读书”，“都爱夜跑”]，“differences”：[“作息不同”，]}"
    )
    report = _payload_to_report(raw)

    assert report["compatibility"] == 82
    assert report["analysis"] == "你们都喜欢安静的相处方式。"
    assert report["common_points"] == ["都爱读书", "都爱夜跑"]


def test_match_report_parses_single_quoted_json():
    raw = "{'compatibility': 79, 'analysis': '你们节奏很像。', 'common_points': ['都爱咖啡'], 'differences': ['话题偏好不同'],}"
    report = _payload_to_report(raw)

    assert report["compatibility"] == 79
    assert report["analysis"] == "你们节奏很像。"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("【匹配度：90%】\n你们都喜欢夜跑，共同话题很多。", 90),
        ("你俩的匹配度 90 分，建议先约一次跑步。", 90),
        ("综合来看契合度为83%，可以慢慢熟起来。", 83),
    ],
    ids=["percent_in_brackets", "score_in_points", "compatibility_prefix"],
)
def test_match_report_extracts_score_from_prose(raw, expected):
    """模型只给自然语言时，分数从正文抽取，而不是直接回落兜底值。"""
    report = _payload_to_report(raw)

    assert report["compatibility"] == expected
    assert report["compatibility"] != 75
    assert report["analysis"].startswith(raw.split("\n")[0][:4])


def test_match_report_prose_without_score_falls_back():
    """正文里也没有任何分数时才允许回落兜底值，同时保住可读正文。"""
    raw = "你们都很有意思，聊起来应该会很轻松，建议先从共同的爱好开始。"
    report = _payload_to_report(raw)

    assert report["compatibility"] == 75
    assert report["analysis"] == raw


def test_match_report_keeps_full_prose_instead_of_truncating():
    """旧实现把正文截断成 200 字；现在要保住完整可读正文。"""
    raw = "匹配度80%。" + "你们都喜欢在夜里跑步整理心情。" * 20
    report = _payload_to_report(raw)

    assert report["compatibility"] == 80
    assert len(report["analysis"]) > 200


@pytest.mark.parametrize("raw_score", ["0.9", "90"])
def test_match_report_normalizes_score_scale_from_model_output(raw_score):
    """模型给 0.9 或 90 都要落到 90。"""
    raw = f'{{"compatibility":{raw_score},"analysis":"很合适。","common_points":["都爱读书"],"differences":["作息不同"]}}'

    assert _payload_to_report(raw)["compatibility"] == 90


def test_match_report_falls_back_when_ai_unavailable(client, monkeypatch, caplog):
    """模型超时/报错时返回合法报告 + 兜底分，并且日志能看出是哪一层失败。"""
    import logging

    from app.social import service as social_service

    monkeypatch.setattr(
        social_service,
        "get_minimax_client",
        lambda: FakeAiClient(error=TimeoutError("vivo timeout")),
    )
    match_id, headers = _accept_match(client, "aifail")

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        resp = client.get(f"/api/social/matches/{match_id}/report", headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["compatibility"] == 75
    assert data["analysis"]
    assert data["commonPoints"] and data["differences"]
    messages = [record.getMessage() for record in caplog.records]
    assert any("匹配报告生成失败" in message for message in messages)


def test_match_report_prose_score_reaches_api(client, monkeypatch):
    """端到端：模型只给自然语言时，接口返回的分数也应该是正文里的真实分数。"""
    from app.social import service as social_service

    monkeypatch.setattr(
        social_service,
        "get_minimax_client",
        lambda: FakeAiClient(raw="【匹配度：90%】你们都喜欢夜跑，很容易聊到一起。"),
    )
    match_id, headers = _accept_match(client, "prosescore")

    resp = client.get(f"/api/social/matches/{match_id}/report", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["compatibility"] == 90


def test_refresh_match_report_keeps_buddy_reason(client, db, monkeypatch):
    """反复重新生成报告都不能覆盖搭子申请理由。"""
    import asyncio

    from app.models.social import Match
    from app.social import service as social_service

    monkeypatch.setattr(
        social_service,
        "get_minimax_client",
        lambda: FakeAiClient(
            raw='{"compatibility":93,"analysis":"你们都爱科幻。","common_points":["都爱电影"],"differences":["口味不同"]}'
        ),
    )
    applicant = create_test_user(client, username="refreshreason1")
    receiver = create_test_user(client, username="refreshreason2")
    match_id = client.post(
        "/api/social/buddy",
        json={"target_user_id": receiver["user"]["id"], "reason": "周末一起看科幻电影"},
        headers=get_auth_header(applicant["token"]),
    ).json()["data"]["id"]

    resp = client.get(
        f"/api/social/matches/{match_id}/report",
        headers=get_auth_header(applicant["token"]),
    )
    assert resp.json()["data"]["compatibility"] == 93

    db.expire_all()
    match = db.query(Match).filter(Match.id == match_id).first()
    assert json.loads(match.match_report)["reason"] == "周末一起看科幻电影"

    asyncio.run(social_service.refresh_match_report(db, match))
    db.expire_all()
    stored = json.loads(db.query(Match).filter(Match.id == match_id).first().match_report)
    assert stored["reason"] == "周末一起看科幻电影"
    assert stored["compatibility"] == 93

    matches = client.get(
        "/api/social/matches?include_pending=true",
        headers=get_auth_header(applicant["token"]),
    ).json()["data"]
    entry = next(item for item in matches if item["id"] == match_id)
    assert entry["reason"] == "周末一起看科幻电影"


def _load_regenerate_script():
    import importlib.util
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "regenerate_match_reports.py",
    )
    spec = importlib.util.spec_from_file_location("regenerate_match_reports", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_regenerate_script_dry_run_does_not_write(client, db, monkeypatch):
    """脚本 dry-run 不写库；加 --apply 才刷新，且刷新后不会被再次选中。"""
    import asyncio

    from app.models.social import Match
    from app.social import service as social_service
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(
        social_service,
        "get_minimax_client",
        lambda: FakeAiClient(
            raw='{"compatibility":92,"analysis":"你们都爱夜跑。","common_points":["都爱夜跑"],"differences":["作息不同"]}'
        ),
    )
    module = _load_regenerate_script()
    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    match_id, _ = _accept_match(client, "regen")
    match = db.query(Match).filter(Match.id == match_id).first()
    match.match_report = json.dumps(
        {
            "compatibility": 75,
            "analysis": "匹配度较高，有共同语言。",
            "common_points": ["有共同兴趣"],
            "differences": ["性格略有差异"],
            "reason": "一起去看展",
        },
        ensure_ascii=False,
    )
    db.commit()

    assert asyncio.run(module.run([match_id], False, False, 0, 0)) == 0
    db.expire_all()
    stored = json.loads(db.query(Match).filter(Match.id == match_id).first().match_report)
    assert stored["compatibility"] == 75

    assert asyncio.run(module.run([match_id], True, False, 0, 0)) == 0
    db.expire_all()
    stored = json.loads(db.query(Match).filter(Match.id == match_id).first().match_report)
    assert stored["compatibility"] == 92
    assert stored["reason"] == "一起去看展"

    selected, _ = module._select(db, [match_id], False, 0)
    assert selected == []

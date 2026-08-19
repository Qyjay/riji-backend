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

        async def generate_match_report(self, portrait_a, portrait_b):
            captured["a"] = portrait_a
            captured["b"] = portrait_b
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
    assert "avatar_card" in captured["a"]
    assert "avatar_card" in captured["b"]
    assert captured["a"]["avatar_card"]["interest_tags"] == ["夜跑"]

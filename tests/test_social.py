"""
社交模块测试
"""
import pytest
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

"""
AI 分身模块测试
覆盖：记忆 CRUD → 状态获取/更新 → 推荐列表/操作 → 侧写获取/生成
"""
import json
import pytest
from tests.conftest import create_test_user, get_auth_header


# ==================== 记忆 CRUD ====================

def test_add_memory(client):
    """POST /avatar/memories 添加记忆"""
    user_data = create_test_user(client, username="avatar_mem_add")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/avatar/memories", json={
        "category": "interest",
        "content": "喜欢周末晨跑和拍照",
    }, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    mem = data["data"]

    assert mem["id"]
    assert mem["category"] == "interest"
    assert mem["content"] == "喜欢周末晨跑和拍照"
    assert mem["source"] == "manual"
    assert mem["confidence"] == 1.0
    assert mem["isActive"] is True
    assert mem["isPinned"] is False
    assert mem["createdAt"] > 0
    assert mem["updatedAt"] > 0


def test_list_memories(client):
    """GET /avatar/memories 记忆列表"""
    user_data = create_test_user(client, username="avatar_mem_list")
    headers = get_auth_header(user_data["token"])

    client.post("/api/avatar/memories", json={"category": "fact", "content": "事实1"}, headers=headers)
    client.post("/api/avatar/memories", json={"category": "interest", "content": "兴趣1"}, headers=headers)

    resp = client.get("/api/avatar/memories", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert isinstance(items, list)
    assert len(items) == 2


def test_list_memories_filter_category(client):
    """GET /avatar/memories?category=fact 按类别筛选"""
    user_data = create_test_user(client, username="avatar_mem_filter")
    headers = get_auth_header(user_data["token"])

    client.post("/api/avatar/memories", json={"category": "fact", "content": "事实1"}, headers=headers)
    client.post("/api/avatar/memories", json={"category": "interest", "content": "兴趣1"}, headers=headers)
    client.post("/api/avatar/memories", json={"category": "fact", "content": "事实2"}, headers=headers)

    resp = client.get("/api/avatar/memories?category=fact", headers=headers)
    items = resp.json()["data"]
    assert len(items) == 2
    assert all(item["category"] == "fact" for item in items)


def test_update_memory(client):
    """PUT /avatar/memories/{id} 更新记忆"""
    user_data = create_test_user(client, username="avatar_mem_upd")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/avatar/memories", json={
        "category": "interest",
        "content": "原始内容",
    }, headers=headers)
    memory_id = create_resp.json()["data"]["id"]
    old_updated_at = create_resp.json()["data"]["updatedAt"]

    resp = client.put(f"/api/avatar/memories/{memory_id}", json={
        "content": "更新后的内容",
        "is_pinned": True,
        "tags": ["运动", "社交"],
    }, headers=headers)

    assert resp.status_code == 200
    mem = resp.json()["data"]
    assert mem["content"] == "更新后的内容"
    assert mem["isPinned"] is True
    assert mem["tags"] == ["运动", "社交"]
    assert mem["updatedAt"] >= old_updated_at


def test_update_memory_partial(client):
    """部分更新：只传 is_active，其他字段不变"""
    user_data = create_test_user(client, username="avatar_mem_partial")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/avatar/memories", json={
        "category": "personality",
        "content": "外向开朗",
    }, headers=headers)
    memory_id = create_resp.json()["data"]["id"]

    resp = client.put(f"/api/avatar/memories/{memory_id}", json={
        "is_active": False,
    }, headers=headers)

    mem = resp.json()["data"]
    assert mem["isActive"] is False
    assert mem["content"] == "外向开朗"
    assert mem["category"] == "personality"


def test_delete_memory(client):
    """DELETE /avatar/memories/{id} 删除记忆"""
    user_data = create_test_user(client, username="avatar_mem_del")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/avatar/memories", json={
        "category": "habit",
        "content": "待删除的记忆",
    }, headers=headers)
    memory_id = create_resp.json()["data"]["id"]

    resp = client.delete(f"/api/avatar/memories/{memory_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] is None

    # 确认已删除
    list_resp = client.get("/api/avatar/memories", headers=headers)
    assert len(list_resp.json()["data"]) == 0


def test_delete_memory_not_found(client):
    """删除不存在的记忆返回 404"""
    user_data = create_test_user(client, username="avatar_mem_del404")
    headers = get_auth_header(user_data["token"])

    resp = client.delete("/api/avatar/memories/nonexistent-id", headers=headers)
    assert resp.status_code == 404


def test_update_memory_not_found(client):
    """更新不存在的记忆返回 404"""
    user_data = create_test_user(client, username="avatar_mem_upd404")
    headers = get_auth_header(user_data["token"])

    resp = client.put("/api/avatar/memories/nonexistent-id", json={
        "content": "不存在",
    }, headers=headers)
    assert resp.status_code == 404


# ==================== 分身状态 ====================

def test_get_status_auto_create(client):
    """GET /avatar/status 首次访问自动创建默认记录"""
    user_data = create_test_user(client, username="avatar_status_auto")
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/avatar/status", headers=headers)
    assert resp.status_code == 200
    status = resp.json()["data"]

    assert status["isActive"] is True
    assert status["browsedCount"] == 0
    assert status["matchedCount"] == 0
    assert status["chattingCount"] == 0
    assert isinstance(status["enabledChannels"], list)
    assert isinstance(status["enabledActions"], list)
    assert isinstance(status["matchRange"], dict)


def test_update_status(client):
    """PUT /avatar/status 更新分身状态"""
    user_data = create_test_user(client, username="avatar_status_upd")
    headers = get_auth_header(user_data["token"])

    # 先触发自动创建
    client.get("/api/avatar/status", headers=headers)

    resp = client.put("/api/avatar/status", json={
        "is_active": False,
        "enabled_channels": ["buddy", "share"],
        "enabled_actions": ["browse"],
        "match_range": {"school": "北京大学", "distanceKm": 5},
    }, headers=headers)

    assert resp.status_code == 200
    status = resp.json()["data"]
    assert status["isActive"] is False
    assert status["enabledChannels"] == ["buddy", "share"]
    assert status["enabledActions"] == ["browse"]
    assert status["matchRange"]["school"] == "北京大学"
    assert status["matchRange"]["distanceKm"] == 5


def test_update_status_partial(client):
    """部分更新：只改 is_active，其他不变"""
    user_data = create_test_user(client, username="avt_stat_partial")
    headers = get_auth_header(user_data["token"])

    client.get("/api/avatar/status", headers=headers)

    resp = client.put("/api/avatar/status", json={
        "is_active": False,
    }, headers=headers)

    status = resp.json()["data"]
    assert status["isActive"] is False
    # 其他字段保持默认
    assert len(status["enabledChannels"]) == 4
    assert len(status["enabledActions"]) == 3


def test_status_persistence(client):
    """更新后再次获取，确认持久化"""
    user_data = create_test_user(client, username="avt_stat_persist")
    headers = get_auth_header(user_data["token"])

    client.get("/api/avatar/status", headers=headers)
    client.put("/api/avatar/status", json={
        "enabled_channels": ["dating"],
    }, headers=headers)

    resp = client.get("/api/avatar/status", headers=headers)
    assert resp.json()["data"]["enabledChannels"] == ["dating"]


# ==================== 分身推荐 ====================

def test_list_matches_empty(client):
    """GET /avatar/matches 无推荐时返回空数组"""
    user_data = create_test_user(client, username="avatar_match_empty")
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/avatar/matches", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_match_action_not_found(client):
    """操作不存在的匹配返回 404"""
    user_data = create_test_user(client, username="avatar_match_404")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/avatar/matches/nonexistent-id/action", json={
        "action": "dismiss",
    }, headers=headers)
    assert resp.status_code == 404


def test_match_action_invalid(client):
    """无效 action 返回错误"""
    user_data = create_test_user(client, username="avatar_match_invalid")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/avatar/matches/some-id/action", json={
        "action": "invalid_action",
    }, headers=headers)
    assert resp.status_code == 400


def test_match_action_with_seeded_data(client, db):
    """用种子数据测试 dismiss/chat 操作"""
    from app.models.plaza import PlazaPost
    from app.models.avatar import AvatarMatch
    import time
    from uuid import uuid4

    user_data = create_test_user(client, username="avatar_match_seed")
    headers = get_auth_header(user_data["token"])
    user_id = user_data["user"]["id"]
    now = int(time.time() * 1000)

    # 手动插入帖子和匹配
    post = PlazaPost(
        id=str(uuid4()), user_id=user_id, type="buddy",
        content="测试帖子", created_at=now,
    )
    db.add(post)
    db.commit()

    match = AvatarMatch(
        id=str(uuid4()), user_id=user_id, post_id=post.id,
        match_score=85, match_reasons=json.dumps(["兴趣相同"]),
        agent_conversation=json.dumps([]),
        status="new", created_at=now,
    )
    db.add(match)
    db.commit()

    # 列表中应有 1 条
    list_resp = client.get("/api/avatar/matches", headers=headers)
    items = list_resp.json()["data"]
    assert len(items) == 1
    assert items[0]["matchScore"] == 85
    assert items[0]["post"]["id"] == post.id

    # dismiss 操作
    action_resp = client.post(f"/api/avatar/matches/{match.id}/action", json={
        "action": "dismiss",
    }, headers=headers)
    assert action_resp.status_code == 200

    # dismissed 后列表为空
    list_resp2 = client.get("/api/avatar/matches", headers=headers)
    assert list_resp2.json()["data"] == []


# ==================== 分身侧写 ====================

def test_get_profile_empty(client):
    """GET /avatar/profile 无侧写时返回默认空侧写"""
    user_data = create_test_user(client, username="avatar_profile_empty")
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/avatar/profile", headers=headers)
    assert resp.status_code == 200
    profile = resp.json()["data"]
    assert profile["summary"] == ""
    assert profile["diaryCount"] == 0
    assert profile["chatCount"] == 0
    assert profile["generatedAt"] == 0


def test_regenerate_profile(client, monkeypatch):
    """POST /avatar/profile/regenerate 使用 Mock AI 生成侧写"""
    from app.ai import minimax_client

    class FakeMiniMaxClient:
        async def chat_completion(self, messages, system_prompt="", temperature=0.8, max_tokens=2048):
            return "这是一个热爱生活、喜欢交朋友的大学生，平时喜欢晨跑和阅读。"

    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

    user_data = create_test_user(client, username="avatar_profile_regen")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/avatar/profile/regenerate", headers=headers)
    assert resp.status_code == 200
    profile = resp.json()["data"]
    assert profile["summary"] == "这是一个热爱生活、喜欢交朋友的大学生，平时喜欢晨跑和阅读。"
    assert profile["generatedAt"] > 0

    # 再次获取，确认持久化
    get_resp = client.get("/api/avatar/profile", headers=headers)
    assert get_resp.json()["data"]["summary"] == profile["summary"]


def test_regenerate_profile_with_memories(client, monkeypatch):
    """侧写生成时会收集用户记忆"""
    from app.ai import minimax_client

    received_prompts = []

    class FakeMiniMaxClient:
        async def chat_completion(self, messages, system_prompt="", temperature=0.8, max_tokens=2048):
            received_prompts.append(messages[0]["content"])
            return "基于记忆生成的侧写"

    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

    user_data = create_test_user(client, username="avt_prof_withmem")
    headers = get_auth_header(user_data["token"])

    # 先添加记忆
    client.post("/api/avatar/memories", json={
        "category": "interest",
        "content": "喜欢打羽毛球",
    }, headers=headers)

    resp = client.post("/api/avatar/profile/regenerate", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["summary"] == "基于记忆生成的侧写"

    # 确认 AI 收到了记忆内容
    assert len(received_prompts) == 1
    assert "喜欢打羽毛球" in received_prompts[0]


# ==================== 鉴权 ====================

def test_avatar_no_auth(client):
    """无 token 访问分身接口返回 401"""
    resp = client.get("/api/avatar/memories")
    assert resp.status_code == 401 or resp.json().get("code", 0) != 0

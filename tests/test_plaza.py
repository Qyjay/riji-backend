"""
广场模块测试
覆盖：创建帖子 → 列表浏览 → 频道筛选 → 帖子详情 → 点赞/取消 → 评论 → school_only
"""
import pytest
from tests.conftest import create_test_user, get_auth_header


# ==================== 创建帖子 ====================

def test_create_post(client):
    """POST /plaza/posts 创建帖子"""
    user_data = create_test_user(client, username="plaza_create")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/plaza/posts", json={
        "type": "buddy",
        "content": "有没有人一起去图书馆自习？",
        "images": ["/uploads/mock/img1.jpg"],
        "location": "图书馆",
        "tags": ["自习", "搭子"],
        "allow_agent_reply": True,
        "school_only": False,
    }, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    post = data["data"]

    assert post["id"]
    assert post["authorId"] == user_data["user"]["id"]
    assert post["authorName"] == "测试用户"
    assert post["type"] == "buddy"
    assert post["content"] == "有没有人一起去图书馆自习？"
    assert post["images"] == ["/uploads/mock/img1.jpg"]
    assert post["location"] == "图书馆"
    assert post["tags"] == ["自习", "搭子"]
    assert post["likes"] == 0
    assert post["comments"] == 0
    assert post["agentResponses"] == 0
    assert post["isFromAgent"] is False
    assert post["allowAgentReply"] is True
    assert post["schoolOnly"] is False
    assert post["createdAt"] > 0


# ==================== 帖子列表 ====================

def test_list_posts_empty(client):
    """GET /plaza/posts 无帖子时返回空列表"""
    user_data = create_test_user(client, username="plaza_empty")
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/plaza/posts", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


def test_list_posts_pagination(client):
    """GET /plaza/posts 分页功能"""
    user_data = create_test_user(client, username="plaza_page")
    headers = get_auth_header(user_data["token"])

    for i in range(5):
        client.post("/api/plaza/posts", json={
            "type": "share",
            "content": f"帖子 {i}",
        }, headers=headers)

    resp = client.get("/api/plaza/posts?page=1&page_size=2", headers=headers)
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2

    resp2 = client.get("/api/plaza/posts?page=3&page_size=2", headers=headers)
    data2 = resp2.json()["data"]
    assert len(data2["items"]) == 1


def test_list_posts_channel_filter(client):
    """GET /plaza/posts?channel=buddy 频道筛选"""
    user_data = create_test_user(client, username="plaza_channel")
    headers = get_auth_header(user_data["token"])

    client.post("/api/plaza/posts", json={"type": "buddy", "content": "找搭子"}, headers=headers)
    client.post("/api/plaza/posts", json={"type": "help", "content": "求助"}, headers=headers)
    client.post("/api/plaza/posts", json={"type": "buddy", "content": "找搭子2"}, headers=headers)

    resp = client.get("/api/plaza/posts?channel=buddy", headers=headers)
    data = resp.json()["data"]
    assert data["total"] == 2
    assert all(item["type"] == "buddy" for item in data["items"])

    resp_all = client.get("/api/plaza/posts", headers=headers)
    assert resp_all.json()["data"]["total"] == 3


def test_list_posts_order_desc(client):
    """帖子列表按 createdAt 降序排列"""
    user_data = create_test_user(client, username="plaza_order")
    headers = get_auth_header(user_data["token"])

    client.post("/api/plaza/posts", json={"type": "share", "content": "第一条"}, headers=headers)
    client.post("/api/plaza/posts", json={"type": "share", "content": "第二条"}, headers=headers)

    resp = client.get("/api/plaza/posts", headers=headers)
    items = resp.json()["data"]["items"]
    assert items[0]["createdAt"] >= items[1]["createdAt"]


# ==================== 帖子详情 ====================

def test_get_post_detail(client):
    """GET /plaza/posts/{id} 帖子详情"""
    user_data = create_test_user(client, username="plaza_detail")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "dating",
        "content": "恋爱帖子",
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/plaza/posts/{post_id}", headers=headers)
    assert resp.status_code == 200
    post = resp.json()["data"]
    assert post["id"] == post_id
    assert post["content"] == "恋爱帖子"
    assert post["authorSchool"] == "南开大学"
    assert post["authorMajor"] == "软件工程"


def test_get_post_not_found(client):
    """GET /plaza/posts/{id} 不存在的帖子返回 404"""
    user_data = create_test_user(client, username="plaza_404")
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/plaza/posts/nonexistent-id", headers=headers)
    assert resp.status_code == 404


# ==================== 点赞 ====================

def test_like_toggle(client):
    """POST /plaza/posts/{id}/like 点赞/取消点赞 Toggle"""
    user_data = create_test_user(client, username="plaza_like")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "share",
        "content": "点赞测试",
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    # 第一次：点赞
    resp1 = client.post(f"/api/plaza/posts/{post_id}/like", headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["data"] is None

    detail1 = client.get(f"/api/plaza/posts/{post_id}", headers=headers).json()["data"]
    assert detail1["likes"] == 1

    # 第二次：取消点赞
    resp2 = client.post(f"/api/plaza/posts/{post_id}/like", headers=headers)
    assert resp2.status_code == 200

    detail2 = client.get(f"/api/plaza/posts/{post_id}", headers=headers).json()["data"]
    assert detail2["likes"] == 0


def test_like_nonexistent_post(client):
    """点赞不存在的帖子返回 404"""
    user_data = create_test_user(client, username="plaza_like404")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/plaza/posts/nonexistent-id/like", headers=headers)
    assert resp.status_code == 404


# ==================== 评论 ====================

def test_add_comment(client):
    """POST /plaza/posts/{id}/comments 添加评论"""
    user_data = create_test_user(client, username="plaza_comment")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "help",
        "content": "评论测试帖",
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    resp = client.post(f"/api/plaza/posts/{post_id}/comments", json={
        "content": "我来帮你！",
        "is_agent": False,
    }, headers=headers)

    assert resp.status_code == 200
    comment = resp.json()["data"]
    assert comment["postId"] == post_id
    assert comment["authorId"] == user_data["user"]["id"]
    assert comment["authorName"] == "测试用户"
    assert comment["content"] == "我来帮你！"
    assert comment["isAgent"] is False

    # 帖子评论数 +1
    detail = client.get(f"/api/plaza/posts/{post_id}", headers=headers).json()["data"]
    assert detail["comments"] == 1


def test_add_agent_comment(client):
    """分身评论显示为「XXX的分身」"""
    user_data = create_test_user(client, username="plaza_agent_cmt")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "buddy",
        "content": "分身评论测试",
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    resp = client.post(f"/api/plaza/posts/{post_id}/comments", json={
        "content": "你的分身觉得这很有趣",
        "is_agent": True,
    }, headers=headers)

    comment = resp.json()["data"]
    assert comment["isAgent"] is True
    assert comment["authorName"] == "测试用户的分身"

    # 帖子 agentResponses +1
    detail = client.get(f"/api/plaza/posts/{post_id}", headers=headers).json()["data"]
    assert detail["agentResponses"] == 1
    assert detail["comments"] == 1


def test_list_comments(client):
    """GET /plaza/posts/{id}/comments 评论列表，按时间正序"""
    user_data = create_test_user(client, username="plaza_cmtlist")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "share",
        "content": "评论列表测试",
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    client.post(f"/api/plaza/posts/{post_id}/comments", json={"content": "第一条"}, headers=headers)
    client.post(f"/api/plaza/posts/{post_id}/comments", json={"content": "第二条"}, headers=headers)

    resp = client.get(f"/api/plaza/posts/{post_id}/comments", headers=headers)
    assert resp.status_code == 200
    comments = resp.json()["data"]
    assert isinstance(comments, list)
    assert len(comments) == 2
    assert comments[0]["content"] == "第一条"
    assert comments[1]["content"] == "第二条"
    # 时间正序
    assert comments[0]["createdAt"] <= comments[1]["createdAt"]


def test_list_comments_empty(client):
    """无评论时返回空数组"""
    user_data = create_test_user(client, username="plaza_cmtempty")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "share",
        "content": "无评论帖",
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/plaza/posts/{post_id}/comments", headers=headers)
    assert resp.json()["data"] == []


# ==================== school_only 逻辑 ====================

def test_school_only_same_school_visible(client):
    """school_only 帖子对同校用户可见"""
    user_data = create_test_user(client, username="plaza_school1", school="北京大学")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "share",
        "content": "仅北大可见",
        "school_only": True,
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    # 同校用户可见
    user2_data = create_test_user(client, username="plaza_school2", school="北京大学")
    headers2 = get_auth_header(user2_data["token"])

    resp = client.get("/api/plaza/posts", headers=headers2)
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert post_id in ids


def test_school_only_different_school_hidden(client):
    """school_only 帖子对不同校用户不可见"""
    user_data = create_test_user(client, username="plaza_school3", school="北京大学")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "share",
        "content": "仅北大可见",
        "school_only": True,
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    # 不同校用户不可见
    user3_data = create_test_user(client, username="plaza_school4", school="清华大学")
    headers3 = get_auth_header(user3_data["token"])

    resp = client.get("/api/plaza/posts", headers=headers3)
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert post_id not in ids


def test_school_only_detail_hidden_for_other_school(client):
    """school_only 帖子详情对不同校用户返回 404"""
    user_data = create_test_user(client, username="plaza_school5", school="北京大学")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "share",
        "content": "仅北大可见",
        "school_only": True,
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    user3_data = create_test_user(client, username="plaza_school6", school="清华大学")
    headers3 = get_auth_header(user3_data["token"])

    resp = client.get(f"/api/plaza/posts/{post_id}", headers=headers3)
    assert resp.status_code == 404


def test_non_school_only_visible_to_all(client):
    """非 school_only 帖子对所有人可见"""
    user_data = create_test_user(client, username="plaza_school7", school="北京大学")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/plaza/posts", json={
        "type": "share",
        "content": "所有人可见",
        "school_only": False,
    }, headers=headers)
    post_id = create_resp.json()["data"]["id"]

    user3_data = create_test_user(client, username="plaza_school8", school="清华大学")
    headers3 = get_auth_header(user3_data["token"])

    resp = client.get("/api/plaza/posts", headers=headers3)
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert post_id in ids


# ==================== 鉴权 ====================

def test_plaza_no_auth(client):
    """无 token 访问广场接口返回 401"""
    resp = client.get("/api/plaza/posts")
    assert resp.status_code == 401 or resp.json().get("code", 0) != 0

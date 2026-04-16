"""
日记模块测试
"""
from app.diary.service import DIARY_MAX_EDITS
from tests.conftest import create_test_user, get_auth_header


def _create_material(client, headers, content="测试素材", date="2026-03-25"):
    resp = client.post("/api/materials", json={
        "type": "text",
        "content": content,
        "date": date,
    }, headers=headers)
    return resp.json()["data"]


def test_generate_diary(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    _create_material(client, headers, "今天上课很有意思", "2026-03-25")

    resp = client.post("/api/diaries/generate", json={
        "date": "2026-03-25",
        "weather": "☀️ 晴",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    d = data["data"]
    # 验证 camelCase 字段
    assert "userId" in d
    assert "editCount" in d
    assert "maxEdits" in d
    assert "emotionSummary" in d
    assert "materialIds" in d
    assert "createdAt" in d
    assert d["status"] == "draft"
    assert d["editCount"] == 0
    assert d["maxEdits"] == DIARY_MAX_EDITS


def test_list_diaries_pagination(client):
    """GET /diaries?page=&page_size= 返回 {items, total}"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    _create_material(client, headers, "素材1", "2026-03-25")
    client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)

    resp = client.get("/api/diaries?page=1&page_size=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "items" in data["data"]
    assert "total" in data["data"]
    assert isinstance(data["data"]["items"], list)


def test_get_diary_detail(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    _create_material(client, headers, "详情测试素材", "2026-03-25")
    gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
    diary_id = gen_resp.json()["data"]["id"]

    resp = client.get(f"/api/diaries/{diary_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == diary_id


def test_update_diary_increments_edit_count(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    _create_material(client, headers, "素材", "2026-03-25")
    gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
    diary_id = gen_resp.json()["data"]["id"]

    resp = client.put(f"/api/diaries/{diary_id}", json={"content": "修改后的内容"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["editCount"] == 1


def test_update_diary_exceeds_max_edits(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    _create_material(client, headers, "素材", "2026-03-25")
    gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
    diary_id = gen_resp.json()["data"]["id"]

    # 修改 max_edits 次
    for i in range(DIARY_MAX_EDITS):
        resp = client.put(
            f"/api/diaries/{diary_id}",
            json={"content": f"修改 {i+1}"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    # 第 4 次应失败
    resp = client.put(f"/api/diaries/{diary_id}", json={"content": "第四次修改"}, headers=headers)
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 40102
    assert "上限" in body["message"]


def test_today_summary_before_diary(client):
    """today-summary 路由在 /{id} 之前，不会被错误匹配"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/diaries/today-summary?date=2026-03-25", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    d = data["data"]
    assert "date" in d
    assert "materialCount" in d or "material_count" in d
    assert "hasDiary" in d or "has_diary" in d
    assert "greetingUserName" in d or "greeting_user_name" in d
    assert "diaryCount" in d or "diary_count" in d
    assert "dominantEmotion" in d or "dominant_emotion" in d


def test_today_summary_includes_dynamic_greeting_fields(client):
    user_data = create_test_user(client, username="diary_summary_user")
    headers = get_auth_header(user_data["token"])

    # name 为空时会回退到 username，dominant_emotion 会从素材情绪聚合
    client.post(
        "/api/materials",
        json={
            "type": "text",
            "content": "今天完成了不少任务",
            "date": "2026-03-25",
            "emotion": {"label": "开心", "score": 0.9, "emoji": "😊"},
        },
        headers=headers,
    )

    resp = client.get("/api/diaries/today-summary?date=2026-03-25", headers=headers)
    assert resp.status_code == 200
    d = resp.json()["data"]

    greeting_name = d.get("greeting_user_name") or d.get("greetingUserName")
    diary_count = d.get("diary_count") if "diary_count" in d else d.get("diaryCount")
    dominant_emotion = d.get("dominant_emotion") if "dominant_emotion" in d else d.get("dominantEmotion")

    assert isinstance(greeting_name, str) and greeting_name
    assert diary_count == 0
    assert dominant_emotion == "开心"


def test_generate_derivative(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    _create_material(client, headers, "素材", "2026-03-25")
    gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
    diary_id = gen_resp.json()["data"]["id"]

    resp = client.post(f"/api/diaries/{diary_id}/derivative", json={"type": "novel"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    d = data["data"]
    assert "diaryId" in d
    assert "shareScope" in d
    assert "createdAt" in d


def test_list_derivatives_bare_array(client):
    """GET /derivatives?diary_id= 返回裸数组"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    _create_material(client, headers, "素材", "2026-03-25")
    gen_resp = client.post("/api/diaries/generate", json={"date": "2026-03-25"}, headers=headers)
    diary_id = gen_resp.json()["data"]["id"]

    client.post(f"/api/diaries/{diary_id}/derivative", json={"type": "novel"}, headers=headers)

    resp = client.get(f"/api/derivatives?diary_id={diary_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)

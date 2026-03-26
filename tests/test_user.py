"""
用户模块测试
"""
import pytest
from tests.conftest import create_test_user, get_auth_header


def test_get_profile(client):
    user_data = create_test_user(client, name="张三", school="清华大学")
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/user/profile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    profile = data["data"]
    # 验证 camelCase
    assert "diaryCount" in profile
    assert "streakDays" in profile
    assert "pomodoroCount" in profile
    assert profile["school"] == "清华大学"


def test_update_profile(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/user/profile", json={
        "name": "新名字",
        "style_tags": ["文艺", "治愈"],
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    profile = data["data"]
    assert profile["name"] == "新名字"
    # styleTags 应该是 camelCase
    assert "styleTags" in profile
    assert profile["styleTags"] == ["文艺", "治愈"]


def test_get_settings(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/user/settings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    settings = data["data"]
    # 验证 autoBGM（大写 BGM）
    assert "autoBGM" in settings
    assert "theme" in settings
    assert "diaryPrivacy" in settings


def test_update_settings(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/user/settings", json={
        "theme": "dark",
        "auto_bgm": True,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    settings = data["data"]
    assert settings["theme"] == "dark"
    assert settings["autoBGM"] == True


def test_get_achievements_bare_array(client):
    """GET /user/achievements 返回裸数组"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/user/achievements", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"], list)
    if data["data"]:
        ach = data["data"][0]
        assert "title" in ach
        assert "unlocked" in ach


def test_growth_data(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/user/growth", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    growth = data["data"]
    assert "diaries" in growth
    assert "emotions" in growth
    assert "tags" in growth
    assert "pomodoros" in growth
    assert "streak" in growth


def test_semester_report(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.get("/api/user/semester-report", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    report = data["data"]
    assert "totalDiaries" in report
    assert "totalPomodoros" in report
    assert "streak" in report

"""
认证模块测试
"""
import pytest


def test_register_success(client):
    resp = client.post("/api/auth/register", json={
        "username": "testuser1",
        "password": "test123",
        "name": "测试用户",
        "school": "南开大学",
        "major": "软件工程",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "token" in data["data"]
    assert data["data"]["user"]["username"] == "testuser1"
    # 验证 camelCase
    assert "name" in data["data"]["user"]
    assert "school" in data["data"]["user"]


def test_register_duplicate_username(client):
    client.post("/api/auth/register", json={"username": "dupeuser", "password": "test123"})
    resp = client.post("/api/auth/register", json={"username": "dupeuser", "password": "test123"})
    assert resp.status_code in [200, 400]
    if resp.status_code == 200:
        assert resp.json()["code"] != 0
    else:
        assert resp.json()["code"] != 0


def test_register_username_too_short(client):
    resp = client.post("/api/auth/register", json={"username": "ab", "password": "test123"})
    # Pydantic validation error returns 422 or code != 0
    assert resp.status_code in [200, 422]
    if resp.status_code == 200:
        assert resp.json()["code"] != 0


def test_login_success(client):
    client.post("/api/auth/register", json={"username": "logintest", "password": "test123"})
    resp = client.post("/api/auth/login", json={"username": "logintest", "password": "test123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "token" in data["data"]


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"username": "pwtest", "password": "test123"})
    resp = client.post("/api/auth/login", json={"username": "pwtest", "password": "wrongpass"})
    assert resp.status_code in [200, 400]
    assert resp.json()["code"] != 0


def test_login_nonexistent_user(client):
    resp = client.post("/api/auth/login", json={"username": "nosuchuser", "password": "test123"})
    assert resp.status_code in [200, 400]
    assert resp.json()["code"] != 0


def test_unauthenticated_access(client):
    resp = client.get("/api/materials")
    assert resp.status_code == 401 or resp.json().get("code", 0) != 0

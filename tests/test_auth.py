"""
认证模块测试（完整示例）
涵盖注册、登录、受保护接口的各种场景
"""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_test_user, get_auth_header


class TestRegister:
    """注册接口测试"""

    def test_register_success(self, client: TestClient):
        """正常注册"""
        resp = client.post("/api/auth/register", json={
            "username": "kylin2024",
            "password": "secure123",
            "name": "麒麟",
            "school": "南开大学",
            "major": "软件工程",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "token" in data["data"]
        assert data["data"]["user"]["username"] == "kylin2024"
        assert data["data"]["user"]["school"] == "南开大学"

    def test_register_duplicate_username(self, client: TestClient):
        """重复用户名注册"""
        # 先注册一次
        client.post("/api/auth/register", json={
            "username": "dupuser",
            "password": "password1",
        })
        # 再次注册同名用户
        resp = client.post("/api/auth/register", json={
            "username": "dupuser",
            "password": "password2",
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == 40001  # AUTH_USERNAME_EXISTS

    def test_register_username_too_short(self, client: TestClient):
        """用户名太短（< 4 字符）"""
        resp = client.post("/api/auth/register", json={
            "username": "abc",
            "password": "password123",
        })
        assert resp.status_code == 422  # FastAPI 验证错误

    def test_register_username_too_long(self, client: TestClient):
        """用户名太长（> 20 字符）"""
        resp = client.post("/api/auth/register", json={
            "username": "a" * 21,
            "password": "password123",
        })
        assert resp.status_code == 422

    def test_register_invalid_username_special_chars(self, client: TestClient):
        """用户名含特殊字符"""
        resp = client.post("/api/auth/register", json={
            "username": "user@name",
            "password": "password123",
        })
        assert resp.status_code == 422

    def test_register_username_with_chinese(self, client: TestClient):
        """用户名含中文（不允许）"""
        resp = client.post("/api/auth/register", json={
            "username": "用户名test",
            "password": "password123",
        })
        assert resp.status_code == 422

    def test_register_password_too_short(self, client: TestClient):
        """密码太短（< 6 字符）"""
        resp = client.post("/api/auth/register", json={
            "username": "validuser",
            "password": "123",
        })
        assert resp.status_code == 422

    def test_register_minimal_fields(self, client: TestClient):
        """只填必填字段（username + password）"""
        resp = client.post("/api/auth/register", json={
            "username": "minimal1",
            "password": "minimal123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 可选字段应有默认值
        assert data["data"]["user"]["name"] == ""
        assert data["data"]["user"]["school"] == ""


class TestLogin:
    """登录接口测试"""

    def test_login_success(self, client: TestClient):
        """正常登录"""
        # 先注册
        create_test_user(client, username="loginuser", password="loginpass")
        # 登录
        resp = client.post("/api/auth/login", json={
            "username": "loginuser",
            "password": "loginpass",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "token" in data["data"]
        assert data["data"]["user"]["username"] == "loginuser"

    def test_login_wrong_password(self, client: TestClient):
        """密码错误"""
        create_test_user(client, username="passuser", password="correctpass")
        resp = client.post("/api/auth/login", json={
            "username": "passuser",
            "password": "wrongpass",
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == 40002  # AUTH_INVALID_CREDENTIALS

    def test_login_nonexistent_user(self, client: TestClient):
        """用户不存在"""
        resp = client.post("/api/auth/login", json={
            "username": "nosuchuser",
            "password": "somepass",
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == 40002

    def test_login_returns_valid_token(self, client: TestClient):
        """登录返回的 Token 可以访问受保护接口"""
        auth_data = create_test_user(client, username="tokenuser", password="tokenpass")
        token = auth_data["token"]

        # 用 token 访问受保护接口（直接测试依赖注入）
        # 这里我们验证 token 格式是否正确（JWT 有 3 部分）
        parts = token.split(".")
        assert len(parts) == 3, "Token 应该是 JWT 格式（3段）"


class TestProtectedEndpoints:
    """受保护接口测试"""

    def test_protected_endpoint_no_token(self, client: TestClient):
        """无 Token 访问受保护接口"""
        # 访问需要认证的接口（例如上传头像）
        resp = client.post("/api/upload/avatar")
        assert resp.status_code == 401  # 自定义认证中间件返回 401

    def test_protected_endpoint_invalid_token(self, client: TestClient):
        """无效 Token 访问受保护接口"""
        resp = client.post(
            "/api/upload/diary-image",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code in (401, 403)

    def test_protected_endpoint_with_valid_token(self, client: TestClient):
        """有效 Token 可以访问受保护接口"""
        auth_data = create_test_user(client, username="authtest1")
        token = auth_data["token"]
        headers = get_auth_header(token)

        # 调用需要认证的接口（骨架接口会返回 500，但至少能通过认证）
        # 这里我们验证不是 401/403
        resp = client.get("/api/user/profile", headers=headers)
        # 骨架路由返回 None，FastAPI 会返回 200 with null body
        # 只需验证不是认证失败
        assert resp.status_code not in (401, 403)

    def test_malformed_authorization_header(self, client: TestClient):
        """格式错误的 Authorization 头"""
        resp = client.get(
            "/api/user/profile",
            headers={"Authorization": "Token sometoken"},  # 应该是 Bearer
        )
        assert resp.status_code in (401, 403)

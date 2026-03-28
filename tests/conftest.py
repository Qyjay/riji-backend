"""
测试配置（conftest.py）
- 使用 SQLite in-memory 测试数据库
- 提供 TestClient fixture
- 提供 create_test_user / get_auth_header helper
- 每个测试自动 rollback（通过 scope='function'）
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# ==================== 测试数据库配置 ====================

TEST_DATABASE_URL = "sqlite://"  # in-memory SQLite

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # 确保所有连接共享同一个 in-memory 数据库
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """覆盖数据库依赖，使用测试数据库"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# 覆盖 FastAPI 依赖
app.dependency_overrides[get_db] = override_get_db


# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重建所有表，测试后删除（自动隔离）"""
    # 导入所有模型确保 Base 知道它们
    from app.models import user, diary, chat, study, social  # noqa
    from app.models import material, anniversary, user_profile, derivative  # noqa
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    """TestClient fixture"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    """数据库会话 fixture（测试中直接操作数据库）"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== Helper 函数 ====================

def create_test_user(
    client: TestClient,
    username: str = "testuser",
    password: str = "test123",
    name: str = "测试用户",
    school: str = "南开大学",
    major: str = "软件工程",
) -> dict:
    """
    通过注册接口创建测试用户
    返回 response data（含 token 和 user）
    """
    resp = client.post("/api/auth/register", json={
        "username": username,
        "password": password,
        "name": name,
        "school": school,
        "major": major,
    })
    assert resp.status_code == 200, f"创建测试用户失败: {resp.json()}"
    data = resp.json()
    assert data["code"] == 0
    return data["data"]


def get_auth_header(token: str) -> dict:
    """生成认证请求头"""
    return {"Authorization": f"Bearer {token}"}

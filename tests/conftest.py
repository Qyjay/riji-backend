"""
测试配置（conftest.py）
- 使用 SQLite in-memory 测试数据库
- 提供 TestClient fixture
- 提供 create_test_user / get_auth_header helper
- 每个测试自动 rollback（通过 scope='function'）
"""
import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.config import settings
from app.upload.router import router as upload_router


def _patch_httpx_testclient_compat():
    """
    兼容 starlette<0.37 与 httpx>=0.28 的 TestClient 参数差异。
    新版 httpx.Client 移除了 app 参数，这里在测试环境中静默忽略。
    """
    init = httpx.Client.__init__
    if getattr(init, "_riji_patched", False):
        return

    def compat_init(self, *args, **kwargs):
        kwargs.pop("app", None)
        return init(self, *args, **kwargs)

    compat_init._riji_patched = True  # type: ignore[attr-defined]
    httpx.Client.__init__ = compat_init  # type: ignore[assignment]


_patch_httpx_testclient_compat()

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


def _ensure_upload_router_registered_for_tests():
    """测试环境补齐 upload 路由，避免依赖 main.py 的路由注册状态。"""
    target_path = "/api/upload/diary-image"
    has_upload_route = any(getattr(route, "path", "") == target_path for route in app.router.routes)
    if not has_upload_route:
        app.include_router(upload_router, prefix="/api")


_ensure_upload_router_registered_for_tests()


# ==================== Fixtures ====================

@pytest.fixture(autouse=True)
def setup_database(monkeypatch):
    """每个测试前重建所有表，测试后删除（自动隔离）"""
    original_vector_enabled = settings.MEMORY_VECTOR_ENABLED
    settings.MEMORY_VECTOR_ENABLED = False
    monkeypatch.setattr(settings, "MINIMAX_MOCK", True)
    from app.ai import minimax_client, model_service

    monkeypatch.setattr(
        model_service,
        "resolve_chat_client",
        lambda _db, _user_id, model_id: (
            minimax_client.get_minimax_client(),
            str(model_id or "builtin:minimax"),
        ),
    )
    # 导入所有模型确保 Base 知道它们
    from app.models import user, diary, chat, study, social  # noqa
    from app.models import material, anniversary, user_profile, derivative  # noqa
    from app.models import plaza, avatar, memory  # noqa
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    settings.MEMORY_VECTOR_ENABLED = original_vector_enabled


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

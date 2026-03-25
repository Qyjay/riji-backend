"""
Service 层单元测试
- social/service.py
- user/service.py
- chat/service.py
使用 in-memory SQLite + mock AI 客户端
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.response import ApiException


# ==================== 测试数据库 ====================

TEST_DB_URL = "sqlite://"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    from app.models import user, social, chat, diary  # noqa
    from app.models import user_profile  # noqa
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_user(db, username="alice"):
    from app.models.user import User
    import time
    now = int(time.time() * 1000)
    u = User(
        id=f"uid-{username}",
        username=username,
        password="hash",
        name=username,
        created_at=now,
        updated_at=now,
    )
    db.add(u)
    db.commit()
    return u


# ==================== social/service 测试 ====================

class TestSocialService:

    def test_list_matches_empty(self, db):
        from app.social import service
        _make_user(db, "alice")
        result = service.list_matches(db, "uid-alice")
        assert result["total"] == 0
        assert result["items"] == []

    def test_create_match_request_ok(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        result = service.create_match_request(db, "uid-alice", "uid-bob", "long_term", ["读书"])
        assert result["user_id"] == "uid-alice"
        assert result["target_id"] == "uid-bob"
        assert result["status"] == "pending"
        assert result["common_tags"] == ["读书"]

    def test_create_match_request_user_not_found(self, db):
        from app.social import service
        _make_user(db, "alice")
        with pytest.raises(ApiException) as exc_info:
            service.create_match_request(db, "uid-alice", "no-such-user", "long_term", [])
        assert exc_info.value.status_code == 404

    def test_create_match_request_duplicate(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        service.create_match_request(db, "uid-alice", "uid-bob", "long_term", [])
        with pytest.raises(ApiException) as exc_info:
            service.create_match_request(db, "uid-alice", "uid-bob", "long_term", [])
        assert exc_info.value.status_code == 400

    def test_respond_match_accept(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        m = service.create_match_request(db, "uid-alice", "uid-bob", "long_term", [])
        result = service.respond_match(db, "uid-bob", m["id"], accept=True)
        assert result["status"] == "accepted"

    def test_respond_match_reject(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        m = service.create_match_request(db, "uid-alice", "uid-bob", "long_term", [])
        result = service.respond_match(db, "uid-bob", m["id"], accept=False)
        assert result["status"] == "rejected"

    def test_respond_match_not_found(self, db):
        from app.social import service
        _make_user(db, "alice")
        with pytest.raises(ApiException) as exc_info:
            service.respond_match(db, "uid-alice", "nonexistent", accept=True)
        assert exc_info.value.status_code == 404

    def test_apply_buddy_ok(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        result = service.apply_buddy(db, "uid-alice", "uid-bob", reason="一起学习")
        assert result["match_type"] == "buddy"
        assert result["match_report"] == "一起学习"

    def test_apply_buddy_user_not_found(self, db):
        from app.social import service
        _make_user(db, "alice")
        with pytest.raises(ApiException) as exc_info:
            service.apply_buddy(db, "uid-alice", "no-such-user")
        assert exc_info.value.status_code == 404

    def test_respond_buddy_ok(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        m = service.apply_buddy(db, "uid-alice", "uid-bob")
        result = service.respond_buddy(db, "uid-bob", m["id"], accept=True)
        assert result["status"] == "accepted"

    def test_respond_buddy_not_found(self, db):
        from app.social import service
        _make_user(db, "alice")
        with pytest.raises(ApiException) as exc_info:
            service.respond_buddy(db, "uid-alice", "nonexistent", accept=True)
        assert exc_info.value.status_code == 404

    def test_get_messages_ok(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        m = service.create_match_request(db, "uid-alice", "uid-bob", "long_term", [])
        result = service.get_messages(db, "uid-alice", m["id"])
        assert result["total"] == 0
        assert result["items"] == []

    def test_get_messages_not_found(self, db):
        from app.social import service
        _make_user(db, "alice")
        with pytest.raises(ApiException) as exc_info:
            service.get_messages(db, "uid-alice", "nonexistent")
        assert exc_info.value.status_code == 404

    def test_get_messages_access_denied(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        _make_user(db, "charlie")
        m = service.create_match_request(db, "uid-alice", "uid-bob", "long_term", [])
        with pytest.raises(ApiException) as exc_info:
            service.get_messages(db, "uid-charlie", m["id"])
        assert exc_info.value.status_code == 404

    def test_list_matches_includes_both_sides(self, db):
        from app.social import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        service.create_match_request(db, "uid-alice", "uid-bob", "long_term", [])
        # bob 也能看到这条匹配
        result = service.list_matches(db, "uid-bob")
        assert result["total"] == 1


# ==================== user/service 测试 ====================

class TestUserService:

    def test_get_portrait_no_profile(self, db):
        from app.user import service
        _make_user(db, "alice")
        result = service.get_portrait(db, "uid-alice")
        assert result is None

    def test_get_portrait_with_profile(self, db):
        from app.user import service
        from app.models.user_profile import UserProfile
        import time
        _make_user(db, "alice")
        profile = UserProfile(
            user_id="uid-alice",
            personality="内向",
            writing_style="简洁",
            interests=json.dumps(["读书", "跑步"]),
            preferences=json.dumps({"music": "古典"}),
            relations=json.dumps({}),
            updated_at=int(time.time() * 1000),
        )
        db.add(profile)
        db.commit()

        result = service.get_portrait(db, "uid-alice")
        assert result is not None
        assert result["personality"] == "内向"
        assert result["interests"] == ["读书", "跑步"]
        assert result["preferences"] == {"music": "古典"}

    @pytest.mark.asyncio
    async def test_refresh_portrait_creates_profile(self, db):
        from app.user import service
        _make_user(db, "alice")

        mock_result = {
            "personality": "外向",
            "writing_style": "活泼",
            "interests": ["旅行"],
            "preferences": {},
            "relations": {},
        }
        mock_client = MagicMock()
        mock_client.generate_portrait = AsyncMock(return_value=mock_result)

        with patch("app.ai.minimax_client.get_minimax_client", return_value=mock_client):
            result = await service.refresh_portrait(db, "uid-alice")

        assert result["personality"] == "外向"

        from app.models.user_profile import UserProfile
        profile = db.query(UserProfile).filter(UserProfile.user_id == "uid-alice").first()
        assert profile is not None
        assert profile.personality == "外向"

    @pytest.mark.asyncio
    async def test_refresh_portrait_updates_existing(self, db):
        from app.user import service
        from app.models.user_profile import UserProfile
        import time
        _make_user(db, "alice")
        profile = UserProfile(
            user_id="uid-alice",
            personality="旧值",
            updated_at=int(time.time() * 1000),
        )
        db.add(profile)
        db.commit()

        mock_result = {
            "personality": "新值",
            "writing_style": "",
            "interests": [],
            "preferences": {},
            "relations": {},
        }
        mock_client = MagicMock()
        mock_client.generate_portrait = AsyncMock(return_value=mock_result)

        with patch("app.ai.minimax_client.get_minimax_client", return_value=mock_client):
            result = await service.refresh_portrait(db, "uid-alice")

        assert result["personality"] == "新值"
        db.refresh(profile)
        assert profile.personality == "新值"


# ==================== chat/service 测试 ====================

class TestChatService:

    def test_save_message(self, db):
        from app.chat import service
        _make_user(db, "alice")
        msg = service.save_message(db, "uid-alice", "user", "你好")
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "你好"
        assert msg.user_id == "uid-alice"
        assert msg.timestamp > 0

    def test_save_message_assistant(self, db):
        from app.chat import service
        _make_user(db, "alice")
        msg = service.save_message(db, "uid-alice", "assistant", "你好，我是 AI")
        assert msg.role == "assistant"

    def test_get_history_empty(self, db):
        from app.chat import service
        _make_user(db, "alice")
        result = service.get_history(db, "uid-alice")
        assert result == []

    def test_get_history_returns_chronological_order(self, db):
        from app.chat import service
        _make_user(db, "alice")
        service.save_message(db, "uid-alice", "user", "第一条")
        service.save_message(db, "uid-alice", "assistant", "第二条")
        service.save_message(db, "uid-alice", "user", "第三条")

        result = service.get_history(db, "uid-alice")
        assert len(result) == 3
        assert result[0].content == "第一条"
        assert result[2].content == "第三条"

    def test_get_history_limit(self, db):
        from app.chat import service
        _make_user(db, "alice")
        for i in range(10):
            service.save_message(db, "uid-alice", "user", f"消息 {i}")
        result = service.get_history(db, "uid-alice", limit=5)
        assert len(result) == 5

    def test_get_history_before_filter(self, db):
        from app.chat import service
        _make_user(db, "alice")
        m1 = service.save_message(db, "uid-alice", "user", "早期消息")
        m2 = service.save_message(db, "uid-alice", "user", "晚期消息")

        # before = m2.timestamp，只应返回 m1
        result = service.get_history(db, "uid-alice", before=m2.timestamp)
        assert len(result) == 1
        assert result[0].content == "早期消息"

    def test_get_history_user_isolation(self, db):
        from app.chat import service
        _make_user(db, "alice")
        _make_user(db, "bob")
        service.save_message(db, "uid-alice", "user", "alice 的消息")
        result = service.get_history(db, "uid-bob")
        assert result == []

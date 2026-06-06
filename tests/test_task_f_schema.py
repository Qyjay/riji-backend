"""
TASK-F (2.1-2.5) 数据模型与建库测试
"""

from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models.chat import ChatMessage, ChatSession
from app.models.material import RawMaterial
from app.models.user import UserLlmModel, UserSettings


def _column_names(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def test_task_f_model_definitions_have_required_columns():
    session_columns = _column_names(ChatSession)
    assert {
        "id",
        "user_id",
        "status",
        "start_time",
        "end_time",
        "message_count",
        "title",
        "summary",
        "mood",
        "mood_emoji",
        "topic_tags",
        "material_id",
        "date",
        "created_at",
    }.issubset(session_columns)

    message_columns = _column_names(ChatMessage)
    assert "session_id" in message_columns

    material_columns = _column_names(RawMaterial)
    assert {"chat_session_id", "start_time", "end_time"}.issubset(material_columns)

    setting_columns = _column_names(UserSettings)
    assert {
        "chat_material_enabled",
        "chat_silence_threshold",
        "chat_material_toast",
        "chat_min_rounds",
        "chat_model_id",
    }.issubset(setting_columns)
    assert {"provider_type", "base_url", "model", "api_key_ciphertext"}.issubset(_column_names(UserLlmModel))

    session_indexes = {index.name for index in ChatSession.__table__.indexes}
    assert "ix_chat_sessions_user_date" in session_indexes
    assert "ix_chat_sessions_user_status" in session_indexes

    message_indexes = {index.name for index in ChatMessage.__table__.indexes}
    assert "ix_chat_messages_session_timestamp" in message_indexes


def test_task_f_schema_exists_in_runtime_test_database(db):
    inspector = inspect(db.bind)

    tables = set(inspector.get_table_names())
    assert "chat_sessions" in tables
    assert "chat_messages" in tables
    assert "raw_materials" in tables
    assert "user_settings" in tables

    chat_session_cols = {col["name"] for col in inspector.get_columns("chat_sessions")}
    assert {
        "id",
        "user_id",
        "status",
        "start_time",
        "end_time",
        "message_count",
        "title",
        "summary",
        "mood",
        "mood_emoji",
        "topic_tags",
        "material_id",
        "date",
        "created_at",
    }.issubset(chat_session_cols)

    chat_message_cols = {col["name"] for col in inspector.get_columns("chat_messages")}
    assert "session_id" in chat_message_cols

    raw_material_cols = {col["name"] for col in inspector.get_columns("raw_materials")}
    assert {"chat_session_id", "start_time", "end_time"}.issubset(raw_material_cols)

    user_settings_cols = {col["name"] for col in inspector.get_columns("user_settings")}
    assert {
        "chat_material_enabled",
        "chat_silence_threshold",
        "chat_material_toast",
        "chat_min_rounds",
        "chat_model_id",
    }.issubset(user_settings_cols)
    assert "user_llm_models" in tables

    chat_session_indexes = {idx["name"] for idx in inspector.get_indexes("chat_sessions")}
    assert "ix_chat_sessions_user_date" in chat_session_indexes
    assert "ix_chat_sessions_user_status" in chat_session_indexes


def test_task_f_schema_available_after_fresh_create_all(tmp_path):
    # 对应 TASK-F 2.5 的删库重建场景：新库 create_all 后应包含完整字段。
    db_path = tmp_path / "task_f_rebuild.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "chat_sessions" in tables

    chat_message_cols = {col["name"] for col in inspector.get_columns("chat_messages")}
    assert "session_id" in chat_message_cols

    raw_material_cols = {col["name"] for col in inspector.get_columns("raw_materials")}
    assert {"chat_session_id", "start_time", "end_time"}.issubset(raw_material_cols)

    user_settings_cols = {col["name"] for col in inspector.get_columns("user_settings")}
    assert {
        "chat_material_enabled",
        "chat_silence_threshold",
        "chat_material_toast",
        "chat_min_rounds",
        "chat_model_id",
    }.issubset(user_settings_cols)
    assert "user_llm_models" in tables

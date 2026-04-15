"""add chat message payload fields

Revision ID: a1c4f7d8e9b2
Revises: 6e2b5c8d1a3f
Create Date: 2026-04-14 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c4f7d8e9b2"
down_revision: Union[str, None] = "6e2b5c8d1a3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _get_table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def _get_index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    tables = _get_table_names()
    if "chat_sessions" not in tables:
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=True, server_default="open"),
            sa.Column("start_time", sa.BigInteger(), nullable=False),
            sa.Column("end_time", sa.BigInteger(), nullable=True),
            sa.Column("message_count", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("title", sa.String(), nullable=True, server_default=""),
            sa.Column("summary", sa.Text(), nullable=True, server_default=""),
            sa.Column("mood", sa.String(), nullable=True, server_default=""),
            sa.Column("mood_emoji", sa.String(), nullable=True, server_default=""),
            sa.Column("topic_tags", sa.Text(), nullable=True, server_default="[]"),
            sa.Column("material_id", sa.String(), nullable=True),
            sa.Column("date", sa.String(), nullable=False),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    session_indexes = _get_index_names("chat_sessions")
    if "ix_chat_sessions_user_date" not in session_indexes:
        op.create_index("ix_chat_sessions_user_date", "chat_sessions", ["user_id", "date"], unique=False)
    if "ix_chat_sessions_user_status" not in session_indexes:
        op.create_index("ix_chat_sessions_user_status", "chat_sessions", ["user_id", "status"], unique=False)

    columns = _get_column_names("chat_messages")
    if not columns:
        return

    if "session_id" not in columns:
        op.add_column("chat_messages", sa.Column("session_id", sa.String(), nullable=True))
        columns.add("session_id")

    if "client_message_id" not in columns:
        op.add_column("chat_messages", sa.Column("client_message_id", sa.String(), nullable=True))
    if "attachments" not in columns:
        op.add_column("chat_messages", sa.Column("attachments", sa.Text(), nullable=True, server_default="[]"))

    indexes = _get_index_names("chat_messages")
    if "ix_chat_messages_session_timestamp" not in indexes and "session_id" in columns and "timestamp" in columns:
        op.create_index("ix_chat_messages_session_timestamp", "chat_messages", ["session_id", "timestamp"], unique=False)


def downgrade() -> None:
    session_indexes = _get_index_names("chat_sessions")
    if "ix_chat_sessions_user_status" in session_indexes:
        op.drop_index("ix_chat_sessions_user_status", table_name="chat_sessions")
    if "ix_chat_sessions_user_date" in session_indexes:
        op.drop_index("ix_chat_sessions_user_date", table_name="chat_sessions")

    indexes = _get_index_names("chat_messages")
    if "ix_chat_messages_session_timestamp" in indexes:
        op.drop_index("ix_chat_messages_session_timestamp", table_name="chat_messages")

    columns = _get_column_names("chat_messages")
    if "attachments" in columns:
        op.drop_column("chat_messages", "attachments")
    if "client_message_id" in columns:
        op.drop_column("chat_messages", "client_message_id")
    if "session_id" in columns:
        op.drop_column("chat_messages", "session_id")

    tables = _get_table_names()
    if "chat_sessions" in tables:
        op.drop_table("chat_sessions")

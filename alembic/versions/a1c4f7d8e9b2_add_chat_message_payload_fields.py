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


def _get_index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    columns = _get_column_names("chat_messages")
    if not columns:
        return

    if "client_message_id" not in columns:
        op.add_column("chat_messages", sa.Column("client_message_id", sa.String(), nullable=True))
    if "attachments" not in columns:
        op.add_column("chat_messages", sa.Column("attachments", sa.Text(), nullable=True, server_default="[]"))

    indexes = _get_index_names("chat_messages")
    if "ix_chat_messages_session_timestamp" not in indexes:
        op.create_index("ix_chat_messages_session_timestamp", "chat_messages", ["session_id", "timestamp"], unique=False)


def downgrade() -> None:
    indexes = _get_index_names("chat_messages")
    if "ix_chat_messages_session_timestamp" in indexes:
        op.drop_index("ix_chat_messages_session_timestamp", table_name="chat_messages")

    columns = _get_column_names("chat_messages")
    if "attachments" in columns:
        op.drop_column("chat_messages", "attachments")
    if "client_message_id" in columns:
        op.drop_column("chat_messages", "client_message_id")

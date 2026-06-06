"""add user llm models

Revision ID: b8f2c6d4e9a1
Revises: i4j5k6l7m8n9
Create Date: 2026-05-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8f2c6d4e9a1"
down_revision: Union[str, Sequence[str], None] = "i4j5k6l7m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if "user_settings" in _tables() and "chat_model_id" not in _columns("user_settings"):
        op.add_column("user_settings", sa.Column("chat_model_id", sa.String(), nullable=True, server_default=""))

    if "user_llm_models" not in _tables():
        op.create_table(
            "user_llm_models",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("provider_type", sa.String(), nullable=False),
            sa.Column("base_url", sa.String(), nullable=False),
            sa.Column("model", sa.String(), nullable=False),
            sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), server_default="1"),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "ix_user_llm_models_user_id" not in _indexes("user_llm_models"):
        op.create_index("ix_user_llm_models_user_id", "user_llm_models", ["user_id"])
    if "ix_user_llm_models_is_enabled" not in _indexes("user_llm_models"):
        op.create_index("ix_user_llm_models_is_enabled", "user_llm_models", ["is_enabled"])


def downgrade() -> None:
    if "user_llm_models" in _tables():
        if "ix_user_llm_models_is_enabled" in _indexes("user_llm_models"):
            op.drop_index("ix_user_llm_models_is_enabled", table_name="user_llm_models")
        if "ix_user_llm_models_user_id" in _indexes("user_llm_models"):
            op.drop_index("ix_user_llm_models_user_id", table_name="user_llm_models")
        op.drop_table("user_llm_models")

    if "user_settings" in _tables() and "chat_model_id" in _columns("user_settings"):
        op.drop_column("user_settings", "chat_model_id")

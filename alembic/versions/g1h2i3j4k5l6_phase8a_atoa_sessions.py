"""Phase 8A: AtoA 搭子模式会话表 + 新字段

Revision ID: g1h2i3j4k5l6
Revises: f2b4d6e8c0a1
Create Date: 2026-05-06

新增/修改内容：
1. 新建 avatar_atoa_sessions 表（Top-10 候选池会话）
2. avatar_atoa_interactions.session_id FK 关联至 avatar_atoa_sessions
3. avatar_surf_logs.top10_session_id 关联本次冲浪的 AtoaSession
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f2b4d6e8c0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _tables() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _add_column_once(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_index_once(index_name: str, table_name: str, columns: list) -> None:
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    # ── 1. 新建 avatar_atoa_sessions 表 ─────────────────────────────────
    if "avatar_atoa_sessions" not in _tables():
        op.create_table(
            "avatar_atoa_sessions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("candidate_ids", sa.Text(), server_default="[]"),
            sa.Column("excluded_ids", sa.Text(), server_default="[]"),
            sa.Column("score_snapshot", sa.Text(), server_default="{}"),
            sa.Column("status", sa.String(), server_default="active"),
            sa.Column("surf_log_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
        )
        op.create_index("ix_atoa_sessions_user", "avatar_atoa_sessions", ["user_id", "created_at"])
        op.create_index("ix_atoa_sessions_user_status", "avatar_atoa_sessions", ["user_id", "status"])

    # ── 2. avatar_atoa_interactions 新增 session_id ──────────────────────
    _add_column_once(
        "avatar_atoa_interactions",
        sa.Column("session_id", sa.String(), nullable=True),
    )
    _create_index_once("ix_atoa_interactions_session", "avatar_atoa_interactions", ["session_id"])

    # ── 3. avatar_surf_logs 新增 top10_session_id ────────────────────────
    _add_column_once(
        "avatar_surf_logs",
        sa.Column("top10_session_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    if "top10_session_id" in _columns("avatar_surf_logs"):
        op.drop_column("avatar_surf_logs", "top10_session_id")

    if "session_id" in _columns("avatar_atoa_interactions"):
        if "ix_atoa_interactions_session" in _indexes("avatar_atoa_interactions"):
            op.drop_index("ix_atoa_interactions_session", "avatar_atoa_interactions")
        op.drop_column("avatar_atoa_interactions", "session_id")

    if "avatar_atoa_sessions" in _tables():
        op.drop_table("avatar_atoa_sessions")

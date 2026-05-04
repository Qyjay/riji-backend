"""add avatar match fields phase5+6

Revision ID: b3c5e7f9a1d2
Revises: a7e9c2d4f6b8
Create Date: 2026-05-03 20:00:00.000000

为 avatar_matches 表添加分身匹配（Phase 5）和 AI 精排（Phase 6）所需字段：
- target_user_id  用户型匹配的目标用户 ID
- match_type      匹配来源类型 post|user
- intent_type     意图类型 buddy/help/share/dating
- risk_flags      JSON 风险标注列表
- suggested_opening AI 生成的开场白
- ai_refined      是否已 AI 精排
- ai_refined_at   AI 精排时间戳
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c5e7f9a1d2"
down_revision: Union[str, None] = "a7e9c2d4f6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def _add_column_once(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_index_once(index_name: str, table_name: str, columns: list) -> None:
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    _add_column_once(
        "avatar_matches",
        sa.Column("target_user_id", sa.String(), nullable=True),
    )
    _add_column_once(
        "avatar_matches",
        sa.Column("match_type", sa.String(), nullable=False, server_default="post"),
    )
    _add_column_once(
        "avatar_matches",
        sa.Column("intent_type", sa.String(), nullable=False, server_default="buddy"),
    )
    _add_column_once(
        "avatar_matches",
        sa.Column("risk_flags", sa.Text(), nullable=False, server_default="[]"),
    )
    _add_column_once(
        "avatar_matches",
        sa.Column("suggested_opening", sa.Text(), nullable=False, server_default=""),
    )
    _add_column_once(
        "avatar_matches",
        sa.Column("ai_refined", sa.Boolean(), nullable=False, server_default="0"),
    )
    _add_column_once(
        "avatar_matches",
        sa.Column("ai_refined_at", sa.BigInteger(), nullable=True),
    )
    _create_index_once(
        "ix_avatar_matches_target_user",
        "avatar_matches",
        ["target_user_id"],
    )


def downgrade() -> None:
    for col in [
        "target_user_id",
        "match_type",
        "intent_type",
        "risk_flags",
        "suggested_opening",
        "ai_refined",
        "ai_refined_at",
    ]:
        if col in _columns("avatar_matches"):
            op.drop_column("avatar_matches", col)

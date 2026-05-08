"""Phase 8B: AtoA 互动追加 interaction_phase / user_decision 字段

Revision ID: f2b4d6e8c0a1
Revises: e1a3c5f7b2d9
Create Date: 2026-05-04

新增字段：
- avatar_atoa_interactions.interaction_phase  当前是第几轮组（每轮组 ≤3 轮）
- avatar_atoa_interactions.user_decision      用户最近一次操作 continue/block/connect
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2b4d6e8c0a1"
down_revision: Union[str, None] = "e1a3c5f7b2d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "interaction_phase" not in _columns("avatar_atoa_interactions"):
        op.add_column(
            "avatar_atoa_interactions",
            sa.Column("interaction_phase", sa.Integer(), server_default="1"),
        )
    if "user_decision" not in _columns("avatar_atoa_interactions"):
        op.add_column(
            "avatar_atoa_interactions",
            sa.Column("user_decision", sa.String(), nullable=True),
        )


def downgrade() -> None:
    for col in ["interaction_phase", "user_decision"]:
        if col in _columns("avatar_atoa_interactions"):
            op.drop_column("avatar_atoa_interactions", col)

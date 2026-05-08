"""Phase 8A: AtoA 探针互动日志 + AvatarMatch 扩展 + AvatarSurfLog 扩展

Revision ID: e1a3c5f7b2d9
Revises: b3c5e7f9a1d2
Create Date: 2026-05-04

新增/修改内容：
1. avatar_matches 表：their_score / their_reasons / is_mutual / peer_match_id / target_avatar_card_id
2. 新建 avatar_atoa_interactions 表（AtoA 探针互动日志）
3. avatar_surf_logs 表：scanned_atoa_pairs / upgraded_to_mutual / surf_report
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1a3c5f7b2d9"
down_revision: Union[str, None] = "b3c5e7f9a1d2"
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
    # ── 1. avatar_matches 新增 AtoA 字段 ────────────────────────────────
    _add_column_once("avatar_matches", sa.Column("their_score", sa.Integer(), server_default="0"))
    _add_column_once("avatar_matches", sa.Column("their_reasons", sa.Text(), server_default="[]"))
    _add_column_once("avatar_matches", sa.Column("is_mutual", sa.Boolean(), server_default="0"))
    _add_column_once("avatar_matches", sa.Column("peer_match_id", sa.String(), nullable=True))
    _add_column_once("avatar_matches", sa.Column("target_avatar_card_id", sa.String(), nullable=True))

    # ── 2. 新建 avatar_atoa_interactions 表 ─────────────────────────────
    if "avatar_atoa_interactions" not in _tables():
        op.create_table(
            "avatar_atoa_interactions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("initiator_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("user_a_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("user_b_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("interaction_type", sa.String(), server_default="card_exchange"),
            sa.Column("outcome", sa.String(), server_default="pending"),
            sa.Column("score_a", sa.Integer(), server_default="0"),
            sa.Column("score_b", sa.Integer(), server_default="0"),
            sa.Column("shared_topics", sa.Text(), server_default="[]"),
            sa.Column("reasons_a", sa.Text(), server_default="[]"),
            sa.Column("reasons_b", sa.Text(), server_default="[]"),
            sa.Column("risk_flags", sa.Text(), server_default="[]"),
            sa.Column("conversation", sa.Text(), server_default="[]"),
            sa.Column("triggered_match_id", sa.String(), nullable=True),
            sa.Column("is_visible_to_a", sa.Boolean(), server_default="1"),
            sa.Column("is_visible_to_b", sa.Boolean(), server_default="0"),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
        )
        op.create_index("ix_atoa_interactions_initiator", "avatar_atoa_interactions", ["initiator_id", "created_at"])
        op.create_index("ix_atoa_interactions_pair", "avatar_atoa_interactions", ["user_a_id", "user_b_id"])
        op.create_index("ix_atoa_interactions_outcome", "avatar_atoa_interactions", ["outcome"])

    # ── 3. avatar_surf_logs 新增 AtoA 统计字段 ──────────────────────────
    _add_column_once("avatar_surf_logs", sa.Column("scanned_atoa_pairs", sa.Integer(), server_default="0"))
    _add_column_once("avatar_surf_logs", sa.Column("upgraded_to_mutual", sa.Integer(), server_default="0"))
    _add_column_once("avatar_surf_logs", sa.Column("surf_report", sa.Text(), server_default=""))


def downgrade() -> None:
    for col in ["their_score", "their_reasons", "is_mutual", "peer_match_id", "target_avatar_card_id"]:
        if col in _columns("avatar_matches"):
            op.drop_column("avatar_matches", col)

    if "avatar_atoa_interactions" in _tables():
        op.drop_table("avatar_atoa_interactions")

    for col in ["scanned_atoa_pairs", "upgraded_to_mutual", "surf_report"]:
        if col in _columns("avatar_surf_logs"):
            op.drop_column("avatar_surf_logs", col)

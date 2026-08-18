"""add social missions and mission candidates

Revision ID: k6l7m8n9o0p1
Revises: j5k6l7m8n9o0
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k6l7m8n9o0p1"
down_revision: Union[str, Sequence[str], None] = "j5k6l7m8n9o0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "social_missions" not in _tables():
        op.create_table(
            "social_missions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("mode", sa.String(), nullable=False),
            sa.Column("purpose_type", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), server_default=""),
            sa.Column("source", sa.String(), server_default="guided_form"),
            sa.Column("status", sa.String(), server_default="draft"),
            sa.Column("time_window", sa.Text(), server_default="{}"),
            sa.Column("location", sa.Text(), server_default="{}"),
            sa.Column("headcount", sa.Text(), server_default="{}"),
            sa.Column("budget", sa.Text(), server_default="{}"),
            sa.Column("must_haves", sa.Text(), server_default="[]"),
            sa.Column("preferences", sa.Text(), server_default="[]"),
            sa.Column("boundaries", sa.Text(), server_default="[]"),
            sa.Column("public_memory_ids", sa.Text(), server_default="[]"),
            sa.Column("public_card_snapshot", sa.Text(), server_default="{}"),
            sa.Column("permissions", sa.Text(), server_default="{}"),
            sa.Column("search_strategy", sa.String(), server_default="search_then_draft"),
            sa.Column("linked_post_id", sa.String(), nullable=True),
            sa.Column("atoa_session_id", sa.String(), sa.ForeignKey("avatar_atoa_sessions.id"), nullable=True),
            sa.Column("candidate_count", sa.Integer(), server_default="0"),
            sa.Column("pending_count", sa.Integer(), server_default="0"),
            sa.Column("expires_at", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
        )
        op.create_index(
            "ix_social_missions_user_status",
            "social_missions",
            ["user_id", "status"],
        )
        op.create_index(
            "ix_social_missions_user_time",
            "social_missions",
            ["user_id", "created_at"],
        )

    if "mission_candidates" not in _tables():
        op.create_table(
            "mission_candidates",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("mission_id", sa.String(), sa.ForeignKey("social_missions.id"), nullable=False),
            sa.Column("target_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("target_post_id", sa.String(), sa.ForeignKey("plaza_posts.id"), nullable=True),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("status", sa.String(), server_default="discovered"),
            sa.Column("hard_constraint_result", sa.Text(), server_default="{}"),
            sa.Column("fit_reasons", sa.Text(), server_default="[]"),
            sa.Column("questions", sa.Text(), server_default="[]"),
            sa.Column("conflicts", sa.Text(), server_default="[]"),
            sa.Column("risk_flags", sa.Text(), server_default="[]"),
            sa.Column("internal_score", sa.Integer(), server_default="0"),
            sa.Column("interaction_id", sa.String(), sa.ForeignKey("avatar_atoa_interactions.id"), nullable=True),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
        )
        op.create_index(
            "ix_mission_candidates_mission_score",
            "mission_candidates",
            ["mission_id", "internal_score"],
        )
        op.create_index(
            "ix_mission_candidates_mission_status",
            "mission_candidates",
            ["mission_id", "status"],
        )

    if "mission_id" not in _columns("matches"):
        op.add_column(
            "matches",
            sa.Column("mission_id", sa.String(), nullable=True),
        )


def downgrade() -> None:
    if "mission_id" in _columns("matches"):
        op.drop_column("matches", "mission_id")
    if "mission_candidates" in _tables():
        op.drop_table("mission_candidates")
    if "social_missions" in _tables():
        op.drop_table("social_missions")

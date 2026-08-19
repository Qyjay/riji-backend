"""add avatar surf jobs

Revision ID: j5k6l7m8n9o0
Revises: b8f2c6d4e9a1
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j5k6l7m8n9o0"
down_revision: Union[str, Sequence[str], None] = "b8f2c6d4e9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "avatar_surf_jobs" in _tables():
        return
    op.create_table(
        "avatar_surf_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trigger", sa.String(), server_default="manual"),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("available_at", sa.BigInteger(), server_default="0"),
        sa.Column("result_json", sa.Text(), server_default="{}"),
        sa.Column("error_message", sa.Text(), server_default=""),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=True),
        sa.Column("finished_at", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_avatar_surf_jobs_status_available",
        "avatar_surf_jobs",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_avatar_surf_jobs_user_time",
        "avatar_surf_jobs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    if "avatar_surf_jobs" in _tables():
        op.drop_table("avatar_surf_jobs")

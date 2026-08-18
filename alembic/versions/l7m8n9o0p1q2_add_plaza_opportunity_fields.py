"""add structured plaza opportunity fields

Revision ID: l7m8n9o0p1q2
Revises: k6l7m8n9o0p1
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l7m8n9o0p1q2"
down_revision: Union[str, Sequence[str], None] = "k6l7m8n9o0p1"
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


def upgrade() -> None:
    columns = [
        sa.Column("mission_id", sa.String(), nullable=True),
        sa.Column("opportunity_mode", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("start_at", sa.BigInteger(), nullable=True),
        sa.Column("end_at", sa.BigInteger(), nullable=True),
        sa.Column("apply_deadline", sa.BigInteger(), nullable=True),
        sa.Column("location_precision", sa.String(), server_default="district"),
        sa.Column("slots_total", sa.Integer(), nullable=True),
        sa.Column("slots_remaining", sa.Integer(), nullable=True),
        sa.Column("allow_waitlist", sa.Boolean(), server_default="0"),
        sa.Column("budget", sa.Text(), server_default="{}"),
        sa.Column("requirements", sa.Text(), server_default="[]"),
        sa.Column("opportunity_status", sa.String(), server_default="open"),
        sa.Column("agent_probe_enabled", sa.Boolean(), server_default="1"),
    ]
    existing = _columns("plaza_posts")
    for column in columns:
        if column.name not in existing:
            op.add_column("plaza_posts", column)

    indexes = _indexes("plaza_posts")
    if "ix_plaza_posts_opportunity" not in indexes:
        op.create_index(
            "ix_plaza_posts_opportunity",
            "plaza_posts",
            ["opportunity_mode", "opportunity_status"],
        )
    if "ix_plaza_posts_start_at" not in indexes:
        op.create_index("ix_plaza_posts_start_at", "plaza_posts", ["start_at"])


def downgrade() -> None:
    indexes = _indexes("plaza_posts")
    if "ix_plaza_posts_start_at" in indexes:
        op.drop_index("ix_plaza_posts_start_at", table_name="plaza_posts")
    if "ix_plaza_posts_opportunity" in indexes:
        op.drop_index("ix_plaza_posts_opportunity", table_name="plaza_posts")
    existing = _columns("plaza_posts")
    for name in [
        "agent_probe_enabled",
        "opportunity_status",
        "requirements",
        "budget",
        "allow_waitlist",
        "slots_remaining",
        "slots_total",
        "location_precision",
        "apply_deadline",
        "end_at",
        "start_at",
        "category",
        "opportunity_mode",
        "mission_id",
    ]:
        if name in existing:
            op.drop_column("plaza_posts", name)

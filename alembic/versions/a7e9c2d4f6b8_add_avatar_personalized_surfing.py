"""add avatar personalized surfing

Revision ID: a7e9c2d4f6b8
Revises: d4f1a8c9b2e7, f3b1d9c2e4a7
Create Date: 2026-05-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7e9c2d4f6b8"
down_revision: Union[str, tuple[str, str], None] = ("d4f1a8c9b2e7", "f3b1d9c2e4a7")
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


def _add_column_once(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_index_once(name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    if "avatar_status" in _tables():
        _add_column_once("avatar_status", sa.Column("surf_frequency", sa.String(), server_default="adaptive"))
        _add_column_once(
            "avatar_status",
            sa.Column(
                "surf_window",
                sa.Text(),
                server_default='{"start":"09:00","end":"23:00","timezone":"Asia/Shanghai"}',
            ),
        )
        _add_column_once("avatar_status", sa.Column("personalized_surf_plan", sa.Text(), server_default="{}"))
        _add_column_once("avatar_status", sa.Column("next_surf_at", sa.BigInteger(), server_default="0"))
        _add_column_once("avatar_status", sa.Column("last_surf_at", sa.BigInteger(), server_default="0"))
        _add_column_once("avatar_status", sa.Column("daily_surf_count", sa.Integer(), server_default="0"))
        _add_column_once("avatar_status", sa.Column("daily_action_count", sa.Integer(), server_default="0"))
        _add_column_once("avatar_status", sa.Column("quiet_mode", sa.Boolean(), server_default="0"))
        _add_column_once("avatar_status", sa.Column("auto_match_enabled", sa.Boolean(), server_default="0"))
        _add_column_once("avatar_status", sa.Column("auto_comment_enabled", sa.Boolean(), server_default="0"))
        _add_column_once("avatar_status", sa.Column("auto_publish_enabled", sa.Boolean(), server_default="0"))
        _add_column_once("avatar_status", sa.Column("surf_lock_until", sa.BigInteger(), server_default="0"))

    if "avatar_usage_stats" not in _tables():
        op.create_table(
            "avatar_usage_stats",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("weekday", sa.Integer(), nullable=False),
            sa.Column("hour", sa.Integer(), nullable=False),
            sa.Column("open_count", sa.Integer(), server_default="0"),
            sa.Column("active_ms", sa.BigInteger(), server_default="0"),
            sa.Column("page_weights", sa.Text(), server_default="{}"),
            sa.Column("last_seen_at", sa.BigInteger(), server_default="0"),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_once(
        "ix_avatar_usage_stats_user_weekday_hour",
        "avatar_usage_stats",
        ["user_id", "weekday", "hour"],
        unique=True,
    )
    _create_index_once("ix_avatar_usage_stats_user_seen", "avatar_usage_stats", ["user_id", "last_seen_at"])

    if "avatar_surf_logs" not in _tables():
        op.create_table(
            "avatar_surf_logs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("trigger", sa.String(), nullable=False),
            sa.Column("status", sa.String(), server_default="success"),
            sa.Column("scanned_posts", sa.Integer(), server_default="0"),
            sa.Column("scanned_users", sa.Integer(), server_default="0"),
            sa.Column("generated_matches", sa.Integer(), server_default="0"),
            sa.Column("generated_actions", sa.Integer(), server_default="0"),
            sa.Column("skipped_reason", sa.String(), server_default=""),
            sa.Column("error_message", sa.Text(), server_default=""),
            sa.Column("started_at", sa.BigInteger(), nullable=False),
            sa.Column("finished_at", sa.BigInteger(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_once("ix_avatar_surf_logs_user_time", "avatar_surf_logs", ["user_id", "started_at"])
    _create_index_once("ix_avatar_surf_logs_status", "avatar_surf_logs", ["status"])


def downgrade() -> None:
    if "avatar_surf_logs" in _tables():
        if "ix_avatar_surf_logs_status" in _indexes("avatar_surf_logs"):
            op.drop_index("ix_avatar_surf_logs_status", table_name="avatar_surf_logs")
        if "ix_avatar_surf_logs_user_time" in _indexes("avatar_surf_logs"):
            op.drop_index("ix_avatar_surf_logs_user_time", table_name="avatar_surf_logs")
        op.drop_table("avatar_surf_logs")

    if "avatar_usage_stats" in _tables():
        if "ix_avatar_usage_stats_user_seen" in _indexes("avatar_usage_stats"):
            op.drop_index("ix_avatar_usage_stats_user_seen", table_name="avatar_usage_stats")
        if "ix_avatar_usage_stats_user_weekday_hour" in _indexes("avatar_usage_stats"):
            op.drop_index("ix_avatar_usage_stats_user_weekday_hour", table_name="avatar_usage_stats")
        op.drop_table("avatar_usage_stats")

    for column_name in [
        "surf_lock_until",
        "auto_publish_enabled",
        "auto_comment_enabled",
        "auto_match_enabled",
        "quiet_mode",
        "daily_action_count",
        "daily_surf_count",
        "last_surf_at",
        "next_surf_at",
        "personalized_surf_plan",
        "surf_window",
        "surf_frequency",
    ]:
        if column_name in _columns("avatar_status"):
            op.drop_column("avatar_status", column_name)

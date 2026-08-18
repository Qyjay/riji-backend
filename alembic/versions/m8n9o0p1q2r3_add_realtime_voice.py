"""add realtime voice sessions and tool audit

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-08-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m8n9o0p1q2r3"
down_revision: Union[str, Sequence[str], None] = "l7m8n9o0p1q2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "realtime_voice_sessions" not in _tables():
        op.create_table(
            "realtime_voice_sessions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "chat_session_id",
                sa.String(),
                sa.ForeignKey("chat_sessions.id"),
                nullable=True,
            ),
            sa.Column("provider", sa.String(), server_default="volcengine_duplex"),
            sa.Column("provider_session_id", sa.String(), server_default=""),
            sa.Column("status", sa.String(), server_default="connecting"),
            sa.Column("client_platform", sa.String(), server_default="h5"),
            sa.Column("input_format", sa.String(), server_default="pcm_16k_s16le"),
            sa.Column("output_format", sa.String(), server_default="pcm_24k_s16le"),
            sa.Column("voice", sa.String(), server_default=""),
            sa.Column("started_at", sa.BigInteger(), nullable=False),
            sa.Column("ended_at", sa.BigInteger(), nullable=True),
            sa.Column("last_active_at", sa.BigInteger(), nullable=False),
            sa.Column("close_reason", sa.String(), server_default=""),
            sa.Column("provider_log_id", sa.String(), server_default=""),
            sa.Column("usage_json", sa.Text(), server_default="{}"),
            sa.Column("error_code", sa.String(), server_default=""),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
        )
        op.create_index(
            "ix_realtime_voice_sessions_user_time",
            "realtime_voice_sessions",
            ["user_id", "created_at"],
        )
        op.create_index(
            "ix_realtime_voice_sessions_status_active",
            "realtime_voice_sessions",
            ["status", "last_active_at"],
        )
        op.create_index(
            "ix_realtime_voice_sessions_provider_session",
            "realtime_voice_sessions",
            ["provider_session_id"],
        )

    if "realtime_tool_calls" not in _tables():
        op.create_table(
            "realtime_tool_calls",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "voice_session_id",
                sa.String(),
                sa.ForeignKey("realtime_voice_sessions.id"),
                nullable=False,
            ),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("provider_call_id", sa.String(), nullable=False),
            sa.Column("tool_name", sa.String(), nullable=False),
            sa.Column("arguments_json", sa.Text(), server_default="{}"),
            sa.Column("risk_level", sa.String(), server_default="R0"),
            sa.Column("status", sa.String(), server_default="received"),
            sa.Column("result_json", sa.Text(), server_default="{}"),
            sa.Column("confirmation_id", sa.String(), nullable=True),
            sa.Column("idempotency_key", sa.String(), nullable=False),
            sa.Column("error_message", sa.Text(), server_default=""),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.Column("finished_at", sa.BigInteger(), nullable=True),
            sa.UniqueConstraint(
                "voice_session_id",
                "provider_call_id",
                name="uq_realtime_tool_call_provider",
            ),
        )
        op.create_index(
            "ix_realtime_tool_calls_user_time",
            "realtime_tool_calls",
            ["user_id", "created_at"],
        )
        op.create_index(
            "ix_realtime_tool_calls_status",
            "realtime_tool_calls",
            ["status", "updated_at"],
        )
        op.create_index(
            "ix_realtime_tool_calls_idempotency",
            "realtime_tool_calls",
            ["idempotency_key"],
        )


def downgrade() -> None:
    tables = _tables()
    if "realtime_tool_calls" in tables:
        op.drop_table("realtime_tool_calls")
    if "realtime_voice_sessions" in tables:
        op.drop_table("realtime_voice_sessions")

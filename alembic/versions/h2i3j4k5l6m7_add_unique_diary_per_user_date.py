"""Add one-diary-per-user-date constraint

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_diaries_user_date"


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _dedupe_diaries() -> None:
    """Keep the newest diary when historical duplicate user/date rows exist."""
    conn = op.get_bind()
    duplicate_groups = conn.execute(sa.text("""
        SELECT user_id, date, COUNT(*) AS count
        FROM diaries
        GROUP BY user_id, date
        HAVING COUNT(*) > 1
    """)).mappings().all()

    for group in duplicate_groups:
        user_id = group["user_id"]
        date = group["date"]
        if date is None:
            rows = conn.execute(sa.text("""
                SELECT id
                FROM diaries
                WHERE user_id = :user_id AND date IS NULL
                ORDER BY updated_at DESC, created_at DESC, id DESC
            """), {"user_id": user_id}).mappings().all()
        else:
            rows = conn.execute(sa.text("""
                SELECT id
                FROM diaries
                WHERE user_id = :user_id AND date = :date
                ORDER BY updated_at DESC, created_at DESC, id DESC
            """), {"user_id": user_id, "date": date}).mappings().all()

        duplicate_ids = [row["id"] for row in rows[1:]]
        for diary_id in duplicate_ids:
            conn.execute(sa.text("DELETE FROM diaries WHERE id = :id"), {"id": diary_id})


def upgrade() -> None:
    _dedupe_diaries()
    if INDEX_NAME not in _index_names("diaries"):
        op.create_index(INDEX_NAME, "diaries", ["user_id", "date"], unique=True)


def downgrade() -> None:
    if INDEX_NAME in _index_names("diaries"):
        op.drop_index(INDEX_NAME, table_name="diaries")

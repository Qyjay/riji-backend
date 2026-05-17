"""add ai_comment to diaries

Revision ID: i4j5k6l7m8n9
Revises: h2i3j4k5l6m7
Create Date: 2026-05-17 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i4j5k6l7m8n9"
down_revision: Union[str, None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _get_column_names("diaries")
    if not columns:
        return

    if "ai_comment" not in columns:
        op.add_column(
            "diaries",
            sa.Column("ai_comment", sa.Text(), nullable=True, server_default=""),
        )

    op.execute(sa.text("UPDATE diaries SET ai_comment = '' WHERE ai_comment IS NULL"))


def downgrade() -> None:
    columns = _get_column_names("diaries")
    if not columns:
        return

    if "ai_comment" in columns:
        op.drop_column("diaries", "ai_comment")

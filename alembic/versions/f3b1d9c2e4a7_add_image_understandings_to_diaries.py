"""add image_understandings to diaries

Revision ID: f3b1d9c2e4a7
Revises: 831ee9e5cb90
Create Date: 2026-04-15 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3b1d9c2e4a7"
down_revision: Union[str, None] = "831ee9e5cb90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_column_names(table_name: str) -> set[str]:
    """读取指定表字段名；表不存在时返回空集合。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _get_column_names("diaries")
    if not columns:
        return

    if "image_understandings" not in columns:
        op.add_column(
            "diaries",
            sa.Column("image_understandings", sa.Text(), nullable=True, server_default="[]"),
        )

    op.execute(sa.text("UPDATE diaries SET image_understandings = '[]' WHERE image_understandings IS NULL"))


def downgrade() -> None:
    columns = _get_column_names("diaries")
    if not columns:
        return

    if "image_understandings" in columns:
        op.drop_column("diaries", "image_understandings")

"""add chat columns to raw_materials

Revision ID: 9f0e2b6a1c4d
Revises: fd6ad53a1082
Create Date: 2026-04-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f0e2b6a1c4d"
down_revision: Union[str, None] = "fd6ad53a1082"
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
    columns = _get_column_names("raw_materials")
    if not columns:
        return

    if "chat_session_id" not in columns:
        op.add_column("raw_materials", sa.Column("chat_session_id", sa.String(), nullable=True))
    if "start_time" not in columns:
        op.add_column("raw_materials", sa.Column("start_time", sa.BigInteger(), nullable=True))
    if "end_time" not in columns:
        op.add_column("raw_materials", sa.Column("end_time", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    columns = _get_column_names("raw_materials")
    if not columns:
        return

    if "end_time" in columns:
        op.drop_column("raw_materials", "end_time")
    if "start_time" in columns:
        op.drop_column("raw_materials", "start_time")
    if "chat_session_id" in columns:
        op.drop_column("raw_materials", "chat_session_id")

"""add chat settings to user_settings

Revision ID: 6e2b5c8d1a3f
Revises: 9f0e2b6a1c4d
Create Date: 2026-04-07 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6e2b5c8d1a3f"
down_revision: Union[str, None] = "9f0e2b6a1c4d"
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
    columns = _get_column_names("user_settings")
    if not columns:
        return

    if "chat_material_enabled" not in columns:
        op.add_column("user_settings", sa.Column("chat_material_enabled", sa.Boolean(), nullable=True, default=True))
    if "chat_silence_threshold" not in columns:
        op.add_column("user_settings", sa.Column("chat_silence_threshold", sa.Integer(), nullable=True, default=30))
    if "chat_material_toast" not in columns:
        op.add_column("user_settings", sa.Column("chat_material_toast", sa.Boolean(), nullable=True, default=True))
    if "chat_min_rounds" not in columns:
        op.add_column("user_settings", sa.Column("chat_min_rounds", sa.Integer(), nullable=True, default=3))


def downgrade() -> None:
    columns = _get_column_names("user_settings")
    if not columns:
        return

    if "chat_min_rounds" in columns:
        op.drop_column("user_settings", "chat_min_rounds")
    if "chat_material_toast" in columns:
        op.drop_column("user_settings", "chat_material_toast")
    if "chat_silence_threshold" in columns:
        op.drop_column("user_settings", "chat_silence_threshold")
    if "chat_material_enabled" in columns:
        op.drop_column("user_settings", "chat_material_enabled")
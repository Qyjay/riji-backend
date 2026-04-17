"""add parent comment id to plaza comments

Revision ID: d4f1a8c9b2e7
Revises: c2d4e6f8a901
Create Date: 2026-04-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f1a8c9b2e7"
down_revision: Union[str, None] = "c2d4e6f8a901"
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
    columns = _columns("plaza_comments")
    if "parent_comment_id" not in columns:
        op.add_column("plaza_comments", sa.Column("parent_comment_id", sa.String(), nullable=True))
    if "ix_plaza_comments_parent_comment_id" not in _indexes("plaza_comments"):
        op.create_index("ix_plaza_comments_parent_comment_id", "plaza_comments", ["parent_comment_id"])


def downgrade() -> None:
    if "ix_plaza_comments_parent_comment_id" in _indexes("plaza_comments"):
        op.drop_index("ix_plaza_comments_parent_comment_id", table_name="plaza_comments")
    if "parent_comment_id" in _columns("plaza_comments"):
        op.drop_column("plaza_comments", "parent_comment_id")

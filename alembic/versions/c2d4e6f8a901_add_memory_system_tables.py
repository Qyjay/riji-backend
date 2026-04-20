"""add memory system tables

Revision ID: c2d4e6f8a901
Revises: 831ee9e5cb90
Create Date: 2026-04-15 19:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d4e6f8a901"
down_revision: Union[str, None] = "831ee9e5cb90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _create_index_once(name: str, table_name: str, columns: list[str], unique: bool = False) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    tables = _table_names()

    if "memory_documents" not in tables:
        op.create_table(
            "memory_documents",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("source_type", sa.String(), nullable=False),
            sa.Column("source_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), server_default=""),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("summary", sa.Text(), server_default=""),
            sa.Column("visibility", sa.String(), server_default="private"),
            sa.Column("memory_scope", sa.String(), server_default="self"),
            sa.Column("emotion", sa.Text(), server_default="{}"),
            sa.Column("tags", sa.Text(), server_default="[]"),
            sa.Column("metadata", sa.Text(), server_default="{}"),
            sa.Column("occurred_at", sa.BigInteger(), nullable=False),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.Column("content_hash", sa.String(), server_default=""),
            sa.Column("is_deleted", sa.Boolean(), server_default="0"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_once("ix_memory_documents_user_source_type", "memory_documents", ["user_id", "source_type"])
    _create_index_once("ix_memory_documents_user_occurred", "memory_documents", ["user_id", "occurred_at"])
    _create_index_once("ix_memory_documents_user_visibility", "memory_documents", ["user_id", "visibility"])
    _create_index_once("ix_memory_documents_source", "memory_documents", ["source_type", "source_id"])
    _create_index_once("ix_memory_documents_content_hash", "memory_documents", ["content_hash"])

    tables = _table_names()
    if "memory_chunks" not in tables:
        op.create_table(
            "memory_chunks",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("document_id", sa.String(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source_type", sa.String(), nullable=False),
            sa.Column("source_id", sa.String(), nullable=False),
            sa.Column("visibility", sa.String(), server_default="private"),
            sa.Column("tags", sa.Text(), server_default="[]"),
            sa.Column("importance_score", sa.Float(), server_default="0.5"),
            sa.Column("embedding_ref", sa.String(), server_default=""),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(["document_id"], ["memory_documents.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_once("ix_memory_chunks_user_document", "memory_chunks", ["user_id", "document_id"])
    _create_index_once("ix_memory_chunks_user_source_type", "memory_chunks", ["user_id", "source_type"])
    _create_index_once("ix_memory_chunks_user_visibility", "memory_chunks", ["user_id", "visibility"])

    tables = _table_names()
    if "memory_facts" not in tables:
        op.create_table(
            "memory_facts",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("subject", sa.String(), server_default=""),
            sa.Column("predicate", sa.String(), server_default=""),
            sa.Column("object", sa.String(), server_default=""),
            sa.Column("confidence", sa.Float(), server_default="0.7"),
            sa.Column("stability", sa.String(), server_default="recent"),
            sa.Column("evidence_document_id", sa.String(), nullable=True),
            sa.Column("evidence_chunk_id", sa.String(), nullable=True),
            sa.Column("source_type", sa.String(), server_default=""),
            sa.Column("valid_from", sa.BigInteger(), nullable=True),
            sa.Column("valid_to", sa.BigInteger(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default="1"),
            sa.Column("is_pinned", sa.Boolean(), server_default="0"),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(["evidence_chunk_id"], ["memory_chunks.id"]),
            sa.ForeignKeyConstraint(["evidence_document_id"], ["memory_documents.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_once("ix_memory_facts_user_category", "memory_facts", ["user_id", "category"])
    _create_index_once("ix_memory_facts_user_active", "memory_facts", ["user_id", "is_active"])
    _create_index_once("ix_memory_facts_evidence_document", "memory_facts", ["evidence_document_id"])

    tables = _table_names()
    if "memory_profiles" not in tables:
        op.create_table(
            "memory_profiles",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("profile_type", sa.String(), server_default="avatar"),
            sa.Column("summary", sa.Text(), server_default=""),
            sa.Column("traits", sa.Text(), server_default="{}"),
            sa.Column("interests", sa.Text(), server_default="[]"),
            sa.Column("preferences", sa.Text(), server_default="{}"),
            sa.Column("relations", sa.Text(), server_default="{}"),
            sa.Column("social_style", sa.Text(), server_default="{}"),
            sa.Column("boundaries", sa.Text(), server_default="[]"),
            sa.Column("recent_state", sa.Text(), server_default=""),
            sa.Column("version", sa.Integer(), server_default="1"),
            sa.Column("generated_at", sa.BigInteger(), nullable=False),
            sa.Column("source_range", sa.Text(), server_default="{}"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_once("ix_memory_profiles_user_type", "memory_profiles", ["user_id", "profile_type"], unique=True)

    tables = _table_names()
    if "avatar_cards" not in tables:
        op.create_table(
            "avatar_cards",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), server_default=""),
            sa.Column("public_summary", sa.Text(), server_default=""),
            sa.Column("interest_tags", sa.Text(), server_default="[]"),
            sa.Column("social_intent", sa.Text(), server_default="[]"),
            sa.Column("conversation_style", sa.Text(), server_default="{}"),
            sa.Column("boundaries", sa.Text(), server_default="[]"),
            sa.Column("visibility", sa.String(), server_default="private"),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )

    tables = _table_names()
    if "agent_actions" not in tables:
        op.create_table(
            "agent_actions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("agent_id", sa.String(), server_default=""),
            sa.Column("action_type", sa.String(), nullable=False),
            sa.Column("target_type", sa.String(), server_default=""),
            sa.Column("target_id", sa.String(), server_default=""),
            sa.Column("input_context", sa.Text(), server_default="{}"),
            sa.Column("output_text", sa.Text(), server_default=""),
            sa.Column("status", sa.String(), server_default="draft"),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_once("ix_agent_actions_user_status", "agent_actions", ["user_id", "status"])
    _create_index_once("ix_agent_actions_target", "agent_actions", ["target_type", "target_id"])


def downgrade() -> None:
    for name, table in [
        ("ix_agent_actions_target", "agent_actions"),
        ("ix_agent_actions_user_status", "agent_actions"),
    ]:
        if name in _index_names(table):
            op.drop_index(name, table_name=table)
    if "agent_actions" in _table_names():
        op.drop_table("agent_actions")
    if "avatar_cards" in _table_names():
        op.drop_table("avatar_cards")
    if "ix_memory_profiles_user_type" in _index_names("memory_profiles"):
        op.drop_index("ix_memory_profiles_user_type", table_name="memory_profiles")
    if "memory_profiles" in _table_names():
        op.drop_table("memory_profiles")
    for name in [
        "ix_memory_facts_evidence_document",
        "ix_memory_facts_user_active",
        "ix_memory_facts_user_category",
    ]:
        if name in _index_names("memory_facts"):
            op.drop_index(name, table_name="memory_facts")
    if "memory_facts" in _table_names():
        op.drop_table("memory_facts")
    for name in [
        "ix_memory_chunks_user_visibility",
        "ix_memory_chunks_user_source_type",
        "ix_memory_chunks_user_document",
    ]:
        if name in _index_names("memory_chunks"):
            op.drop_index(name, table_name="memory_chunks")
    if "memory_chunks" in _table_names():
        op.drop_table("memory_chunks")
    for name in [
        "ix_memory_documents_content_hash",
        "ix_memory_documents_source",
        "ix_memory_documents_user_visibility",
        "ix_memory_documents_user_occurred",
        "ix_memory_documents_user_source_type",
    ]:
        if name in _index_names("memory_documents"):
            op.drop_index(name, table_name="memory_documents")
    if "memory_documents" in _table_names():
        op.drop_table("memory_documents")

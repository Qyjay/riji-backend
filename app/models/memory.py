"""
统一记忆系统数据模型
- MemoryDocument: 原始记忆文档，保留证据来源
- MemoryChunk: 可检索的记忆片段
- MemoryFact: 从原文抽取的结构化记忆
- MemoryProfile: 多场景画像快照
- AvatarCard: 可用于匹配/agent-to-agent 的分身名片
- AgentAction: 分身行动草稿、审批与审计记录
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Column, Float, ForeignKey, Index, Integer, String, Text

from app.database import Base


def _uuid():
    return str(uuid4())


class MemoryDocument(Base):
    """一条完整来源内容，例如日记、聊天会话、帖子或社交消息。"""

    __tablename__ = "memory_documents"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    title = Column(String, default="")
    content = Column(Text, nullable=False)
    summary = Column(Text, default="")
    visibility = Column(String, default="private")
    memory_scope = Column(String, default="self")
    emotion = Column(Text, default="{}")
    tags = Column(Text, default="[]")
    metadata_json = Column("metadata", Text, default="{}")
    occurred_at = Column(BigInteger, nullable=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)
    content_hash = Column(String, default="")
    is_deleted = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_memory_documents_user_source_type", "user_id", "source_type"),
        Index("ix_memory_documents_user_occurred", "user_id", "occurred_at"),
        Index("ix_memory_documents_user_visibility", "user_id", "visibility"),
        Index("ix_memory_documents_source", "source_type", "source_id"),
        Index("ix_memory_documents_content_hash", "content_hash"),
    )


class MemoryChunk(Base):
    """用于检索和注入 prompt 的小块原文。"""

    __tablename__ = "memory_chunks"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    document_id = Column(String, ForeignKey("memory_documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=False)
    visibility = Column(String, default="private")
    tags = Column(Text, default="[]")
    importance_score = Column(Float, default=0.5)
    embedding_ref = Column(String, default="")
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_memory_chunks_user_document", "user_id", "document_id"),
        Index("ix_memory_chunks_user_source_type", "user_id", "source_type"),
        Index("ix_memory_chunks_user_visibility", "user_id", "visibility"),
    )


class MemoryFact(Base):
    """结构化记忆，可追溯到原文证据。"""

    __tablename__ = "memory_facts"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    subject = Column(String, default="")
    predicate = Column(String, default="")
    object = Column(String, default="")
    confidence = Column(Float, default=0.7)
    stability = Column(String, default="recent")
    evidence_document_id = Column(String, ForeignKey("memory_documents.id"), nullable=True)
    evidence_chunk_id = Column(String, ForeignKey("memory_chunks.id"), nullable=True)
    source_type = Column(String, default="")
    valid_from = Column(BigInteger, nullable=True)
    valid_to = Column(BigInteger, nullable=True)
    is_active = Column(Boolean, default=True)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_memory_facts_user_category", "user_id", "category"),
        Index("ix_memory_facts_user_active", "user_id", "is_active"),
        Index("ix_memory_facts_evidence_document", "evidence_document_id"),
    )


class MemoryProfile(Base):
    """多场景画像快照。"""

    __tablename__ = "memory_profiles"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    profile_type = Column(String, default="avatar")
    summary = Column(Text, default="")
    traits = Column(Text, default="{}")
    interests = Column(Text, default="[]")
    preferences = Column(Text, default="{}")
    relations = Column(Text, default="{}")
    social_style = Column(Text, default="{}")
    boundaries = Column(Text, default="[]")
    recent_state = Column(Text, default="")
    version = Column(Integer, default=1)
    generated_at = Column(BigInteger, nullable=False)
    source_range = Column(Text, default="{}")

    __table_args__ = (
        Index("ix_memory_profiles_user_type", "user_id", "profile_type", unique=True),
    )


class AvatarCard(Base):
    """分身对外名片，只包含允许用于匹配/社交探索的信息。"""

    __tablename__ = "avatar_cards"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    display_name = Column(String, default="")
    public_summary = Column(Text, default="")
    interest_tags = Column(Text, default="[]")
    social_intent = Column(Text, default="[]")
    conversation_style = Column(Text, default="{}")
    boundaries = Column(Text, default="[]")
    visibility = Column(String, default="private")
    updated_at = Column(BigInteger, nullable=False)


class AgentAction(Base):
    """分身行动记录，用于草稿审批和审计。"""

    __tablename__ = "agent_actions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    agent_id = Column(String, default="")
    action_type = Column(String, nullable=False)
    target_type = Column(String, default="")
    target_id = Column(String, default="")
    input_context = Column(Text, default="{}")
    output_text = Column(Text, default="")
    status = Column(String, default="draft")
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_agent_actions_user_status", "user_id", "status"),
        Index("ix_agent_actions_target", "target_type", "target_id"),
    )

"""
聊天消息数据模型
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String, Text

from app.database import Base


def _uuid():
    return str(uuid4())


class ChatSession(Base):
    """对话段 — 一段连续对话的封装"""
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="open")           # "open" | "closed"
    start_time = Column(BigInteger, nullable=False)    # 第一条消息时间戳（ms）
    end_time = Column(BigInteger, nullable=True)       # 最后一条消息时间戳（ms）
    message_count = Column(Integer, default=0)         # 消息条数（user+assistant 各算一条）
    title = Column(String, default="")                 # AI 生成标题
    summary = Column(Text, default="")                 # AI 生成摘要
    mood = Column(String, default="")                  # 情绪标签
    mood_emoji = Column(String, default="")            # 情绪 emoji
    topic_tags = Column(Text, default="[]")            # JSON: 话题标签
    material_id = Column(String, nullable=True)        # 关联素材 ID
    date = Column(String, nullable=False)              # 归属日期 YYYY-MM-DD
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_chat_sessions_user_date", "user_id", "date"),
        Index("ix_chat_sessions_user_status", "user_id", "status"),
    )


class ChatMessage(Base):
    """AI 对话消息表"""
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)    # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)  # 毫秒时间戳
    session_id = Column(String, nullable=True)  # 关联 chat_sessions.id
    client_message_id = Column(String, nullable=True)
    attachments = Column(Text, default="[]")

    __table_args__ = (
        # 按用户和时间排序索引
        Index("ix_chat_messages_user_timestamp", "user_id", "timestamp"),
        Index("ix_chat_messages_session_timestamp", "session_id", "timestamp"),
    )

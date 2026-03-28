"""
聊天消息数据模型
"""
from sqlalchemy import BigInteger, Column, ForeignKey, Index, String, Text

from app.database import Base


class ChatMessage(Base):
    """AI 对话消息表"""
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(String, nullable=False)    # 'user' | 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)  # 毫秒时间戳

    __table_args__ = (
        # 按用户和时间排序索引
        Index("ix_chat_messages_user_timestamp", "user_id", "timestamp"),
    )

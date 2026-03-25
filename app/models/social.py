"""
社交相关数据模型
- Match: 搭子匹配记录
- SocialMessage: 搭子聊天消息
"""
from sqlalchemy import BigInteger, Column, ForeignKey, String, Text

from app.database import Base


class Match(Base):
    """搭子匹配表"""
    __tablename__ = "matches"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    target_id = Column(String, ForeignKey("users.id"), nullable=False)
    common_tags = Column(Text, default="[]")    # JSON array: 共同标签
    status = Column(String, default="pending")  # pending / accepted / rejected
    created_at = Column(BigInteger, nullable=False)


class SocialMessage(Base):
    """搭子聊天消息表"""
    __tablename__ = "social_messages"

    id = Column(String, primary_key=True)
    match_id = Column(String, ForeignKey("matches.id"), nullable=False)
    from_uid = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)

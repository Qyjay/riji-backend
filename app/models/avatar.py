"""
AI 分身相关数据模型
- AvatarMemory: 分身记忆库
- AvatarStatus: 分身状态
- AvatarMatch: 分身推荐匹配
- AvatarProfile: 分身侧写
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Column, Float, ForeignKey, Index, Integer, String, Text

from app.database import Base


def _uuid():
    """生成字符串 UUID"""
    return str(uuid4())


class AvatarMemory(Base):
    """分身记忆库表"""
    __tablename__ = "avatar_memories"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=False)           # fact/interest/personality/need/habit/relation
    content = Column(Text, nullable=False)              # 记忆内容
    source = Column(String, default="manual")           # diary/chat/manual/behavior
    source_ref = Column(String, default="")             # 来源引用 ID（如日记 ID）
    confidence = Column(Float, default=1.0)             # 置信度 0.0-1.0
    is_active = Column(Boolean, default=True)           # 是否激活
    is_pinned = Column(Boolean, default=False)          # 是否置顶
    need_type = Column(String, nullable=True)           # need 专属：buddy/dating/help/activity
    urgency = Column(String, nullable=True)             # need 专属：active/passive
    expiry = Column(BigInteger, nullable=True)          # need 专属：过期时间戳
    match_status = Column(String, nullable=True)        # need 专属：searching/matched/expired
    tags = Column(Text, default="[]")                   # JSON: string[] 关联标签
    created_at = Column(BigInteger, nullable=False)     # 毫秒时间戳
    updated_at = Column(BigInteger, nullable=False)     # 毫秒时间戳

    __table_args__ = (
        # 按用户+类型查询索引
        Index("ix_avatar_memories_user_category", "user_id", "category"),
    )


class AvatarStatus(Base):
    """分身状态表（每个用户一条记录）"""
    __tablename__ = "avatar_status"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)           # 分身是否在线冲浪
    browsed_count = Column(Integer, default=0)          # 已浏览帖子数
    matched_count = Column(Integer, default=0)          # 已匹配帖子数
    chatting_count = Column(Integer, default=0)         # 正在聊天数
    last_active_at = Column(BigInteger, default=0)      # 最后活跃时间
    enabled_channels = Column(Text, default='["buddy","help","share","dating"]')  # JSON: string[]
    enabled_actions = Column(Text, default='["browse","match","comment"]')        # JSON: string[]
    match_range = Column(Text, default='{"school":"","distanceKm":10}')          # JSON: {school, distanceKm}


class AvatarMatch(Base):
    """分身推荐匹配表"""
    __tablename__ = "avatar_matches"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)        # 被推荐的用户
    post_id = Column(String, ForeignKey("plaza_posts.id"), nullable=False)  # 匹配的帖子
    match_score = Column(Integer, default=0)            # 匹配度 0-100
    match_reasons = Column(Text, default="[]")          # JSON: string[] 匹配原因
    agent_conversation = Column(Text, default="[]")     # JSON: AgentConversationMessage[]
    status = Column(String, default="new")              # new/viewed/chatting/dismissed
    created_at = Column(BigInteger, nullable=False)     # 毫秒时间戳

    __table_args__ = (
        # 按用户查询索引
        Index("ix_avatar_matches_user_id", "user_id"),
        # 按状态查询索引
        Index("ix_avatar_matches_status", "status"),
    )


class AvatarProfile(Base):
    """分身侧写表（每个用户一条记录）"""
    __tablename__ = "avatar_profiles"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    summary = Column(Text, default="")                  # AI 生成的人格摘要
    diary_count = Column(Integer, default=0)            # 基于多少篇日记生成
    chat_count = Column(Integer, default=0)             # 基于多少条对话生成
    generated_at = Column(BigInteger, default=0)        # 生成时间戳

"""
AI 分身相关数据模型
- AvatarMemory: 分身记忆库
- AvatarStatus: 分身状态
- AvatarMatch: 分身推荐匹配
- AvatarProfile: 分身侧写
- AvatarUsageStat: App 使用习惯聚合
- AvatarSurfLog: 分身冲浪日志
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
    surf_frequency = Column(String, default="adaptive")  # adaptive/low/medium/high/custom
    surf_window = Column(Text, default='{"start":"09:00","end":"23:00","timezone":"Asia/Shanghai"}')
    personalized_surf_plan = Column(Text, default="{}")  # JSON: 个性化冲浪计划
    next_surf_at = Column(BigInteger, default=0)         # 下次允许冲浪时间
    last_surf_at = Column(BigInteger, default=0)         # 上次实际冲浪时间
    daily_surf_count = Column(Integer, default=0)        # 今日冲浪次数
    daily_action_count = Column(Integer, default=0)      # 今日行动数
    quiet_mode = Column(Boolean, default=False)          # 用户暂停分身
    auto_match_enabled = Column(Boolean, default=False)  # 是否自动生成推荐
    auto_comment_enabled = Column(Boolean, default=False)  # 是否自动生成评论草稿
    auto_publish_enabled = Column(Boolean, default=False)  # 是否自动发布（默认关闭）
    surf_lock_until = Column(BigInteger, default=0)      # 调度幂等锁


class AvatarMatch(Base):
    """分身推荐匹配表"""
    __tablename__ = "avatar_matches"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)        # 被推荐的用户
    post_id = Column(String, ForeignKey("plaza_posts.id"), nullable=False)  # 匹配的帖子（用户型匹配取对方最近帖）
    match_score = Column(Integer, default=0)            # 匹配度 0-100
    match_reasons = Column(Text, default="[]")          # JSON: string[] 匹配原因
    agent_conversation = Column(Text, default="[]")     # JSON: AgentConversationMessage[]
    status = Column(String, default="new")              # new/viewed/chatting/dismissed
    created_at = Column(BigInteger, nullable=False)     # 毫秒时间戳

    # Phase 5 分身匹配扩展字段（帖子型 / 用户型）
    target_user_id = Column(String, ForeignKey("users.id"), nullable=True)  # 用户型匹配：目标用户 ID
    match_type = Column(String, default="post")         # post（帖子召回）| user（用户召回）
    intent_type = Column(String, default="buddy")       # buddy/help/share/dating
    risk_flags = Column(Text, default="[]")             # JSON: string[] 风险标注

    # Phase 6 AI 精排新增字段
    suggested_opening = Column(Text, default="")        # AI 生成的开场白建议
    ai_refined = Column(Boolean, default=False)         # 是否已经过 AI 精排
    ai_refined_at = Column(BigInteger, nullable=True)   # AI 精排时间

    __table_args__ = (
        # 按用户查询索引
        Index("ix_avatar_matches_user_id", "user_id"),
        # 按状态查询索引
        Index("ix_avatar_matches_status", "status"),
        # 按目标用户查询索引（用户型匹配）
        Index("ix_avatar_matches_target_user", "target_user_id"),
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


class AvatarUsageStat(Base):
    """用户 App 使用习惯聚合表（按星期和小时聚合，不保存完整行为轨迹）"""
    __tablename__ = "avatar_usage_stats"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    weekday = Column(Integer, nullable=False)            # 0=周一 ... 6=周日（Asia/Shanghai）
    hour = Column(Integer, nullable=False)               # 0-23（Asia/Shanghai）
    open_count = Column(Integer, default=0)              # 该小时打开/回到前台次数
    active_ms = Column(BigInteger, default=0)            # 该小时累计活跃时长
    page_weights = Column(Text, default="{}")            # JSON: 页面访问权重
    last_seen_at = Column(BigInteger, default=0)         # 最近一次上报时间
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_avatar_usage_stats_user_weekday_hour", "user_id", "weekday", "hour", unique=True),
        Index("ix_avatar_usage_stats_user_seen", "user_id", "last_seen_at"),
    )


class AvatarSurfLog(Base):
    """分身冲浪执行日志，用于频率控制、调试和前端展示"""
    __tablename__ = "avatar_surf_logs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    trigger = Column(String, nullable=False)             # scheduler/post_publish/manual/profile_update
    status = Column(String, default="success")           # success/skipped/failed
    scanned_posts = Column(Integer, default=0)
    scanned_users = Column(Integer, default=0)
    generated_matches = Column(Integer, default=0)
    generated_actions = Column(Integer, default=0)
    skipped_reason = Column(String, default="")
    error_message = Column(Text, default="")
    started_at = Column(BigInteger, nullable=False)
    finished_at = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_avatar_surf_logs_user_time", "user_id", "started_at"),
        Index("ix_avatar_surf_logs_status", "status"),
    )

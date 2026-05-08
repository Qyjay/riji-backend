"""
AI 分身相关数据模型
- AvatarMemory: 分身记忆库
- AvatarStatus: 分身状态
- AvatarMatch: 分身推荐匹配
- AvatarProfile: 分身侧写
- AvatarUsageStat: App 使用习惯聚合
- AvatarSurfLog: 分身冲浪日志
- AvatarAtoaSession: Phase 8A Top-10 粗筛会话（候选池 + 排除列表）
- AvatarAtoaInteraction: Phase 8A AtoA 探针互动日志
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

    # Phase 8A AtoA 双向匹配字段
    their_score = Column(Integer, default=0)            # 对方视角给我的规则打分
    their_reasons = Column(Text, default="[]")          # JSON: string[]，对方视角的匹配理由
    is_mutual = Column(Boolean, default=False)          # 是否双向达标
    peer_match_id = Column(String, nullable=True)       # 对方那条 AvatarMatch 的 ID（atoa 型互相关联）
    target_avatar_card_id = Column(String, nullable=True)  # 匹配时使用的对方名片 ID 快照

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
    # Phase 8A AtoA 统计字段
    scanned_atoa_pairs = Column(Integer, default=0)     # 本次冲浪进入 AtoA 探针的候选对数
    upgraded_to_mutual = Column(Integer, default=0)     # 本次升级为 mutual 的对数
    surf_report = Column(Text, default="")              # Agent 汇报摘要文案（自然语言）

    # Phase 8A: Top-10 会话关联
    top10_session_id = Column(String, nullable=True)         # 本次冲浪创建的 AtoaSession.id

    __table_args__ = (
        Index("ix_avatar_surf_logs_user_time", "user_id", "started_at"),
        Index("ix_avatar_surf_logs_status", "status"),
    )


class AvatarAtoaSession(Base):
    """Phase 8A: Top-10 搭子模式候选池会话。
    每次冲浪触发 Top-10 粗筛后写一条记录，记录候选 ID 列表、排除列表和评分快照。
    打断时从排除列表外的候选中自动补位。
    """
    __tablename__ = "avatar_atoa_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    candidate_ids = Column(Text, default="[]")
    # JSON: string[]，本次粗筛 Top-10 候选用户 ID（按评分降序排列）

    excluded_ids = Column(Text, default="[]")
    # JSON: string[]，用户已打断或已结交申请的候选 ID，补位时不再出现

    score_snapshot = Column(Text, default="{}")
    # JSON: {user_id: score}，粗筛时各候选的规则评分快照（含第11+位，用于补位）

    status = Column(String, default="active")
    # active     — 会话进行中，仍有候选未决策
    # completed  — 所有候选已决策，可开启新一轮
    # superseded — 被新的冲浪会话取代

    surf_log_id = Column(String, nullable=True)   # 关联的 AvatarSurfLog.id

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_atoa_sessions_user", "user_id", "created_at"),
        Index("ix_atoa_sessions_user_status", "user_id", "status"),
    )


class AvatarAtoaInteraction(Base):
    """Phase 8A: AtoA 探针互动日志，记录每一次两个分身互查的完整过程。"""
    __tablename__ = "avatar_atoa_interactions"

    id = Column(String, primary_key=True, default=_uuid)
    initiator_id = Column(String, ForeignKey("users.id"), nullable=False)
    # 触发本次探针的冲浪用户（谁的冲浪任务写了这条记录）

    session_id = Column(String, ForeignKey("avatar_atoa_sessions.id"), nullable=True)
    # 所属的 AtoaSession（Top-10 粗筛会话），用于进度追踪和补位逻辑

    user_a_id = Column(String, ForeignKey("users.id"), nullable=False)
    user_b_id = Column(String, ForeignKey("users.id"), nullable=False)
    # user_a 始终是 initiator（当前用户），user_b 是候选搭子

    interaction_type = Column(String, default="card_exchange")

    outcome = Column(String, default="pending_user_decision")
    # pending_user_decision — 分身初次对话已生成，等待用户手动决策（初始值）
    # blocked              — 用户打断，双向降分，已从候选池排除
    # connected            — 用户发出结交申请，等待对方确认
    # connect_confirmed    — 对方已确认，社交闭环完成
    # connect_rejected     — 对方拒绝了结交申请

    score_a = Column(Integer, default=0)    # A 视角打 B 的分
    score_b = Column(Integer, default=0)    # B 视角打 A 的分（对方冲浪时补填）

    shared_topics = Column(Text, default="[]")  # JSON: string[]，双方名片重合词

    reasons_a = Column(Text, default="[]")  # JSON: string[]，A 视角的匹配理由
    reasons_b = Column(Text, default="[]")  # JSON: string[]，B 视角的匹配理由

    risk_flags = Column(Text, default="[]") # JSON: string[]，探针发现的风险

    conversation = Column(Text, default="[]")
    # JSON: [{role: "avatar_a"|"avatar_b", content: "..."}]
    # 两个分身的模拟对话内容（AI 生成）

    triggered_match_id = Column(String, nullable=True)  # outcome=connected 时为 social.Match.id（供 respond 后同步终态）

    is_visible_to_a = Column(Boolean, default=True)     # A 在「分身动态」可见
    is_visible_to_b = Column(Boolean, default=False)    # B 默认不可见，mutual 后开放

    interaction_phase = Column(Integer, default=1)
    # 当前是第几轮组（每组 ≤3 轮，用户选「继续聊」后 +1）

    user_decision = Column(String, nullable=True)
    # 用户最近一次操作：continue / block / connect

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_atoa_interactions_initiator", "initiator_id", "created_at"),
        Index("ix_atoa_interactions_pair", "user_a_id", "user_b_id"),
        Index("ix_atoa_interactions_outcome", "outcome"),
        Index("ix_atoa_interactions_session", "session_id"),
    )

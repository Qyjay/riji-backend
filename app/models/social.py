"""
社交相关数据模型
- Match: 搭子匹配记录
- SocialMessage: 搭子聊天消息
- SocialMission: 用户发起的短期/长期找人任务
- MissionCandidate: 找人任务召回的帖子或用户候选
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String, Text

from app.database import Base


def _uuid() -> str:
    return str(uuid4())


class SocialMission(Base):
    """用户可控制、可暂停的找人任务。"""

    __tablename__ = "social_missions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    mode = Column(String, nullable=False)  # short_term / long_term
    purpose_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    source = Column(String, default="guided_form")
    status = Column(String, default="draft")

    time_window = Column(Text, default="{}")
    location = Column(Text, default="{}")
    headcount = Column(Text, default="{}")
    budget = Column(Text, default="{}")
    must_haves = Column(Text, default="[]")
    preferences = Column(Text, default="[]")
    boundaries = Column(Text, default="[]")
    public_memory_ids = Column(Text, default="[]")
    public_card_snapshot = Column(Text, default="{}")
    permissions = Column(Text, default="{}")

    search_strategy = Column(String, default="search_then_draft")
    linked_post_id = Column(String, nullable=True)
    atoa_session_id = Column(String, ForeignKey("avatar_atoa_sessions.id"), nullable=True)
    candidate_count = Column(Integer, default=0)
    pending_count = Column(Integer, default=0)
    expires_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_social_missions_user_status", "user_id", "status"),
        Index("ix_social_missions_user_time", "user_id", "created_at"),
    )


class MissionCandidate(Base):
    """某个找人任务下的帖子或用户候选。"""

    __tablename__ = "mission_candidates"

    id = Column(String, primary_key=True, default=_uuid)
    mission_id = Column(String, ForeignKey("social_missions.id"), nullable=False)
    target_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    target_post_id = Column(String, ForeignKey("plaza_posts.id"), nullable=True)
    source = Column(String, nullable=False)  # plaza_post / public_card
    status = Column(String, default="discovered")
    hard_constraint_result = Column(Text, default="{}")
    fit_reasons = Column(Text, default="[]")
    questions = Column(Text, default="[]")
    conflicts = Column(Text, default="[]")
    risk_flags = Column(Text, default="[]")
    internal_score = Column(Integer, default=0)
    interaction_id = Column(String, ForeignKey("avatar_atoa_interactions.id"), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_mission_candidates_mission_score", "mission_id", "internal_score"),
        Index("ix_mission_candidates_mission_status", "mission_id", "status"),
    )


class Match(Base):
    """搭子匹配表"""
    __tablename__ = "matches"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    target_id = Column(String, ForeignKey("users.id"), nullable=False)
    common_tags = Column(Text, default="[]")    # JSON array: 共同标签
    status = Column(String, default="pending")  # pending / accepted / rejected
    created_at = Column(BigInteger, nullable=False)

    # v2 新增字段
    match_type = Column(String, default="long_term")        # "long_term" | "buddy"
    match_report = Column(Text, default="")                 # AI 匹配报告文本
    user_portrait_snapshot = Column(Text, default="{}")     # JSON: 匹配时的用户画像快照
    mission_id = Column(String, ForeignKey("social_missions.id"), nullable=True)


class SocialMessage(Base):
    """搭子聊天消息表"""
    __tablename__ = "social_messages"

    id = Column(String, primary_key=True)
    match_id = Column(String, ForeignKey("matches.id"), nullable=False)
    from_uid = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False)

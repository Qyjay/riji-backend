"""
社交模块 Pydantic Schema
恢复之前版本中的代码
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from app.serializers import CamelModel


class MatchRequestBody(BaseModel):
    """发送匹配请求体"""
    toUid: Optional[str] = None


class SendMessageBody(BaseModel):
    """发送社交消息"""
    content: str



class RespondRequest(BaseModel):
    """响应匹配/搭子申请"""
    accept: bool


class BuddyRequest(BaseModel):
    """申请搭子"""
    target_user_id: str
    reason: str = ""


class MatchOut(CamelModel):
    """匹配列表项（含用户信息）"""
    id: str
    nickname: str
    avatar: str
    school: str
    common_tags: List[str]
    matched_at: int
    status: str = "accepted"
    match_type: str = "long_term"
    request_direction: str = "outgoing"
    reason: str = ""


class MatchRequestOut(CamelModel):
    """匹配请求响应"""
    id: str
    from_uid: str
    to_uid: str
    status: str
    created_at: int


class MessageOut(CamelModel):
    """消息响应"""
    id: str
    match_id: str
    from_uid: str
    content: str
    timestamp: int


class MatchReportOut(CamelModel):
    """匹配报告响应"""
    compatibility: int
    analysis: str
    common_points: List[str]
    differences: List[str]


class BuddyRequestOut(CamelModel):
    """搭子申请响应"""
    id: str
    from_uid: str
    to_uid: str
    reason: str
    status: str
    created_at: int


# ==================== 找人任务 ====================

class ParseMissionRequest(BaseModel):
    text: str


class CreateMissionRequest(BaseModel):
    mode: str
    purpose_type: str
    title: str
    description: str = ""
    source: str = "guided_form"
    time_window: dict = Field(default_factory=dict)
    location: dict = Field(default_factory=dict)
    headcount: dict = Field(default_factory=dict)
    budget: dict = Field(default_factory=dict)
    must_haves: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    public_memory_ids: list[str] = Field(default_factory=list)
    permissions: dict = Field(default_factory=dict)
    search_strategy: str = "search_then_draft"
    expires_at: Optional[int] = None


class UpdateMissionRequest(BaseModel):
    purpose_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    time_window: Optional[dict] = None
    location: Optional[dict] = None
    headcount: Optional[dict] = None
    budget: Optional[dict] = None
    must_haves: Optional[list[str]] = None
    preferences: Optional[list[str]] = None
    boundaries: Optional[list[str]] = None
    public_memory_ids: Optional[list[str]] = None
    permissions: Optional[dict] = None
    search_strategy: Optional[str] = None
    expires_at: Optional[int] = None


class MissionOut(CamelModel):
    id: str
    mode: str
    purpose_type: str
    title: str
    description: str
    source: str
    status: str
    time_window: dict
    location: dict
    headcount: dict
    budget: dict
    must_haves: list[str]
    preferences: list[str]
    boundaries: list[str]
    public_memory_ids: list[str]
    public_card_snapshot: dict
    permissions: dict
    search_strategy: str
    linked_post_id: Optional[str] = None
    atoa_session_id: Optional[str] = None
    candidate_count: int = 0
    pending_count: int = 0
    expires_at: Optional[int] = None
    created_at: int
    updated_at: int


class MissionParseOut(CamelModel):
    draft: dict
    inferred_fields: list[str]
    questions: list[str]


class MissionCandidateOut(CamelModel):
    id: str
    mission_id: str
    target_user_id: Optional[str] = None
    target_post_id: Optional[str] = None
    source: str
    status: str
    hard_constraint_result: dict
    fit_reasons: list[dict]
    questions: list[str]
    conflicts: list[dict]
    risk_flags: list[str]
    internal_score: int
    interaction_id: Optional[str] = None
    target_user: Optional[dict] = None
    target_post: Optional[dict] = None
    created_at: int
    updated_at: int


class MissionSearchOut(CamelModel):
    mission: MissionOut
    candidates: list[MissionCandidateOut]
    scanned_count: int
    matched_count: int
    suggestion: str


class MissionProbeOut(CamelModel):
    candidate: MissionCandidateOut
    interaction_id: str
    session_id: str


class MissionPostDraftOut(CamelModel):
    type: str
    content: str
    location: str
    tags: list[str]
    allow_agent_reply: bool
    school_only: bool


class PublishMissionPostRequest(BaseModel):
    content: str
    location: str = ""
    tags: list[str] = Field(default_factory=list)
    allow_agent_reply: bool = True
    school_only: bool = False


# ==================== 活动房间 ====================

class ActivityParticipantOut(CamelModel):
    id: str
    name: str
    avatar: str
    school: str
    is_organizer: bool


class ActivityRoomOut(CamelModel):
    match_id: str
    mission_id: str
    title: str
    status: str
    time_window: dict
    location: dict
    budget: dict
    linked_post_id: Optional[str] = None
    participants: list[ActivityParticipantOut]
    created_at: int
    completed_at: Optional[int] = None

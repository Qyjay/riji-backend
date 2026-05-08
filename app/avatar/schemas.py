"""
AI 分身模块 schemas
定义请求/响应的 Pydantic 模型（记忆/状态/推荐/侧写）
"""
from typing import Optional

from pydantic import BaseModel

from app.serializers import CamelModel


# ==================== 请求 Schema ====================

class AddMemoryRequest(BaseModel):
    """添加记忆请求"""
    category: str                       # fact/interest/personality/need/habit/relation
    content: str                        # 记忆内容


class UpdateMemoryRequest(BaseModel):
    """更新记忆请求（所有字段可选）"""
    content: Optional[str] = None
    is_active: Optional[bool] = None
    is_pinned: Optional[bool] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None


class UpdateStatusRequest(BaseModel):
    """更新分身状态请求（所有字段可选）"""
    is_active: Optional[bool] = None
    enabled_channels: Optional[list[str]] = None
    enabled_actions: Optional[list[str]] = None
    match_range: Optional[dict] = None
    surf_frequency: Optional[str] = None
    surf_window: Optional[dict] = None
    quiet_mode: Optional[bool] = None
    auto_match_enabled: Optional[bool] = None
    auto_comment_enabled: Optional[bool] = None
    auto_publish_enabled: Optional[bool] = None


class CreateAgentCommentDraftRequest(BaseModel):
    """创建广场分身评论草稿"""
    post_id: str
    parent_comment_id: Optional[str] = None


class AutoSurfRequest(BaseModel):
    """触发一次分身自动冲浪评论"""
    limit: Optional[int] = 1


class RecordUsageEventRequest(BaseModel):
    """记录 App 使用事件，用于学习用户个性化冲浪时间"""
    event_type: str                      # app_open/app_resume/app_close/active_ping/page_view
    timestamp: Optional[int] = None       # 毫秒时间戳，不传用服务端时间
    active_ms: Optional[int] = 0          # 本次活跃时长，用于 active_ping/app_close
    page: Optional[str] = ""              # 当前页面，如 plaza/diary/chat/avatar


# ==================== 响应 Schema ====================

# Phase 8A ──────────────────────────────────────────────────────────────────

class AtoaConversationTurn(BaseModel):
    """AtoA 对话轮次"""
    role: str       # avatar_a / avatar_b
    content: str


class ProbeLogItemOut(CamelModel):
    """GET /api/avatar/probe-log 单条记录"""
    id: str
    session_id: Optional[str] = None
    user_b_id: str
    user_b_name: str
    user_b_avatar: str
    interaction_type: str
    outcome: str
    # pending_user_decision / blocked / connected / connect_confirmed / connect_rejected
    readable_outcome: str                   # 中文可读文案
    score_a: int
    score_b: int
    shared_topics: list[str]
    reasons_a: list[str]
    conversation: list[AtoaConversationTurn]
    risk_flags: list[str]
    interaction_phase: int = 1
    user_decision: Optional[str] = None    # continue / block / connect
    is_mutual: bool
    triggered_match_id: Optional[str] = None  # connected 后为 social.Match.id
    created_at: int
    updated_at: int


class AtoaSessionOut(CamelModel):
    """GET /api/avatar/atoa/sessions 单条 AtoaSession 摘要"""
    id: str
    status: str                     # active / completed / superseded
    candidate_count: int            # Top-10 候选数
    excluded_count: int             # 已排除（打断/结交）的候选数
    pending_count: int              # 待决策的候选数
    decided_count: int              # 已决策的候选数
    surf_log_id: Optional[str] = None
    created_at: int
    updated_at: int


class MutualMatchItemOut(CamelModel):
    """GET /api/avatar/mutual-matches 单条记录"""
    id: str
    target_user_id: str
    target_user_name: str
    target_user_avatar: str
    target_user_school: str
    target_card_interests: list[str]
    target_card_intent: list[str]
    my_score: int
    their_score: int
    my_reasons: list[str]
    their_reasons: list[str]
    intent_type: str
    suggested_opening: str
    status: str
    peer_match_id: Optional[str] = None
    created_at: int


# Phase 8B ──────────────────────────────────────────────────────────────────

class ContinueAtoaChatResultOut(CamelModel):
    """POST /api/avatar/atoa/{id}/continue 响应"""
    id: str
    user_b_id: str
    user_b_name: str
    outcome: str
    interaction_phase: int
    new_turns: list[AtoaConversationTurn]
    conversation: list[AtoaConversationTurn]
    updated_at: int


# Phase 8C ──────────────────────────────────────────────────────────────────

class DecideAtoaRequest(BaseModel):
    """POST /api/avatar/atoa/{id}/decide 请求"""
    decision: str                             # "block" | "connect"
    opening_message: Optional[str] = None    # connect 时可选的开场白


class DecideAtoaResultOut(CamelModel):
    """POST /api/avatar/atoa/{id}/decide 响应"""
    outcome: str                              # "blocked" | "connected"
    social_match_id: Optional[str] = None    # connect 成功时

class AvatarMemoryOut(CamelModel):
    """记忆响应（camelCase 输出）"""
    id: str
    category: str
    content: str
    source: str
    source_ref: Optional[str] = None
    confidence: float
    created_at: int
    updated_at: int
    is_active: bool
    is_pinned: bool
    need_type: Optional[str] = None
    urgency: Optional[str] = None
    expiry: Optional[int] = None
    match_status: Optional[str] = None
    tags: Optional[list[str]] = None


class AvatarStatusOut(CamelModel):
    """分身状态响应（camelCase 输出）"""
    is_active: bool
    browsed_count: int
    matched_count: int
    chatting_count: int
    last_active_at: int
    enabled_channels: list[str]
    enabled_actions: list[str]
    match_range: dict
    surf_frequency: str
    surf_window: dict
    personalized_surf_plan: dict
    next_surf_at: int
    last_surf_at: int
    daily_surf_count: int
    daily_action_count: int
    quiet_mode: bool
    auto_match_enabled: bool
    auto_comment_enabled: bool
    auto_publish_enabled: bool


class AvatarProfileOut(CamelModel):
    """分身侧写响应（camelCase 输出）"""
    summary: str
    diary_count: int
    chat_count: int
    generated_at: int


class AvatarCardOut(CamelModel):
    """分身名片响应（用于匹配/agent-to-agent 的可控摘要）"""
    display_name: str
    public_summary: str
    interest_tags: list[str]
    social_intent: list[str]
    conversation_style: dict
    boundaries: list[str]
    visibility: str
    updated_at: int


class AgentActionOut(CamelModel):
    """分身行动响应"""
    id: str
    action_type: str
    target_type: str
    target_id: str
    input_context: dict
    output_text: str
    status: str
    created_at: int
    updated_at: int


class AutoSurfResultOut(CamelModel):
    """分身自动冲浪结果"""
    actions: list[AgentActionOut]
    published_count: int
    draft_count: int
    skipped_reason: str = ""


class UsageEventOut(CamelModel):
    """使用事件记录结果"""
    recorded: bool
    personalized_surf_plan: dict
    next_surf_at: int
    recorded_at: int


class AvatarSurfLogOut(CamelModel):
    """分身冲浪日志响应"""
    id: str
    trigger: str
    status: str
    scanned_posts: int
    scanned_users: int
    generated_matches: int
    generated_actions: int
    skipped_reason: str
    error_message: str
    started_at: int
    finished_at: Optional[int] = None
    # Phase 8A AtoA 统计字段
    scanned_atoa_pairs: int = 0
    upgraded_to_mutual: int = 0
    surf_report: str = ""
    top10_session_id: Optional[str] = None


class SurfLogsOut(CamelModel):
    """分身冲浪日志列表"""
    items: list[AvatarSurfLogOut]
    total: int


class TriggerSurfResultOut(CamelModel):
    """POST /avatar/surf/trigger 响应"""
    status: str                         # success / skipped / failed
    generated_matches: int = 0
    atoa_scanned: int = 0
    atoa_mutual: int = 0
    surf_report: str = ""
    top10_session_id: Optional[str] = None
    skipped_reason: str = ""

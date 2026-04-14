"""
AI 分身模块 schemas
定义请求/响应的 Pydantic 模型（记忆/状态/推荐/侧写）
"""
from typing import Optional

from pydantic import BaseModel

from app.serializers import CamelModel
from app.plaza.schemas import PlazaPostOut


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


class MatchActionRequest(BaseModel):
    """分身匹配操作请求"""
    action: str                         # "dismiss" / "chat"


# ==================== 响应 Schema ====================

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


class AvatarMatchOut(CamelModel):
    """分身推荐匹配响应（camelCase 输出）"""
    id: str
    post_id: str
    post: PlazaPostOut                  # 嵌套完整帖子
    match_score: int
    match_reasons: list[str]
    agent_conversation: list[dict]
    status: str
    created_at: int


class AvatarProfileOut(CamelModel):
    """分身侧写响应（camelCase 输出）"""
    summary: str
    diary_count: int
    chat_count: int
    generated_at: int

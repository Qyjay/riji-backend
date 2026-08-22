"""
广场模块 schemas
定义请求/响应的 Pydantic 模型
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.serializers import CamelModel


# ==================== 请求 Schema ====================

class CreatePostRequest(BaseModel):
    """创建帖子请求"""
    type: str = ""                      # buddy / help / share / dating；留空或 auto 交给 AI 判定
    content: str                        # 正文
    images: list[str] = []              # 图片 URL 列表
    location: str = ""                  # 位置
    tags: list[str] = []                # 话题标签
    allow_agent_reply: bool = True      # 允许分身回复
    school_only: bool = False           # 仅本校可见
    opportunity_mode: Optional[str] = None
    category: Optional[str] = None
    start_at: Optional[int] = None
    end_at: Optional[int] = None
    apply_deadline: Optional[int] = None
    location_precision: str = "district"
    slots_total: Optional[int] = None
    slots_remaining: Optional[int] = None
    allow_waitlist: bool = False
    budget: dict = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    opportunity_status: str = "open"
    agent_probe_enabled: bool = True


class AddCommentRequest(BaseModel):
    """添加评论请求"""
    content: str                        # 评论内容
    is_agent: bool = False              # 是否分身回复
    parent_comment_id: Optional[str] = None  # 回复某条评论；为空表示回复帖子


class AgentCommentRequest(BaseModel):
    """分身评论请求"""
    parent_comment_id: Optional[str] = None  # 回复某条评论；为空表示回复帖子


# ==================== 响应 Schema ====================

class PlazaPostOut(CamelModel):
    """帖子响应（camelCase 输出）"""
    id: str
    author_id: str
    author_name: str
    author_avatar: str
    author_school: str
    author_major: str
    author_grade: str
    type: str
    content: str
    images: list[str]
    location: str
    tags: list[str]
    likes: int
    comments: int
    agent_responses: int
    created_at: int
    is_from_agent: bool
    allow_agent_reply: bool
    school_only: bool
    mission_id: Optional[str] = None
    opportunity_mode: Optional[str] = None
    category: Optional[str] = None
    start_at: Optional[int] = None
    end_at: Optional[int] = None
    apply_deadline: Optional[int] = None
    location_precision: str = "district"
    slots_total: Optional[int] = None
    slots_remaining: Optional[int] = None
    allow_waitlist: bool = False
    budget: dict = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    opportunity_status: str = "open"
    agent_probe_enabled: bool = True


class PlazaCommentOut(CamelModel):
    """评论响应（camelCase 输出）"""
    id: str
    post_id: str
    parent_comment_id: Optional[str] = None
    author_id: str
    author_name: str
    author_avatar: str
    content: str
    is_agent: bool
    created_at: int
    parent_author_name: Optional[str] = None
    parent_content: Optional[str] = None

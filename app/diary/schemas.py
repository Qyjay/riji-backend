"""
日记模块 schemas v2
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from app.serializers import CamelModel


class UpdateDiaryRequest(BaseModel):
    """更新日记请求（只允许更新 content）"""
    content: str


class GenerateDiaryRequest(BaseModel):
    """AI 生成日记请求"""
    date: str
    weather: Optional[str] = ""
    weather_periods: List[Dict[str, Any]] = Field(default_factory=list, alias="weatherPeriods")
    allow_fallback: bool = False


class DerivativeRequest(BaseModel):
    """生成衍生内容请求"""
    type: str = "share_card"    # "comic" | "novel" | "share_card"


class ShareRequest(BaseModel):
    """设置分享范围"""
    scope: str = "private"      # "private" | "friends" | "public"


class DiarySearchParams(BaseModel):
    """日记搜索参数（多条件组合，AND 关系）"""
    model_config = ConfigDict(populate_by_name=True)

    q: Optional[str] = None
    emotion: Optional[str] = None
    tag: Optional[str] = None
    weather: Optional[str] = None
    from_date: Optional[str] = Field(default=None, alias="from")
    to_date: Optional[str] = Field(default=None, alias="to")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class DiaryOut(CamelModel):
    """日记响应（camelCase 输出）"""
    id: str
    user_id: str
    title: str
    content: str
    date: str
    weather: str
    special_date: str
    ai_comment: str = ""
    emotion_summary: Dict[str, Any]
    material_ids: List[str]
    style: str
    edit_count: int
    max_edits: int
    status: str
    created_at: int
    updated_at: int
    # legacy 兼容字段
    emotion: Dict[str, Any]
    images: List[str]
    tags: List[str]
    location: str
    has_comic: bool
    has_bgm: bool
    image_understandings: List[str] = []


class DerivativeOut(CamelModel):
    """衍生内容响应（camelCase 输出）"""
    id: str
    diary_id: str
    type: str
    content: str
    media_url: str
    share_scope: str
    created_at: int


class DerivativeTaskOut(CamelModel):
    """异步衍生内容任务响应"""
    task_id: str
    diary_id: str
    type: str
    status: str
    derivative_id: Optional[str] = None
    error: str = ""
    created_at: int
    updated_at: int


class TodaySummaryOut(CamelModel):
    """今日概览响应"""
    date: str
    material_count: int
    materials: List[Dict[str, Any]]
    has_diary: bool
    diary_id: Optional[str] = None
    diary_status: Optional[str] = None
    greeting_user_name: str = "同学"
    diary_count: int = 0
    dominant_emotion: str = ""

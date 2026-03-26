"""
日记模块 schemas v2
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from app.serializers import CamelModel


class UpdateDiaryRequest(BaseModel):
    """更新日记请求（只允许更新 content）"""
    content: str


class GenerateDiaryRequest(BaseModel):
    """AI 生成日记请求"""
    date: str
    weather: Optional[str] = ""


class DerivativeRequest(BaseModel):
    """生成衍生内容请求"""
    type: str = "share_card"    # "comic" | "novel" | "share_card"


class ShareRequest(BaseModel):
    """设置分享范围"""
    scope: str = "private"      # "private" | "friends" | "public"


class DiaryOut(CamelModel):
    """日记响应（camelCase 输出）"""
    id: str
    user_id: str
    title: str
    content: str
    date: str
    weather: str
    special_date: str
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


class DerivativeOut(CamelModel):
    """衍生内容响应（camelCase 输出）"""
    id: str
    diary_id: str
    type: str
    content: str
    media_url: str
    share_scope: str
    created_at: int


class TodaySummaryOut(CamelModel):
    """今日概览响应"""
    date: str
    material_count: int
    materials: List[Dict[str, Any]]
    has_diary: bool
    diary_id: Optional[str] = None
    diary_status: Optional[str] = None

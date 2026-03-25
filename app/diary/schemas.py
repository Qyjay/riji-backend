"""
日记模块 schemas v2
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CreateDiaryRequest(BaseModel):
    """创建日记请求（手动创建，保留向后兼容）"""
    content: str
    images: Optional[List[str]] = []
    emotion: Optional[dict] = {}
    tags: Optional[List[str]] = []
    location: Optional[str] = ""
    weather: Optional[str] = ""
    style: Optional[str] = "日记式"


class UpdateDiaryRequest(BaseModel):
    """更新日记请求"""
    content: Optional[str] = None
    images: Optional[List[str]] = None
    emotion: Optional[dict] = None
    tags: Optional[List[str]] = None
    location: Optional[str] = None
    weather: Optional[str] = None
    title: Optional[str] = None


class GenerateDiaryRequest(BaseModel):
    """AI 生成日记请求"""
    date: str                   # "2026-03-25"
    weather: Optional[str] = ""


class DerivativeRequest(BaseModel):
    """生成衍生内容请求"""
    type: str = "share_card"    # "comic" | "novel" | "share_card"


class DiaryOut(BaseModel):
    """日记响应"""
    id: str
    user_id: str
    content: str
    title: str
    images: List[str]
    emotion: Dict[str, Any]
    tags: List[str]
    location: str
    weather: str
    style: str
    has_comic: bool
    has_bgm: bool
    comic_url: str
    bgm_url: str
    created_at: int
    updated_at: int
    special_date: str
    emotion_summary: Dict[str, Any]
    material_ids: List[str]
    edit_count: int
    max_edits: int
    status: str
    date: str

"""
纪念日模块 schemas
"""
from typing import Optional
from pydantic import BaseModel
from app.serializers import CamelModel


class AnniversaryCreate(BaseModel):
    """创建纪念日请求"""
    title: str
    date: str                           # 月-日，如 "03-25"
    year: Optional[int] = None
    source: Optional[str] = "manual"
    related_person: Optional[str] = ""
    diary_id: Optional[str] = None


class AnniversaryUpdate(BaseModel):
    """更新纪念日请求"""
    title: Optional[str] = None
    date: Optional[str] = None
    year: Optional[int] = None
    related_person: Optional[str] = None


class AnniversaryOut(CamelModel):
    """纪念日响应（camelCase 输出）"""
    id: str
    user_id: str
    title: str
    date: str
    year: Optional[int] = None
    source: str
    related_person: str
    diary_id: Optional[str] = None
    created_at: int

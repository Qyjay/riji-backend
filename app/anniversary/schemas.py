"""
纪念日模块 schemas
"""
from typing import Optional
from pydantic import BaseModel


class AnniversaryCreate(BaseModel):
    """创建纪念日请求"""
    title: str
    date: str                           # 月-日，如 "03-25"
    year: Optional[int] = None          # 发生年份
    related_person: Optional[str] = ""


class AnniversaryUpdate(BaseModel):
    """更新纪念日请求"""
    title: Optional[str] = None
    date: Optional[str] = None
    year: Optional[int] = None
    related_person: Optional[str] = None


class AnniversaryOut(BaseModel):
    """纪念日响应"""
    id: str
    user_id: str
    title: str
    date: str
    year: Optional[int]
    source: str
    related_person: str
    diary_id: Optional[str]
    created_at: int

"""
日记模块 Pydantic Schema（组员 B+C 根据需要扩展）
"""
from typing import List, Optional
from pydantic import BaseModel


class CreateDiaryRequest(BaseModel):
    """创建日记请求"""
    content: str
    images: Optional[List[str]] = []        # 图片 URL 列表
    emotion: Optional[dict] = {}            # {emoji, label, score}
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

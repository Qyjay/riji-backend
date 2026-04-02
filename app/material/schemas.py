"""
素材管理模块 schemas
定义请求/响应的 Pydantic 模型
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from app.serializers import CamelModel


# ==================== 请求 Schema ====================

class MaterialCreate(BaseModel):
    """创建素材请求"""
    type: str                           # "image" | "voice" | "text"
    content: str = ""
    media_url: str = ""
    thumbnail_url: str = ""
    location: Dict[str, Any] = {}
    emotion: Dict[str, Any] = {}
    tags: List[str] = []
    date: str = ""


class MaterialUpdate(BaseModel):
    """更新素材请求（所有字段可选）"""
    content: Optional[str] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    emotion: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class PolishRequest(BaseModel):
    """文字润色请求"""
    style: str = "文艺"    # "文艺" | "幽默" | "简洁" | "温暖"


# ==================== 响应 Schema ====================

class MaterialOut(CamelModel):
    """素材响应（camelCase 输出）"""
    id: str
    user_id: str
    type: str
    content: str
    media_url: str
    thumbnail_url: str
    location: Dict[str, Any]
    emotion: Dict[str, Any]
    tags: List[str]
    date: str
    created_at: int
    # chat 类型专属字段
    chat_session_id: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None

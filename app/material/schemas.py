"""
素材管理模块 schemas
定义请求/响应的 Pydantic 模型
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict
from app.serializers import CamelModel


POLISH_STYLES = ["文艺", "幽默", "简洁", "温暖"]


# ==================== 请求 Schema ====================

class MaterialCreate(BaseModel):
    """创建素材请求"""
    model_config = ConfigDict(populate_by_name=True)

    type: str                           # "image" | "voice" | "text"
    content: str = ""
    media_url: str = Field(default="", alias="mediaUrl")
    thumbnail_url: str = Field(default="", alias="thumbnailUrl")
    location: Dict[str, Any] = {}
    emotion: Dict[str, Any] = {}
    tags: List[str] = []
    date: str = ""                     # 可选：传 YYYY-MM-DD，入库时补齐为 YYYY-MM-DD HH:MM:SS


class MaterialUpdate(BaseModel):
    """更新素材请求（所有字段可选）"""
    model_config = ConfigDict(populate_by_name=True)

    content: Optional[str] = None
    media_url: Optional[str] = Field(default=None, alias="mediaUrl")
    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")
    location: Optional[Dict[str, Any]] = None
    emotion: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class PolishRequest(BaseModel):
    """文字润色请求"""
    style: str = POLISH_STYLES[0]


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
    date: str                           # YYYY-MM-DD HH:MM:SS
    created_at: int
    # chat 类型专属字段
    chat_session_id: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None

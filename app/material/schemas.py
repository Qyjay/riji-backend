"""
素材管理模块 schemas
定义请求/响应的 Pydantic 模型
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.serializers import CamelModel


POLISH_STYLES = ["文艺", "幽默", "简洁", "温暖"]


def _normalize_media_urls(value) -> List[str]:
    """兼容 string / list / {url} 输入，统一归一为 URL 数组。"""
    if value is None:
        return []

    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, dict):
        raw_items = [value.get("url")]
    elif isinstance(value, list):
        raw_items = value
    else:
        return []

    result: List[str] = []
    for item in raw_items:
        url = ""
        if isinstance(item, str):
            url = item.strip()
        elif isinstance(item, dict):
            url = str(item.get("url") or "").strip()

        if url and url not in result:
            result.append(url)

    return result


def _normalize_thumbnail_urls(value) -> List[str]:
    """缩略图字段与媒体字段保持同一归一化规则。"""
    return _normalize_media_urls(value)


# ==================== 请求 Schema ====================

class MaterialCreate(BaseModel):
    """创建素材请求"""
    model_config = ConfigDict(populate_by_name=True)

    type: str                           # "image" | "voice" | "text"
    content: str = ""
    media_url: List[str] = Field(default_factory=list, alias="mediaUrl")
    thumbnail_url: List[str] = Field(default_factory=list, alias="thumbnailUrl")
    location: Dict[str, Any] = {}
    emotion: Optional[Dict[str, Any]] = None
    tags: List[str] = []
    date: str = ""                     # 可选：传 YYYY-MM-DD，入库时补齐为 YYYY-MM-DD HH:MM:SS

    @field_validator("media_url", mode="before")
    @classmethod
    def normalize_media_url(cls, value):
        return _normalize_media_urls(value)

    @field_validator("thumbnail_url", mode="before")
    @classmethod
    def normalize_thumbnail_url(cls, value):
        return _normalize_thumbnail_urls(value)


class MaterialUpdate(BaseModel):
    """更新素材请求（所有字段可选）"""
    model_config = ConfigDict(populate_by_name=True)

    content: Optional[str] = None
    media_url: Optional[List[str]] = Field(default=None, alias="mediaUrl")
    thumbnail_url: Optional[List[str]] = Field(default=None, alias="thumbnailUrl")
    location: Optional[Dict[str, Any]] = None
    emotion: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None

    @field_validator("media_url", mode="before")
    @classmethod
    def normalize_media_url(cls, value):
        if value is None:
            return None
        return _normalize_media_urls(value)

    @field_validator("thumbnail_url", mode="before")
    @classmethod
    def normalize_thumbnail_url(cls, value):
        if value is None:
            return None
        return _normalize_thumbnail_urls(value)


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
    media_url: List[str]
    thumbnail_url: List[str]
    location: Dict[str, Any]
    emotion: Optional[Dict[str, Any]] = None
    tags: List[str]
    date: str                           # YYYY-MM-DD HH:MM:SS
    created_at: int
    # chat 类型专属字段
    chat_session_id: Optional[str] = None
    start_time: Optional[int] = None
    end_time: Optional[int] = None

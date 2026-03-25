"""
素材管理模块 schemas
定义请求/响应的 Pydantic 模型
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ==================== 请求 Schema ====================

class MaterialCreate(BaseModel):
    """创建素材请求"""
    type: str                           # "image" | "voice" | "text"
    content: str = ""                  # 文字内容 / 语音转文字
    media_url: str = ""                # 图片/语音文件 URL
    thumbnail_url: str = ""            # 缩略图 URL
    location: Dict[str, Any] = {}      # {lat, lng, address}
    emotion: Dict[str, Any] = {}       # {label, score, emoji}
    tags: List[str] = []               # 标签列表
    date: str = ""                     # "2026-03-25"


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

class MaterialOut(BaseModel):
    """素材响应"""
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


class EmotionResult(BaseModel):
    """情绪提取结果"""
    label: str     # "开心" / "悲伤" / "平静" 等
    score: float   # 0.0 ~ 1.0 置信度
    emoji: str     # 对应 emoji


class PolishResult(BaseModel):
    """润色结果"""
    original: str   # 原始文字
    polished: str   # 润色后文字
    style: str      # 使用的风格

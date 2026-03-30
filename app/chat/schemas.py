"""
聊天模块 Pydantic Schema
"""
from pydantic import BaseModel

from app.serializers import CamelModel


class ChatRequest(BaseModel):
    """AI 对话请求体"""
    message: str


class ChatMessageOut(CamelModel):
    """聊天消息响应项"""
    role: str
    content: str
    timestamp: int


class ChatHistoryOut(CamelModel):
    """聊天历史响应"""
    items: list[ChatMessageOut]
    total: int

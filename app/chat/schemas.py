"""
对话模块 schemas
"""
from typing import List, Optional

from pydantic import BaseModel
from app.serializers import CamelModel


class ChatRequest(BaseModel):
    message: str


class CloseSessionOut(CamelModel):
    """关闭对话段响应"""
    session_closed: bool
    material_generated: bool
    material_id: Optional[str] = None


class ChatSessionOut(CamelModel):
    """对话段信息"""
    id: str
    title: str
    summary: str
    start_time: int
    end_time: Optional[int] = None
    message_count: int
    mood: str
    mood_emoji: str


class ChatMessageOut(CamelModel):
    """对话消息"""
    role: str
    content: str
    timestamp: int


class SessionMessagesOut(CamelModel):
    """对话段消息列表"""
    session: ChatSessionOut
    messages: List[ChatMessageOut]


class ChatHistoryOut(CamelModel):
    """聊天历史响应"""
    items: List[dict]
    total: int

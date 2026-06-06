"""
对话模块 schemas
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.serializers import CamelModel


class ChatAttachmentIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str
    name: str
    url: str
    mime_type: Optional[str] = Field(default=None, alias="mimeType")
    size: Optional[int] = None
    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")


class ChatAttachmentOut(CamelModel):
    type: str
    name: str
    url: str
    mime_type: Optional[str] = None
    size: Optional[int] = None
    thumbnail_url: Optional[str] = None
    snippet: Optional[str] = None
    domain: Optional[str] = None
    published_at: Optional[str] = None
    source: Optional[str] = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str = ""
    client_message_id: Optional[str] = Field(default=None, alias="clientMessageId")
    use_web_search: bool = Field(default=False, alias="useWebSearch")
    attachments: List[ChatAttachmentIn] = Field(default_factory=list)
    session_id: Optional[str] = Field(default=None, alias="sessionId")
    model_id: Optional[str] = Field(default=None, alias="modelId")

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value):
        return (value or "").strip()

    @model_validator(mode="after")
    def validate_payload(self):
        if not self.message and not self.attachments:
            raise ValueError("message 与 attachments 至少需要一项")
        return self


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
    status: str = "open"
    date: str = ""
    topic_tags: List[str] = Field(default_factory=list)
    material_id: Optional[str] = None


class SessionListOut(CamelModel):
    """对话段列表响应"""
    items: List[ChatSessionOut]
    total: int
    page: int
    page_size: int


class CreateSessionOut(CamelModel):
    """新建对话段响应"""
    session: ChatSessionOut
    old_session_closed: bool
    material_generated: bool
    material_id: Optional[str] = None


class ChatMessageOut(CamelModel):
    """对话消息"""
    id: str
    session_id: Optional[str] = None
    client_message_id: Optional[str] = None
    role: str
    content: str
    timestamp: int
    attachments: List[ChatAttachmentOut] = Field(default_factory=list)


class SessionMessageOut(CamelModel):
    """对话段消息（契约简版）"""
    role: str
    content: str
    timestamp: int


class SessionMessagesOut(CamelModel):
    """对话段消息列表"""
    session: ChatSessionOut
    messages: List[SessionMessageOut]


class ChatHistoryOut(CamelModel):
    """聊天历史响应"""
    items: List[ChatMessageOut]
    total: int

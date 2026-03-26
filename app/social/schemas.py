"""
社交模块 Pydantic Schema
"""
from typing import List, Optional
from pydantic import BaseModel
from app.serializers import CamelModel


class MatchRequestBody(BaseModel):
    """发送匹配请求体"""
    toUid: Optional[str] = None


class RespondRequest(BaseModel):
    """响应匹配/搭子申请"""
    accept: bool


class BuddyRequest(BaseModel):
    """申请搭子"""
    target_user_id: str
    reason: str = ""


class MatchOut(CamelModel):
    """匹配列表项（含用户信息）"""
    id: str
    nickname: str
    avatar: str
    school: str
    common_tags: List[str]
    matched_at: int


class MatchRequestOut(CamelModel):
    """匹配请求响应"""
    id: str
    from_uid: str
    to_uid: str
    status: str
    created_at: int


class MessageOut(CamelModel):
    """消息响应"""
    id: str
    match_id: str
    from_uid: str
    content: str
    timestamp: int


class MatchReportOut(CamelModel):
    """匹配报告响应"""
    compatibility: int
    analysis: str
    common_points: List[str]
    differences: List[str]


class BuddyRequestOut(CamelModel):
    """搭子申请响应"""
    id: str
    from_uid: str
    to_uid: str
    reason: str
    status: str
    created_at: int

"""
社交模块 Pydantic Schema（组员 D 根据需要扩展）
"""
from typing import List, Optional
from pydantic import BaseModel


class MatchRequest(BaseModel):
    """发起匹配请求"""
    target_id: str
    common_tags: Optional[List[str]] = []


class MatchActionRequest(BaseModel):
    """接受/拒绝匹配请求"""
    action: str  # 'accept' | 'reject'


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    match_id: str
    content: str

# app/chat/service.py
# 聊天历史业务逻辑
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def save_message(db: Session, user_id: str, role: str, content: str) -> ChatMessage:
    """保存一条聊天消息到数据库"""
    msg = ChatMessage(
        id=_uuid(),
        user_id=user_id,
        role=role,
        content=content,
        timestamp=_now_ms(),
    )
    db.add(msg)
    db.commit()
    return msg


def get_history(db: Session, user_id: str, limit: int = 50, before: int = 0) -> list:
    """获取 AI 聊天历史，支持时间游标分页"""
    query = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)
    if before > 0:
        query = query.filter(ChatMessage.timestamp < before)
    messages = query.order_by(ChatMessage.timestamp.desc()).limit(limit).all()
    return list(reversed(messages))

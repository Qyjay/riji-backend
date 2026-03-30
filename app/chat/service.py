"""
聊天模块服务层
"""
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.ai.minimax_client import get_minimax_client
from app.models.chat import ChatMessage

SYSTEM_PROMPT = "你是日迹 App 的 AI 伙伴，帮助用户记录生活、整理情绪、分析成长。请用温暖、友善的语气回复。"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _save_message(db: Session, user_id: str, role: str, content: str) -> ChatMessage:
    message = ChatMessage(
        id=_uuid(),
        user_id=user_id,
        role=role,
        content=content,
        timestamp=_now_ms(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _get_recent_context(db: Session, user_id: str, limit: int = 20) -> list[dict]:
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {"role": msg.role, "content": msg.content}
        for msg in reversed(history)
    ]


async def send_message(db: Session, user_id: str, message: str) -> str:
    """保存用户消息 + 调 AI + 保存回复 + 返回回复文本"""
    _save_message(db, user_id, "user", message)

    client = get_minimax_client()
    messages = _get_recent_context(db, user_id, limit=20)
    reply = await client.chat_completion(messages, system_prompt=SYSTEM_PROMPT)

    _save_message(db, user_id, "assistant", reply)
    return reply


def get_history(db: Session, user_id: str, limit: int = 20) -> dict:
    """获取聊天历史"""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "role": message.role,
            "content": message.content,
            "timestamp": message.timestamp,
        }
        for message in reversed(messages)
    ]
    return {"items": items, "total": len(items)}

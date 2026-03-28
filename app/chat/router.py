"""
聊天路由
- POST /chat          AI 对话（返回纯文本，非 SSE）
- GET  /chat/history  聊天历史
"""
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.chat import ChatMessage
from app.models.user import User
from app.response import success

router = APIRouter(prefix="/chat", tags=["AI 对话"])


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


class ChatRequest(BaseModel):
    message: str


@router.post("", summary="AI 对话（返回纯文本）")
async def ai_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AI 对话，返回纯文本字符串（前端用模拟打字机渲染）。
    同时保存对话历史。
    """
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    # 保存用户消息
    user_msg = ChatMessage(
        id=_uuid(),
        user_id=current_user.id,
        role="user",
        content=body.message,
        timestamp=_now_ms(),
    )
    db.add(user_msg)
    db.commit()

    # 构建历史消息（最近 20 条）
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(20)
        .all()
    )
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in reversed(history)
    ]

    # 调用 AI（一次性返回完整文本）
    system_prompt = "你是日迹 App 的 AI 伙伴，帮助用户记录生活、整理情绪、分析成长。请用温暖、友善的语气回复。"
    reply = await client.chat_completion(messages, system_prompt=system_prompt)

    # 保存 AI 回复
    ai_msg = ChatMessage(
        id=_uuid(),
        user_id=current_user.id,
        role="assistant",
        content=reply,
        timestamp=_now_ms(),
    )
    db.add(ai_msg)
    db.commit()

    return success(reply)


@router.get("/history", summary="聊天历史")
def get_chat_history(
    limit: int = Query(20, ge=1, le=100, description="获取条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取 AI 聊天历史"""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "role": m.role,
            "content": m.content,
            "timestamp": m.timestamp,
        }
        for m in reversed(messages)
    ]
    return success({"items": items, "total": len(items)})

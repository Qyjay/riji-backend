"""
聊天路由 v2
prefix="/api/chat", tags=["AI 对话"]
"""
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.chat import ChatMessage
from app.models.user import User
from app.response import ok

router = APIRouter(prefix="/chat", tags=["AI 对话"])


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


class ChatRequest(BaseModel):
    message: str
    system_prompt: str = ""


@router.post("", summary="AI 对话（SSE 流式）")
async def ai_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AI 流式对话（SSE EventSource 格式）
    - 保存用户消息 + AI 回复到 chat_messages 表
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

    # 构建历史消息
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

    assistant_content = []

    async def generate():
        async for chunk in client.stream_chat(messages, system_prompt=body.system_prompt):
            assistant_content.append(chunk)
            yield f"data: {chunk}\n\n"

        # 保存 AI 回复
        full_response = "".join(assistant_content)
        ai_msg = ChatMessage(
            id=_uuid(),
            user_id=current_user.id,
            role="assistant",
            content=full_response,
            timestamp=_now_ms(),
        )
        db.add(ai_msg)
        db.commit()
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/history", summary="聊天历史")
def get_chat_history(
    limit: int = Query(50, ge=1, le=100, description="获取条数"),
    before: int = Query(0, description="此时间戳之前的消息（0 表示最新）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取 AI 聊天历史，支持时间游标分页"""
    query = db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id)
    if before > 0:
        query = query.filter(ChatMessage.timestamp < before)
    messages = query.order_by(ChatMessage.timestamp.desc()).limit(limit).all()
    return ok({
        "items": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in reversed(messages)
        ],
        "total": len(messages),
    })

"""
聊天路由
- POST /chat          AI 对话（返回纯文本，非 SSE）
- GET  /chat/history  聊天历史
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.chat import service
from app.chat.schemas import ChatHistoryOut, ChatRequest
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success

router = APIRouter(prefix="/chat", tags=["AI 对话"])


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
    reply = await service.send_message(db, current_user.id, body.message)
    return success(reply)


@router.get("/history", summary="聊天历史")
def get_chat_history(
    limit: int = Query(20, ge=1, le=100, description="获取条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取 AI 聊天历史"""
    result = service.get_history(db, current_user.id, limit=limit)
    out = ChatHistoryOut(**result)
    return success(out.model_dump(by_alias=True))

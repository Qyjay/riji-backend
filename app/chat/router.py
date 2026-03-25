"""
聊天历史路由骨架
组员 D 负责实现
（注意：实际对话接口在 app/ai/router.py 的 /ai/chat）
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["聊天历史"])


@router.get("/history", summary="获取聊天历史")
def get_chat_history(
    limit: int = Query(50, ge=1, le=100, description="获取条数"),
    before: int = Query(0, description="此时间戳之前的消息（翻页用，0 表示最新）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现
    获取当前用户的 AI 对话历史
    1. 查询 chat_messages 表，按 timestamp DESC 排序
    2. 支持 before 参数翻页（时间游标分页）
    3. 返回消息列表（按时间正序排列）
    """
    pass


@router.delete("/history", summary="清空聊天历史")
def clear_chat_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现
    清空当前用户的所有 AI 对话历史
    """
    pass

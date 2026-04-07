"""
聊天路由
- POST /chat                          AI 对话（集成 session 管理）
- GET  /chat/history                  聊天历史
- POST /chat/close-session            主动关闭对话段
- GET  /chat/session/{id}/messages    获取对话段消息
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.chat import service
from app.chat.schemas import ChatHistoryOut, ChatRequest
from app.dependencies import get_current_user, get_db
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User, UserSettings
from app.response import success, ApiException, NOT_FOUND
from app.chat.schemas import (
    ChatRequest, CloseSessionOut, ChatSessionOut, ChatMessageOut, SessionMessagesOut,
)
from app.chat.service import get_or_create_session, close_and_materialize

router = APIRouter(prefix="/chat", tags=["AI 对话"])


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _get_settings(db: Session, user_id: str) -> UserSettings:
    """获取用户设置，不存在则返回默认对象"""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
    return settings


@router.post("", summary="AI 对话（返回纯文本）")
async def ai_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AI 对话，返回纯文本字符串（前端用模拟打字机渲染）。
    同时保存对话历史，集成 session 管理。
    """
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    now = _now_ms()
    settings = _get_settings(db, current_user.id)
    silence_threshold = getattr(settings, 'chat_silence_threshold', 30) or 30

    # Session 管理：获取或创建 session
    current_session, old_session = get_or_create_session(
        db, current_user.id, now, silence_threshold
    )

    # 如果有旧 session 需要封闭，先处理
    material_generated = False
    material_id = None
    if old_session:
        material = await close_and_materialize(db, old_session, settings)
        if material:
            material_generated = True
            material_id = material.id

    # 保存用户消息
    user_msg = ChatMessage(
        id=_uuid(),
        user_id=current_user.id,
        role="user",
        content=body.message,
        timestamp=now,
        session_id=current_session.id,
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
    ai_now = _now_ms()
    ai_msg = ChatMessage(
        id=_uuid(),
        user_id=current_user.id,
        role="assistant",
        content=reply,
        timestamp=ai_now,
        session_id=current_session.id,
    )
    db.add(ai_msg)

    # 更新 session 的 message_count 和 end_time
    current_session.message_count = (current_session.message_count or 0) + 2
    current_session.end_time = ai_now
    db.commit()

    # 构造响应
    result = {"code": 0, "data": reply, "message": "ok"}
    if material_generated:
        result["meta"] = {"materialGenerated": True, "materialId": material_id}
    return result


@router.post("/close-session", summary="主动关闭当前对话段")
async def close_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """用户离开聊天页时，前端主动调用此接口封闭当前 open 的 session。"""
    open_session = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id, ChatSession.status == "open")
        .first()
    )

    if not open_session:
        out = CloseSessionOut(
            session_closed=False, material_generated=False, material_id=None
        )
        return success(out.model_dump(by_alias=True))

    settings = _get_settings(db, current_user.id)
    material = await close_and_materialize(db, open_session, settings)

    out = CloseSessionOut(
        session_closed=True,
        material_generated=material is not None,
        material_id=material.id if material else None,
    )
    return success(out.model_dump(by_alias=True))


@router.get("/session/{session_id}/messages", summary="获取对话段消息")
def get_session_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """前端素材卡片「展开对话」时获取原始对话记录。"""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise ApiException(code=NOT_FOUND, message="对话段不存在", status_code=404)

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp)
        .all()
    )

    session_out = ChatSessionOut(
        id=session.id,
        title=session.title or "",
        summary=session.summary or "",
        start_time=session.start_time,
        end_time=session.end_time,
        message_count=session.message_count or 0,
        mood=session.mood or "",
        mood_emoji=session.mood_emoji or "",
    )
    messages_out = [
        ChatMessageOut(role=m.role, content=m.content, timestamp=m.timestamp)
        for m in messages
    ]
    out = SessionMessagesOut(session=session_out, messages=messages_out)
    return success(out.model_dump(by_alias=True))


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

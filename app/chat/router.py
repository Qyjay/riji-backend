"""
聊天路由
- POST /chat                         AI 对话（非流式）
- POST /chat/stream                  AI 对话（SSE 流式）
- GET  /chat/history                 聊天历史（近期消息扁平列表）
- GET  /chat/sessions                对话段列表（分页）
- POST /chat/sessions                新建对话段
- POST /chat/close-session           主动关闭当前对话段
- GET  /chat/session/{id}/messages   获取对话段消息
"""
import json
import logging
import traceback
from time import time
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.chat.schemas import (
    ChatMessageOut,
    ChatRequest,
    ChatSendOut,
    ChatSessionOut,
    CloseSessionOut,
    CreateSessionOut,
    SessionListOut,
    SessionMessagesOut,
)
from app.chat.service import (
    close_and_materialize,
    create_chat_message,
    create_new_session,
    get_history,
    get_or_create_session,
    get_session_for_message,
    list_session_messages,
    list_session_messages_for_ai,
    list_sessions,
    serialize_message,
    serialize_session,
)
from app.dependencies import get_current_user, get_db
from app.models.chat import ChatSession
from app.models.user import User, UserSettings
from app.response import ApiException, NOT_FOUND, success

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/chat", tags=["AI 对话"])

SYSTEM_PROMPT = "你是日迹 App 的 AI 伙伴，帮助用户记录生活、整理情绪、分析成长。请用温暖、友善的语气回复。"


def _now_ms() -> int:
    return int(time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _get_settings(db: Session, user_id: str) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        settings = UserSettings(user_id=user_id)
    return settings


async def _close_old_session_if_needed(
    db: Session,
    old_session: Optional[ChatSession],
    settings: UserSettings,
) -> tuple[bool, Optional[str]]:
    material_generated = False
    material_id = None
    if old_session:
        material = await close_and_materialize(db, old_session, settings)
        if material:
            material_generated = True
            material_id = material.id
    return material_generated, material_id


@router.post("", summary="AI 对话（返回完整消息）")
async def ai_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        from app.ai.minimax_client import get_minimax_client

        client = get_minimax_client()
        now = _now_ms()
        settings = _get_settings(db, current_user.id)
        silence_threshold = getattr(settings, "chat_silence_threshold", 30) or 30
        current_session, old_session = get_session_for_message(
            db, current_user.id, now, body.session_id, silence_threshold
        )
        if current_session is None:
            raise ApiException(code=NOT_FOUND, message="对话段不存在", status_code=404)
        material_generated, material_id = await _close_old_session_if_needed(db, old_session, settings)

        user_message = create_chat_message(
            db,
            user_id=current_user.id,
            role="user",
            content=body.message,
            timestamp=now,
            session_id=current_session.id,
            client_message_id=body.client_message_id,
            attachments=[item.model_dump(by_alias=False, exclude_none=True) for item in body.attachments],
        )
        current_session.message_count = (current_session.message_count or 0) + 1
        current_session.end_time = now
        db.commit()
        db.refresh(user_message)

        messages = list_session_messages_for_ai(db, current_session.id)
        reply = await client.chat_completion(messages, system_prompt=SYSTEM_PROMPT)

        ai_now = _now_ms()
        assistant_message = create_chat_message(
            db,
            user_id=current_user.id,
            role="assistant",
            content=reply,
            timestamp=ai_now,
            session_id=current_session.id,
        )
        current_session.message_count = (current_session.message_count or 0) + 1
        current_session.end_time = ai_now
        db.commit()
        db.refresh(assistant_message)

        out = ChatSendOut(
            session_id=current_session.id,
            user_message=ChatMessageOut(**serialize_message(user_message)),
            assistant_message=ChatMessageOut(**serialize_message(assistant_message)),
            material_generated=material_generated,
            material_id=material_id,
        )
        return success(out.model_dump(by_alias=True))
    except Exception as exc:
        logger.error("[chat] ai_chat failed: %s\n%s", str(exc), traceback.format_exc())
        raise


async def stream_response_generator(
    *,
    session_id: str,
    user_id: str,
    user_message_dict: dict,
    client_message_id: Optional[str],
):
    """SSE 流式生成器 — 自行管理 db session，避免 Depends(get_db) 生命周期冲突"""
    from app.ai.minimax_client import get_minimax_client
    from app.database import SessionLocal

    client = get_minimax_client()
    yield f"data: {json.dumps({'type': 'session', 'sessionId': session_id}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'ack', 'clientMessageId': client_message_id, 'message': user_message_dict}, ensure_ascii=False)}\n\n"

    db = SessionLocal()
    full_reply = ""
    try:
        messages = list_session_messages_for_ai(db, session_id)
        async for chunk in client.stream_chat(messages, system_prompt=SYSTEM_PROMPT):
            full_reply += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False)}\n\n"

        ai_now = _now_ms()
        assistant_message = create_chat_message(
            db,
            user_id=user_id,
            role="assistant",
            content=full_reply,
            timestamp=ai_now,
            session_id=session_id,
        )
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session:
            session.message_count = (session.message_count or 0) + 1
            session.end_time = ai_now
        db.commit()
        db.refresh(assistant_message)
        yield f"data: {json.dumps({'type': 'done', 'message': serialize_message(assistant_message)}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.error("[chat/stream] generator error: %s\n%s", str(exc), traceback.format_exc())
        db.rollback()
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
    finally:
        db.close()


@router.post("/stream", summary="AI 对话（流式 SSE）")
async def ai_chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _now_ms()
    settings = _get_settings(db, current_user.id)
    silence_threshold = getattr(settings, "chat_silence_threshold", 30) or 30
    current_session, old_session = get_session_for_message(
        db, current_user.id, now, body.session_id, silence_threshold
    )
    if current_session is None:
        raise ApiException(code=NOT_FOUND, message="对话段不存在", status_code=404)
    if old_session:
        await close_and_materialize(db, old_session, settings)

    user_message = create_chat_message(
        db,
        user_id=current_user.id,
        role="user",
        content=body.message,
        timestamp=now,
        session_id=current_session.id,
        client_message_id=body.client_message_id,
        attachments=[item.model_dump(by_alias=False, exclude_none=True) for item in body.attachments],
    )
    current_session.message_count = (current_session.message_count or 0) + 1
    current_session.end_time = now
    db.commit()
    db.refresh(user_message)

    # 在 Depends(get_db) session 关闭前，将 ORM 数据提取为纯 dict
    user_message_dict = serialize_message(user_message)
    session_id = current_session.id
    user_id = current_user.id
    client_message_id = body.client_message_id

    return StreamingResponse(
        stream_response_generator(
            session_id=session_id,
            user_id=user_id,
            user_message_dict=user_message_dict,
            client_message_id=client_message_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", summary="获取对话段列表（分页）")
def get_sessions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize", description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = list_sessions(db, current_user.id, page=page, page_size=page_size)
    out = SessionListOut(
        items=[ChatSessionOut(**item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )
    return success(out.model_dump(by_alias=True))


@router.post("/sessions", summary="新建对话段（强制开启新会话）")
async def new_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _now_ms()
    settings = _get_settings(db, current_user.id)
    new_sess, old_sess = create_new_session(db, current_user.id, now)
    material_generated = False
    material_id = None
    if old_sess:
        material = await close_and_materialize(db, old_sess, settings)
        if material:
            material_generated = True
            material_id = material.id
    db.refresh(new_sess)
    out = CreateSessionOut(
        session=ChatSessionOut(**serialize_session(new_sess)),
        old_session_closed=old_sess is not None,
        material_generated=material_generated,
        material_id=material_id,
    )
    return success(out.model_dump(by_alias=True))


@router.post("/close-session", summary="主动关闭当前对话段")
async def close_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    open_session = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id, ChatSession.status == "open")
        .first()
    )

    if not open_session:
        out = CloseSessionOut(
            session_closed=False,
            material_generated=False,
            material_id=None,
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
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise ApiException(code=NOT_FOUND, message="对话段不存在", status_code=404)

    messages = list_session_messages(db, session_id)
    session_out = ChatSessionOut(**serialize_session(session))
    out = SessionMessagesOut(
        session=session_out,
        messages=[ChatMessageOut(**serialize_message(message)) for message in messages],
    )
    return success(out.model_dump(by_alias=True))


@router.get("/history", summary="聊天历史")
def get_chat_history(
    limit: int = Query(20, ge=1, le=100, description="获取条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history = get_history(db, current_user.id, limit)
    total = history["total"]
    items = [
        ChatMessageOut(**message).model_dump(by_alias=True)
        for message in history["items"]
    ]
    if not items:
        welcome = ChatMessageOut(
            id=f"welcome-{current_user.id}",
            session_id=None,
            client_message_id=None,
            role="assistant",
            content=(
                f"嗨 {current_user.name or current_user.username}！我是日迹 AI 伙伴，很高兴见到你 😊\n\n"
                "你可以跟我聊聊今天发生的事情，或者让我帮你记录心情、整理思绪。\n"
                "有什么想说的，尽管告诉我吧！"
            ),
            timestamp=_now_ms(),
            attachments=[],
        ).model_dump(by_alias=True)
        items = [welcome]
        total = 1
    return success({"items": items, "total": total})

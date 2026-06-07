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
    ChatSessionOut,
    CloseSessionOut,
    CreateSessionOut,
    SessionListOut,
    SessionMessageOut,
    SessionMessagesOut,
)
from app.chat.service import (
    close_and_materialize,
    create_chat_message,
    create_new_session,
    get_history,
    get_session_for_message,
    ingest_session_memory_snapshot,
    list_session_messages,
    list_session_messages_for_ai,
    list_sessions,
    serialize_message,
    serialize_session,
)
from app.chat.ai_queue import acquire_chat_model_slot, get_chat_queue_status
from app.chat.web_search import search_web_for_chat
from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.chat import ChatSession
from app.models.user import User, UserSettings
from app.response import ApiException, NOT_FOUND, PARAM_ERROR, success

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/chat", tags=["AI 对话"])

SYSTEM_PROMPT = (
    "你是 Avalin 的 AI 伙伴，也是用户逐渐孵化出的专属数字分身。"
    "Avalin 主打零门槛生活记录与 AI 轻社交：用户可以通过拍照、文字或语音随手记录日常，"
    "AI 会把生活碎片整合成个性化多模态日记，并持续学习用户的性格、情绪、兴趣和表达方式。"
    "你的核心任务是贴近用户的真实自我，帮助用户记录生活、整理情绪、理解成长，"
    "也在合适时支持同频共鸣和真实世界社交。"
    "回复时要温暖、真诚、具体、克制，优先结合用户当前上下文与长期记忆；"
    "不要空泛说教，不要虚构用户没有提供或记忆中不存在的事实。"
)

CHAT_RAG_SOURCE_TYPES = [
    "diary",
    "material",
    "plaza_post",
    "plaza_comment",
    "social_message",
    "chat_session",
]


def _has_image_attachments(attachments) -> bool:
    return any(str(getattr(item, "type", "") or "").lower() == "image" for item in attachments or [])


def _skip_model_ids_for_request(*, has_image_attachments: bool) -> Optional[set[str]]:
    if not has_image_attachments:
        return None
    from app.ai.model_service import BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID

    return {BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID}


@router.get("/queue-status", summary="获取 AI 聊天队列状态")
async def chat_queue_status(
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return success(await get_chat_queue_status())


def _now_ms() -> int:
    return int(time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _build_system_prompt(
    web_context: str,
    *,
    web_search_requested: bool = False,
) -> str:
    if not web_context and not web_search_requested:
        return SYSTEM_PROMPT
    if web_search_requested and not web_context:
        return (
            f"{SYSTEM_PROMPT}\n\n"
            "用户已开启联网搜索。你本轮已执行联网检索，但未拿到有效结果。"
            "请直接说明“本轮未检索到可靠网页结果”，并基于已有知识给出尽可能有帮助的回答。"
            "不要说“我无法联网”或“我没有联网能力”。"
        )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "以下是用户当前问题对应的联网搜索结果，请优先基于这些内容回答，"
        "不要编造无法从搜索结果验证的信息；若信息不足，请明确说明。\n\n"
        "用户已开启联网搜索，你本轮已经获得联网检索结果。"
        "不要说“我无法联网”或“我没有联网能力”。\n\n"
        f"{web_context}"
    )


def _build_prompt_with_memory(
    db: Session,
    *,
    user_id: str,
    query: str,
    base_prompt: str,
    scenario: str = "chat",
) -> str:
    """按场景检索长期记忆并附加到 system prompt，失败时静默降级。"""
    if not getattr(settings, "MEMORY_ENABLED", True):
        return base_prompt
    try:
        from app.memory.prompts import append_memory_to_system_prompt, format_memory_context
        from app.memory.retriever import retrieve_memories

        memories = retrieve_memories(
            db,
            user_id=user_id,
            query=query,
            scenario=scenario,
            top_k=getattr(settings, "MEMORY_TOP_K", 6),
            source_types=CHAT_RAG_SOURCE_TYPES if scenario == "chat" else None,
        )
        memory_context = format_memory_context(memories, scenario=scenario)
        source_stats = {}
        for item in memories:
            source = str(item.get("source_type") or "unknown")
            source_stats[source] = source_stats.get(source, 0) + 1
        logger.info(
            "[chat] memory retrieved=%s scenario=%s sources=%s",
            len(memories),
            scenario,
            source_stats,
        )
        return append_memory_to_system_prompt(base_prompt, memory_context, scenario=scenario)
    except Exception as exc:
        logger.warning("[chat] memory retrieval skipped: %s", str(exc))
        return base_prompt


def _sanitize_web_capability_claim(reply: str, *, web_search_requested: bool) -> str:
    """
    开启联网搜索时，兜底修正模型错误话术，避免出现“无法联网/没有联网能力”。
    """
    if not web_search_requested:
        return reply
    text = str(reply or "")
    blocked_phrases = [
        "我无法联网",
        "我没法联网",
        "我不能联网",
        "我没有联网能力",
        "我没有联网搜索能力",
        "无法访问互联网",
        "无法联网搜索",
        "不能联网搜索",
        "无法实时获取",
    ]
    if not any(phrase in text for phrase in blocked_phrases):
        return text

    for phrase in blocked_phrases:
        text = text.replace(phrase, "本轮已尝试联网检索")

    if text.startswith("<think>"):
        return text
    return f"说明：本轮已尝试联网检索。\n\n{text}"


def _get_settings(db: Session, user_id: str) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        # 若用户还没有 settings 行，使用业务默认值构造临时对象，
        # 避免 SQLAlchemy 列默认值在未 flush 时为 None 造成逻辑误判。
        settings = UserSettings(
            user_id=user_id,
            theme="light",
            notifications=True,
            auto_bgm=False,
            diary_privacy="private",
            language="zh-CN",
            chat_material_enabled=True,
            chat_silence_threshold=30,
            chat_material_toast=True,
            chat_min_rounds=3,
            chat_model_id="",
        )
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


@router.post("", summary="AI 对话（返回文本）")
async def ai_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.message:
        raise ApiException(code=PARAM_ERROR, message="message 不能为空", status_code=400)

    try:
        from app.ai.model_service import resolve_chat_client

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

        web_attachments: list[dict] = []
        web_context = ""
        if body.use_web_search:
            web_attachments, web_context = await search_web_for_chat(body.message)
        logger.info(
            "[chat] web_search requested=%s results=%s context_len=%s",
            body.use_web_search,
            len(web_attachments),
            len(web_context),
        )

        messages = list_session_messages_for_ai(db, current_session.id)
        base_system_prompt = _build_system_prompt(
            web_context,
            web_search_requested=body.use_web_search,
        )
        system_prompt = _build_prompt_with_memory(
            db,
            user_id=current_user.id,
            query=body.message,
            base_prompt=base_system_prompt,
        )
        has_image_attachments = _has_image_attachments(body.attachments)
        lease = await acquire_chat_model_slot(
            skip_model_ids=_skip_model_ids_for_request(has_image_attachments=has_image_attachments)
        )
        async with lease as routed_model_id:
            client, resolved_model_id = resolve_chat_client(db, current_user.id, routed_model_id)
            logger.info(
                "[chat] auto routed model_id=%s has_image_attachments=%s",
                resolved_model_id,
                has_image_attachments,
            )
            reply = await client.chat_completion(
                messages,
                system_prompt=system_prompt,
            )
        reply = _sanitize_web_capability_claim(reply, web_search_requested=body.use_web_search)

        ai_now = _now_ms()
        assistant_message = create_chat_message(
            db,
            user_id=current_user.id,
            role="assistant",
            content=reply,
            timestamp=ai_now,
            session_id=current_session.id,
            attachments=web_attachments,
        )
        current_session.message_count = (current_session.message_count or 0) + 1
        current_session.end_time = ai_now
        db.commit()
        db.refresh(assistant_message)
        ingest_session_memory_snapshot(db, current_session.id)

        result = success(reply)
        if material_generated:
            result["meta"] = {
                "materialGenerated": True,
                "materialId": material_id,
            }
        return result
    except Exception as exc:
        logger.error("[chat] ai_chat failed: %s\n%s", str(exc), traceback.format_exc())
        raise


async def stream_response_generator(
    *,
    session_id: str,
    user_id: str,
    user_message_dict: dict,
    client_message_id: Optional[str],
    web_attachments: list[dict],
    web_context: str,
    web_search_requested: bool,
    memory_context: str,
    model_id: Optional[str],
    has_image_attachments: bool,
):
    """SSE 流式生成器 — 自行管理 db session，避免 Depends(get_db) 生命周期冲突"""
    from app.ai.model_service import resolve_chat_client
    from app.database import SessionLocal

    yield f"data: {json.dumps({'type': 'session', 'sessionId': session_id}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'ack', 'clientMessageId': client_message_id, 'message': user_message_dict}, ensure_ascii=False)}\n\n"

    db = SessionLocal()
    full_reply = ""
    try:
        if web_attachments:
            yield (
                f"data: {json.dumps({'type': 'web_search', 'results': web_attachments}, ensure_ascii=False)}\n\n"
            )

        messages = list_session_messages_for_ai(db, session_id)
        stream_system_prompt = _build_system_prompt(
            web_context,
            web_search_requested=web_search_requested,
        )
        if memory_context:
            from app.memory.prompts import append_memory_to_system_prompt

            stream_system_prompt = append_memory_to_system_prompt(
                stream_system_prompt,
                memory_context,
                scenario="chat",
            )

        try:
            lease = await acquire_chat_model_slot(
                skip_model_ids=_skip_model_ids_for_request(has_image_attachments=has_image_attachments)
            )
            async with lease as routed_model_id:
                client, resolved_model_id = resolve_chat_client(db, user_id, routed_model_id)
                logger.info(
                    "[chat/stream] auto routed model_id=%s has_image_attachments=%s",
                    resolved_model_id,
                    has_image_attachments,
                )
                async for chunk in client.stream_chat(
                    messages,
                    system_prompt=stream_system_prompt,
                ):
                    full_reply += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False)}\n\n"
        except Exception as stream_exc:
            logger.warning("[chat/stream] stream failed, fallback to non-stream: %s", str(stream_exc))
            lease = await acquire_chat_model_slot(
                skip_model_ids=_skip_model_ids_for_request(has_image_attachments=has_image_attachments)
            )
            async with lease as routed_model_id:
                client, resolved_model_id = resolve_chat_client(db, user_id, routed_model_id)
                logger.info(
                    "[chat/stream:fallback] auto routed model_id=%s has_image_attachments=%s",
                    resolved_model_id,
                    has_image_attachments,
                )
                fallback_reply = await client.chat_completion(
                    messages,
                    system_prompt=stream_system_prompt,
                )
                full_reply = fallback_reply
                if fallback_reply:
                    yield f"data: {json.dumps({'type': 'chunk', 'text': fallback_reply}, ensure_ascii=False)}\n\n"

        full_reply = _sanitize_web_capability_claim(
            full_reply,
            web_search_requested=web_search_requested,
        )

        ai_now = _now_ms()
        assistant_message = create_chat_message(
            db,
            user_id=user_id,
            role="assistant",
            content=full_reply,
            timestamp=ai_now,
            session_id=session_id,
            attachments=web_attachments,
        )
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session:
            session.message_count = (session.message_count or 0) + 1
            session.end_time = ai_now
        db.commit()
        db.refresh(assistant_message)
        ingest_session_memory_snapshot(db, session_id)
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

    web_attachments: list[dict] = []
    web_context = ""
    if body.use_web_search:
        web_attachments, web_context = await search_web_for_chat(body.message)
    logger.info(
        "[chat/stream] web_search requested=%s results=%s context_len=%s",
        body.use_web_search,
        len(web_attachments),
        len(web_context),
    )

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
    memory_context = ""
    if getattr(settings, "MEMORY_ENABLED", True):
        try:
            from app.memory.prompts import format_memory_context
            from app.memory.retriever import retrieve_memories

            memories = retrieve_memories(
                db,
                user_id=user_id,
                query=body.message,
                scenario="chat",
                top_k=getattr(settings, "MEMORY_TOP_K", 6),
                source_types=CHAT_RAG_SOURCE_TYPES,
            )
            memory_context = format_memory_context(memories, scenario="chat")
            source_stats = {}
            for item in memories:
                source = str(item.get("source_type") or "unknown")
                source_stats[source] = source_stats.get(source, 0) + 1
            logger.info("[chat/stream] memory retrieved=%s sources=%s", len(memories), source_stats)
        except Exception as exc:
            logger.warning("[chat/stream] memory retrieval skipped: %s", str(exc))

    return StreamingResponse(
        stream_response_generator(
            session_id=session_id,
            user_id=user_id,
            user_message_dict=user_message_dict,
            client_message_id=client_message_id,
            web_attachments=web_attachments,
            web_context=web_context,
            web_search_requested=body.use_web_search,
            memory_context=memory_context,
            model_id=body.model_id,
            has_image_attachments=_has_image_attachments(body.attachments),
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
    else:
        # old_sess 不存在时 close_and_materialize 不会触发提交，
        # 需要显式 commit，确保返回的 sessionId 在下一请求可查询。
        db.commit()
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
        messages=[
            SessionMessageOut(
                role=message.role,
                content=message.content,
                timestamp=message.timestamp,
            )
            for message in messages
        ],
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

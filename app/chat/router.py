"""
聊天路由 v2
prefix="/api/chat", tags=["AI 对话"]

三层降级策略：
1. OPENCLAW_ENABLED + token → OpenClaw Gateway SSE（带记忆）
2. OpenClaw 异常        → 降级直连 MiniMax
3. MINIMAX_MOCK=True    → Mock 模式
"""
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import ok
from app.chat import service as chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["AI 对话"])


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
    - 优先走 OpenClaw Gateway（带记忆）
    - OpenClaw 不可用时降级到直连 MiniMax
    - 保存用户消息 + AI 回复到 chat_messages 表
    """
    # 保存用户消息
    chat_service.save_message(db, current_user.id, "user", body.message)

    # 构建历史消息
    history = chat_service.get_history(db, current_user.id, limit=20)
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in history
    ]

    # 决策：是否走 OpenClaw
    use_openclaw = (
        settings.OPENCLAW_ENABLED
        and bool(settings.OPENCLAW_GATEWAY_TOKEN)
        and not settings.MINIMAX_MOCK
    )

    assistant_content = []

    async def generate():
        used_openclaw = False

        # ── 层 1：OpenClaw Gateway ─────────────────────────
        if use_openclaw:
            try:
                from app.openclaw.client import get_openclaw_client
                from app.openclaw.prompt_builder import build_chat_system_prompt

                system_prompt = body.system_prompt or build_chat_system_prompt(
                    current_user, db
                )
                client = get_openclaw_client()
                async for chunk in client.stream_chat(
                    messages=messages,
                    user_id=current_user.id,
                    system_prompt=system_prompt,
                ):
                    assistant_content.append(chunk)
                    yield f"data: {chunk}\n\n"
                used_openclaw = True
            except Exception as exc:
                logger.warning(
                    "OpenClaw 异常，降级到 MiniMax: %s", exc, exc_info=True
                )
                assistant_content.clear()

        # ── 层 2 / 层 3：MiniMax（直连 or Mock）──────────────
        if not used_openclaw:
            from app.ai.minimax_client import get_minimax_client

            minimax = get_minimax_client()
            async for chunk in minimax.stream_chat(
                messages, system_prompt=body.system_prompt
            ):
                assistant_content.append(chunk)
                yield f"data: {chunk}\n\n"

        # 保存 AI 回复
        full_response = "".join(assistant_content)
        chat_service.save_message(db, current_user.id, "assistant", full_response)
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
    messages = chat_service.get_history(db, current_user.id, limit=limit, before=before)
    return ok({
        "items": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in messages
        ],
        "total": len(messages),
    })

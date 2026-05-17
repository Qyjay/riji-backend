"""
WebSocket 流式聊天路由
- WebSocket /ws/chat    AI 对话（流式推送）
"""
import asyncio
import json
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User
from app.chat.service import get_or_create_session, close_and_materialize

router = APIRouter()


def _now_ms() -> int:
    import time as _time
    return int(_time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _get_user_from_token(token: str, db: Session) -> Optional[User]:
    """从 JWT token 中解析 user_id 并查询用户"""
    from app.auth.service import verify_token
    payload = verify_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


async def stream_chat_websocket(websocket: WebSocket, user: User, db: Session, message: str):
    """处理单次流式对话"""
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    now = _now_ms()
    silence_threshold = 30

    # 获取或创建 session
    current_session, old_session = get_or_create_session(
        db, user.id, now, silence_threshold
    )

    # 封闭旧 session
    if old_session:
        await close_and_materialize(db, old_session, None)

    # 保存用户消息
    user_msg_id = _uuid()
    from app.models.chat import ChatMessage
    user_msg = ChatMessage(
        id=user_msg_id,
        user_id=user.id,
        role="user",
        content=message,
        timestamp=now,
        session_id=current_session.id,
    )
    db.add(user_msg)

    # 构建历史消息
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(20)
        .all()
    )
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in reversed(history)
    ]
    db.commit()

    system_prompt = (
        "你是 Avalin 的 AI 伙伴，也是用户逐渐孵化出的专属数字分身。"
        "Avalin 主打零门槛生活记录与 AI 轻社交：用户可以通过拍照、文字或语音随手记录日常，"
        "AI 会把生活碎片整合成个性化多模态日记，并持续学习用户的性格、情绪、兴趣和表达方式。"
        "你的核心任务是贴近用户的真实自我，帮助用户记录生活、整理情绪、理解成长，"
        "也在合适时支持同频共鸣和真实世界社交。"
        "回复时要温暖、真诚、具体、克制，优先结合用户当前上下文与长期记忆；"
        "不要空泛说教，不要虚构用户没有提供或记忆中不存在的事实。"
    )

    full_reply = ""

    try:
        async for chunk in client.stream_chat(messages, system_prompt=system_prompt):
            full_reply += chunk
            # 通过 WebSocket 发送每个文本片段
            await websocket.send_text(json.dumps({
                "type": "chunk",
                "text": chunk,
            }))

        # 流结束，保存 AI 回复到数据库
        ai_now = _now_ms()
        ai_msg = ChatMessage(
            id=_uuid(),
            user_id=user.id,
            role="assistant",
            content=full_reply,
            timestamp=ai_now,
            session_id=current_session.id,
        )
        db.add(ai_msg)

        # 更新 session
        db.query(ChatMessage).filter(ChatMessage.session_id == current_session.id).first()
        from app.models.chat import ChatSession
        db.query(ChatSession).filter(ChatSession.id == current_session.id).update({
            "message_count": (ChatSession.message_count or 0) + 2,
            "end_time": ai_now,
        })
        db.commit()

        await websocket.send_text(json.dumps({"type": "done"}))

    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": str(e),
        }))


@router.websocket("/ws/chat")
async def chat_websocket(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket 流式聊天接口
    连接时传递 ?token=xxx，发送消息格式: {"message": "xxx"}
    """
    await websocket.accept()

    db = SessionLocal()
    try:
        user = _get_user_from_token(token, db)
        if not user:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "认证失败，请重新登录",
            }))
            await websocket.close(code=4001)
            return

        # 等待客户端发送消息
        try:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            payload = json.loads(data)
            message = payload.get("message", "")
            if not message:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "消息内容不能为空",
                }))
                return

            await stream_chat_websocket(websocket, user, db, message)

        except asyncio.TimeoutError:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "等待消息超时",
            }))
        except WebSocketDisconnect:
            pass
        except Exception as e:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": str(e),
            }))
    finally:
        db.close()

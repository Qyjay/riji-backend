"""
对话段管理服务层
- close_and_materialize: 封闭对话段并生成素材
- get_or_create_session: 获取或创建当前 open 的 session
"""
import json
import time
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession
from app.models.material import RawMaterial
from app.models.user import UserSettings


def _now_ms() -> int:
    return int(time.time() * 1000)

def _uuid() -> str:
    return str(uuid4())


async def close_and_materialize(
    db: Session,
    session: ChatSession,
    settings: UserSettings,
) -> Optional[RawMaterial]:
    """封闭对话段并生成素材。返回生成的素材，或 None（不满足条件）。"""

    # 1. 封闭 session
    session.status = "closed"
    session.end_time = session.end_time or _now_ms()

    # 2. 检查是否开启
    if not getattr(settings, 'chat_material_enabled', True):
        db.commit()
        return None

    # 3. 检查最小轮数（chat_min_rounds 指 user 消息数，message_count 是总数）
    min_rounds = getattr(settings, 'chat_min_rounds', 3)
    user_msg_count = session.message_count // 2  # user+assistant 各算一条
    if user_msg_count < min_rounds:
        db.commit()
        return None

    # 4. 获取该 session 的所有消息
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.timestamp)
        .all()
    )

    if not messages:
        db.commit()
        return None

    msg_list = [{"role": m.role, "content": m.content} for m in messages]

    # 5. 调用 AI 生成摘要
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    result = await client.summarize_chat_session(msg_list)

    # 6. 回填 session
    session.title = result.get("title", "对话记录")
    session.summary = result.get("summary", "")
    session.mood = result.get("mood", "平静")
    session.mood_emoji = result.get("mood_emoji", "😐")
    session.topic_tags = json.dumps(result.get("tags", []), ensure_ascii=False)

    # 7. 创建素材
    material = RawMaterial(
        id=_uuid(),
        user_id=session.user_id,
        type="chat",
        content=result.get("summary", ""),
        chat_session_id=session.id,
        start_time=session.start_time,
        end_time=session.end_time,
        emotion=json.dumps({
            "label": result.get("mood", "平静"),
            "score": 0.8,
            "emoji": result.get("mood_emoji", "😐"),
        }, ensure_ascii=False),
        tags=json.dumps(result.get("tags", []), ensure_ascii=False),
        date=session.date,
        created_at=session.start_time,
    )
    db.add(material)

    # 8. 回填 session.material_id
    session.material_id = material.id
    db.commit()

    return material


def get_or_create_session(
    db: Session,
    user_id: str,
    now_ms: int,
    silence_threshold_min: int = 30,
) -> tuple:
    """
    获取或创建当前 open 的 session。
    返回 (session, old_session_to_close_or_None)
    """
    from datetime import datetime

    open_session = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id, ChatSession.status == "open")
        .first()
    )

    if open_session:
        # 检查是否超过静默阈值
        last_time = open_session.end_time or open_session.start_time
        silence_ms = silence_threshold_min * 60 * 1000

        if (now_ms - last_time) > silence_ms:
            # 超时，需要封闭旧 session 并创建新的
            old_session = open_session
            today = datetime.fromtimestamp(now_ms / 1000).strftime("%Y-%m-%d")
            new_session = ChatSession(
                id=_uuid(),
                user_id=user_id,
                status="open",
                start_time=now_ms,
                end_time=now_ms,
                message_count=0,
                date=today,
                created_at=now_ms,
            )
            db.add(new_session)
            db.flush()
            return new_session, old_session
        else:
            # 未超时，复用
            return open_session, None
    else:
        # 无 open session，新建
        today = datetime.fromtimestamp(now_ms / 1000).strftime("%Y-%m-%d")
        new_session = ChatSession(
            id=_uuid(),
            user_id=user_id,
            status="open",
            start_time=now_ms,
            end_time=now_ms,
            message_count=0,
            date=today,
            created_at=now_ms,
        )
        db.add(new_session)
        db.flush()
        return new_session, None

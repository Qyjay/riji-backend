"""
对话段管理服务层
- close_and_materialize: 封闭对话段并生成素材
- get_or_create_session: 获取或创建当前 open 的 session
"""
import json
import time
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession
from app.models.material import RawMaterial
from app.models.user import UserSettings


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _is_same_day(material_date: str, target_date: str) -> bool:
    left = str(material_date or "").strip()
    right = str(target_date or "").strip()
    if not left or not right:
        return False
    return left == right or left.startswith(f"{right} ")


def _collect_existing_materials_for_dedup(
    db: Session,
    user_id: str,
    date: str,
    limit: int = 60,
) -> list[dict]:
    rows = (
        db.query(RawMaterial)
        .filter(RawMaterial.user_id == user_id)
        .order_by(RawMaterial.created_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    for row in rows:
        if not _is_same_day(row.date or "", date):
            continue
        content = str(row.content or "").strip()
        if not content:
            continue

        items.append(
            {
                "id": row.id,
                "type": row.type,
                "content": content,
                "created_at": row.created_at,
            }
        )
    return items


def encode_attachments(items: Optional[List[dict]]) -> str:
    return json.dumps(items or [], ensure_ascii=False)


def decode_attachments(raw: Optional[str]) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def serialize_message(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "client_message_id": message.client_message_id,
        "role": message.role,
        "content": message.content,
        "timestamp": message.timestamp,
        "attachments": decode_attachments(message.attachments),
    }


def _attachment_prompt_text(attachment: dict) -> str:
    att_type = str(attachment.get("type") or "file")
    name = str(attachment.get("name") or attachment.get("url") or "未命名附件")
    if att_type == "image":
        return f"[用户上传了图片：{name}]"
    if att_type == "voice":
        return f"[用户上传了语音：{name}]"
    return f"[用户上传了文件：{name}]"


def message_to_ai_payload(message: ChatMessage) -> dict:
    attachments = decode_attachments(message.attachments)
    parts = []
    if attachments:
        parts.append("\n".join(_attachment_prompt_text(item) for item in attachments))
    if message.content:
        parts.append(message.content.strip())
    return {
        "role": message.role,
        "content": "\n".join(part for part in parts if part).strip() or "[空消息]",
    }


def list_session_messages(db: Session, session_id: str) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp)
        .all()
    )


def list_session_messages_for_ai(db: Session, session_id: str) -> list[dict]:
    return [message_to_ai_payload(message) for message in list_session_messages(db, session_id)]


def create_chat_message(
    db: Session,
    *,
    user_id: str,
    role: str,
    content: str,
    timestamp: int,
    session_id: str,
    client_message_id: Optional[str] = None,
    attachments: Optional[list[dict]] = None,
) -> ChatMessage:
    message = ChatMessage(
        id=_uuid(),
        user_id=user_id,
        role=role,
        content=content,
        timestamp=timestamp,
        session_id=session_id,
        client_message_id=client_message_id,
        attachments=encode_attachments(attachments),
    )
    db.add(message)
    return message


async def close_and_materialize(
    db: Session,
    session: ChatSession,
    settings: UserSettings,
) -> Optional[RawMaterial]:
    """封闭对话段并生成素材。返回生成的素材，或 None（不满足条件）。"""
    session.status = "closed"
    session.end_time = session.end_time or _now_ms()

    messages = list_session_messages(db, session.id)
    session.message_count = len(messages)

    if not getattr(settings, "chat_material_enabled", True):
        db.commit()
        return None

    min_rounds = getattr(settings, "chat_min_rounds", 3)
    user_msg_count = sum(1 for message in messages if message.role == "user")
    if user_msg_count < min_rounds:
        db.commit()
        return None

    if not messages:
        db.commit()
        return None

    msg_list = [message_to_ai_payload(message) for message in messages]

    from app.ai.minimax_client import get_minimax_client

    client = get_minimax_client()
    result = await client.summarize_chat_session(msg_list)

    session.title = result.get("title", "对话记录")
    session.summary = result.get("summary", "")
    session.mood = result.get("mood", "平静")
    session.mood_emoji = result.get("mood_emoji", "😐")
    session.topic_tags = json.dumps(result.get("tags", []), ensure_ascii=False)

    existing_materials = _collect_existing_materials_for_dedup(
        db,
        user_id=session.user_id,
        date=session.date,
    )
    dedup_result = await client.detect_duplicate_chat_material(
        candidate_summary=session.summary,
        existing_materials=existing_materials,
    )

    if dedup_result.get("is_duplicate"):
        duplicate_id = dedup_result.get("duplicate_material_id")
        if duplicate_id:
            session.material_id = str(duplicate_id)
        db.commit()
        return None

    material = RawMaterial(
        id=_uuid(),
        user_id=session.user_id,
        type="chat",
        content=result.get("summary", ""),
        chat_session_id=session.id,
        start_time=session.start_time,
        end_time=session.end_time,
        emotion=json.dumps(
            {
                "label": result.get("mood", "平静"),
                "score": 0.8,
                "emoji": result.get("mood_emoji", "😐"),
            },
            ensure_ascii=False,
        ),
        tags=json.dumps(result.get("tags", []), ensure_ascii=False),
        date=session.date,
        created_at=session.start_time,
    )
    db.add(material)
    session.material_id = material.id
    db.commit()
    return material


def get_or_create_session(
    db: Session,
    user_id: str,
    now_ms: int,
    silence_threshold_min: int = 30,
) -> tuple[ChatSession, Optional[ChatSession]]:
    """
    获取或创建当前 open 的 session。
    返回 (session, old_session_to_close_or_None)
    """
    open_session = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id, ChatSession.status == "open")
        .first()
    )

    if open_session:
        last_time = open_session.end_time or open_session.start_time
        silence_ms = silence_threshold_min * 60 * 1000
        if (now_ms - last_time) > silence_ms:
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
        return open_session, None

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


def get_history(db: Session, user_id: str, limit: int = 20):
    """获取用户聊天历史记录"""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(limit)
        .all()
    )

    total = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .count()
    )

    items = [serialize_message(message) for message in reversed(messages)]
    return {"items": items, "total": total}

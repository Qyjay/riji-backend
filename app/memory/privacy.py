"""隐私安全协议：为 agent-to-agent 生成可分享上下文。"""
from sqlalchemy.orm import Session

from app.memory.retriever import retrieve_shared_memories
from app.memory.service import _decode
from app.models.memory import AvatarCard
from app.models.user import User


FORBIDDEN_AGENT_CONTEXT_KEYS = {
    "private_raw_text",
    "diary_content",
    "chat_content",
    "social_message_content",
    "memory_document_content",
}


def _card_to_public_dict(card: AvatarCard) -> dict:
    return {
        "displayName": card.display_name or "",
        "publicSummary": card.public_summary or "",
        "interestTags": _decode(card.interest_tags, []),
        "socialIntent": _decode(card.social_intent, []),
        "conversationStyle": _decode(card.conversation_style, {}),
        "boundaries": _decode(card.boundaries, []),
        "visibility": card.visibility or "private",
        "updatedAt": card.updated_at or 0,
    }


def build_agent_context(
    db: Session,
    *,
    owner_user_id: str,
    viewer_user_id: str,
    query: str = "",
    top_k: int = 5,
) -> dict:
    """只暴露 AvatarCard 与 public/school/match_card 级别记忆摘要。"""
    owner = db.query(User).filter(User.id == owner_user_id).first()
    viewer = db.query(User).filter(User.id == viewer_user_id).first()
    card = db.query(AvatarCard).filter(AvatarCard.user_id == owner_user_id).first()
    shared = retrieve_shared_memories(
        db,
        owner_user_id=owner_user_id,
        query=query,
        scenario="agent_to_agent",
        top_k=top_k,
        source_types=["plaza_post_index"],
        viewer_school=(viewer.school if viewer else "") or "",
        owner_school=(owner.school if owner else "") or "",
    )
    safe_memories = [
        {
            "sourceType": item["source_type"],
            "title": item["title"],
            "summary": (item.get("summary") or item.get("content") or "")[:180],
            "visibility": item["visibility"],
            "score": item["score"],
        }
        for item in shared
    ]
    return {
        "ownerUserId": owner_user_id,
        "avatarCard": _card_to_public_dict(card) if card else None,
        "sharedMemories": safe_memories,
        "privacyContract": {
            "allowed": ["avatar_card", "public_memory_summary", "school_memory_summary", "match_card"],
            "forbidden": sorted(FORBIDDEN_AGENT_CONTEXT_KEYS),
            "rawPrivateMemoryIncluded": False,
        },
    }

"""统一记忆画像生成。"""
import json
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.memory import MemoryDocument, MemoryFact, MemoryProfile


def _now_ms() -> int:
    return int(time.time() * 1000)


def _encode(obj, default="{}") -> str:
    if obj is None:
        return default
    return json.dumps(obj, ensure_ascii=False)


def _decode(raw, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def build_profile_context(db: Session, user_id: str) -> str:
    facts = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user_id, MemoryFact.is_active == True)  # noqa: E712
        .order_by(MemoryFact.is_pinned.desc(), MemoryFact.updated_at.desc())
        .limit(80)
        .all()
    )
    documents = (
        db.query(MemoryDocument)
        .filter(MemoryDocument.user_id == user_id, MemoryDocument.is_deleted == False)  # noqa: E712
        .order_by(MemoryDocument.occurred_at.desc())
        .limit(20)
        .all()
    )
    fact_lines = [f"- [{f.category}] {f.content}" for f in facts]
    doc_lines = [f"- [{d.source_type}] {d.title or '无标题'}: {(d.summary or d.content or '')[:120]}" for d in documents]
    return "【结构化记忆】\n" + ("\n".join(fact_lines) or "暂无") + "\n\n【近期原文记忆】\n" + ("\n".join(doc_lines) or "暂无")


async def regenerate_memory_profile(db: Session, user_id: str, profile_type: str = "avatar") -> MemoryProfile:
    """基于 MemoryFact + MemoryDocument 生成统一画像快照。"""
    from app.ai.minimax_client import get_minimax_client

    context = build_profile_context(db, user_id)
    system_prompt = (
        "你是日迹 App 的用户画像生成器。根据长期记忆生成结构化画像。"
        "只基于给定记忆，不要编造。输出严格 JSON，不要 markdown。"
    )
    user_prompt = (
        "请生成 JSON：{\"summary\":\"150字以内摘要\",\"traits\":{},\"interests\":[],"
        "\"preferences\":{},\"relations\":{},\"social_style\":{},\"boundaries\":[],\"recent_state\":\"\"}\n\n"
        f"画像类型：{profile_type}\n{context[:7000]}"
    )

    client = get_minimax_client()
    if getattr(client, "mock", False):
        data = {
            "summary": "用户正在通过日记、对话和社交记录逐步形成更清晰的个人画像。",
            "traits": {},
            "interests": [],
            "preferences": {},
            "relations": {},
            "social_style": {"tone": "自然、友善"},
            "boundaries": [],
            "recent_state": "画像仍在积累中",
        }
    else:
        raw = await client.chat_completion(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1600,
        )
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            import re

            match = re.search(r"\{[\s\S]*\}", raw or "")
            data = json.loads(match.group(0)) if match else {}

    now = _now_ms()
    profile = (
        db.query(MemoryProfile)
        .filter(MemoryProfile.user_id == user_id, MemoryProfile.profile_type == profile_type)
        .first()
    )
    doc_count = db.query(MemoryDocument).filter(MemoryDocument.user_id == user_id).count()
    source_range = {"document_count": doc_count, "generated_from": "memory_facts_and_documents"}
    if not profile:
        profile = MemoryProfile(
            id=str(uuid4()),
            user_id=user_id,
            profile_type=profile_type,
            summary=data.get("summary", ""),
            traits=_encode(data.get("traits", {})),
            interests=_encode(data.get("interests", []), "[]"),
            preferences=_encode(data.get("preferences", {})),
            relations=_encode(data.get("relations", {})),
            social_style=_encode(data.get("social_style", {})),
            boundaries=_encode(data.get("boundaries", []), "[]"),
            recent_state=data.get("recent_state", ""),
            version=1,
            generated_at=now,
            source_range=_encode(source_range),
        )
        db.add(profile)
    else:
        profile.summary = data.get("summary", "")
        profile.traits = _encode(data.get("traits", {}))
        profile.interests = _encode(data.get("interests", []), "[]")
        profile.preferences = _encode(data.get("preferences", {}))
        profile.relations = _encode(data.get("relations", {}))
        profile.social_style = _encode(data.get("social_style", {}))
        profile.boundaries = _encode(data.get("boundaries", []), "[]")
        profile.recent_state = data.get("recent_state", "")
        profile.version = (profile.version or 0) + 1
        profile.generated_at = now
        profile.source_range = _encode(source_range)
    db.commit()
    db.refresh(profile)
    return profile


def memory_profile_to_dict(profile: MemoryProfile) -> dict:
    return {
        "id": profile.id,
        "profile_type": profile.profile_type or "avatar",
        "summary": profile.summary or "",
        "traits": _decode(profile.traits, {}),
        "interests": _decode(profile.interests, []),
        "preferences": _decode(profile.preferences, {}),
        "relations": _decode(profile.relations, {}),
        "social_style": _decode(profile.social_style, {}),
        "boundaries": _decode(profile.boundaries, []),
        "recent_state": profile.recent_state or "",
        "version": profile.version or 1,
        "generated_at": profile.generated_at or 0,
        "source_range": _decode(profile.source_range, {}),
    }

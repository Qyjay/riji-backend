"""结构化记忆抽取。"""
import json
import re
import time
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from app.models.memory import MemoryDocument, MemoryFact

_FACT_CATEGORIES = {
    "identity",
    "personality",
    "interest",
    "preference",
    "habit",
    "relation",
    "need",
    "boundary",
    "writing_style",
    "experience",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _normalize_fact(item: dict, source_type: str) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    content = str(item.get("content") or "").strip()
    if not content:
        return None
    category = str(item.get("category") or "experience").strip() or "experience"
    if category not in _FACT_CATEGORIES:
        category = "experience"
    try:
        confidence = float(item.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    if confidence < 0.6:
        return None
    return {
        "category": category,
        "content": content[:500],
        "subject": str(item.get("subject") or "").strip()[:80],
        "predicate": str(item.get("predicate") or "").strip()[:80],
        "object": str(item.get("object") or "").strip()[:160],
        "confidence": max(0.0, min(confidence, 1.0)),
        "stability": str(item.get("stability") or "recent").strip()[:40] or "recent",
        "source_type": source_type,
    }


def _upsert_fact(db: Session, user_id: str, document: MemoryDocument, data: dict) -> MemoryFact:
    existing = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == user_id,
            MemoryFact.category == data["category"],
            MemoryFact.content == data["content"],
            MemoryFact.is_active == True,  # noqa: E712
        )
        .first()
    )
    now = _now_ms()
    if existing:
        existing.confidence = max(existing.confidence or 0.0, data["confidence"])
        existing.evidence_document_id = document.id
        existing.source_type = document.source_type
        existing.updated_at = now
        return existing

    fact = MemoryFact(
        id=str(uuid4()),
        user_id=user_id,
        category=data["category"],
        content=data["content"],
        subject=data["subject"],
        predicate=data["predicate"],
        object=data["object"],
        confidence=data["confidence"],
        stability=data["stability"],
        evidence_document_id=document.id,
        evidence_chunk_id=None,
        source_type=data["source_type"],
        valid_from=document.occurred_at,
        valid_to=None,
        is_active=True,
        is_pinned=False,
        created_at=now,
        updated_at=now,
    )
    db.add(fact)
    return fact


async def extract_facts_from_document(db: Session, document_id: str) -> list[MemoryFact]:
    """从 MemoryDocument 抽取结构化事实，并写入 MemoryFact。"""
    document = (
        db.query(MemoryDocument)
        .filter(MemoryDocument.id == document_id, MemoryDocument.is_deleted == False)  # noqa: E712
        .first()
    )
    if not document:
        return []

    content = (document.content or "").strip()
    if not content:
        return []

    from app.ai.minimax_client import get_minimax_client

    system_prompt = (
        "你是 Avalin 的长期记忆抽取器。请从用户原文中抽取稳定或近期有用的结构化记忆。"
        "只抽取有明确证据的信息，不要臆测。输出严格 JSON，不要 markdown。"
        "可用 category: identity, personality, interest, preference, habit, relation, need, boundary, writing_style, experience。"
        "confidence 范围 0-1；不确定的信息不要输出。"
    )
    user_prompt = (
        "请从以下内容抽取结构化记忆，格式：\n"
        "{\"facts\":[{\"category\":\"interest\",\"content\":\"用户喜欢晚上散步\","
        "\"subject\":\"用户\",\"predicate\":\"likes\",\"object\":\"晚上散步\","
        "\"confidence\":0.8,\"stability\":\"recent\"}]}\n\n"
        f"来源类型：{document.source_type}\n"
        f"标题：{document.title or '无标题'}\n"
        f"正文：\n{content[:6000]}"
    )

    client = get_minimax_client()
    if getattr(client, "mock", False):
        # Mock 模式给开发环境一个可见结果，方便验证链路。
        result_data = {
            "facts": [
                {
                    "category": "experience",
                    "content": (document.summary or content[:80] or "用户产生了一条生活记录"),
                    "subject": "用户",
                    "predicate": "recorded",
                    "object": document.source_type,
                    "confidence": 0.65,
                    "stability": "recent",
                }
            ]
        }
    else:
        raw = await client.chat_completion(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=1200,
        )
        result_data = _extract_json_object(raw)

    facts = result_data.get("facts", []) if isinstance(result_data, dict) else []
    saved: list[MemoryFact] = []
    for item in facts:
        normalized = _normalize_fact(item, document.source_type)
        if not normalized:
            continue
        saved.append(_upsert_fact(db, document.user_id, document, normalized))
    db.commit()
    return saved

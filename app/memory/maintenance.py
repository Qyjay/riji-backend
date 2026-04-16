"""记忆维护：冲突检测、淡化与基础评估辅助。"""
import time
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models.memory import MemoryFact


def _now_ms() -> int:
    return int(time.time() * 1000)


def detect_memory_conflicts(db: Session, user_id: str) -> list[dict]:
    """用保守规则发现潜在冲突，不自动删除。"""
    facts = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user_id, MemoryFact.is_active == True)  # noqa: E712
        .order_by(MemoryFact.updated_at.desc())
        .all()
    )
    groups = defaultdict(list)
    for fact in facts:
        key = (
            fact.category or "",
            (fact.subject or "").strip(),
            (fact.predicate or "").strip(),
            (fact.object or "").strip(),
        )
        if key[0] and key[1:] != ("", "", ""):
            groups[key].append(fact)

    conflicts = []
    for key, items in groups.items():
        contents = {item.content for item in items if item.content}
        if len(contents) <= 1:
            continue
        conflicts.append(
            {
                "category": key[0],
                "subject": key[1],
                "predicate": key[2],
                "object": key[3],
                "facts": [
                    {
                        "id": item.id,
                        "content": item.content,
                        "confidence": item.confidence or 0.0,
                        "updatedAt": item.updated_at or 0,
                    }
                    for item in items
                ],
            }
        )
    return conflicts


def decay_memory_facts(
    db: Session,
    user_id: str,
    *,
    older_than_days: int = 180,
    decay_factor: float = 0.92,
    min_confidence: float = 0.3,
) -> dict:
    """对低稳定性的旧 facts 做置信度淡化。"""
    threshold = _now_ms() - older_than_days * 24 * 60 * 60 * 1000
    candidates = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == user_id,
            MemoryFact.is_active == True,  # noqa: E712
            MemoryFact.is_pinned == False,  # noqa: E712
            MemoryFact.updated_at < threshold,
        )
        .all()
    )
    decayed = 0
    deactivated = 0
    now = _now_ms()
    for fact in candidates:
        if (fact.stability or "recent") == "stable":
            continue
        current = fact.confidence if fact.confidence is not None else 0.7
        fact.confidence = max(0.0, current * decay_factor)
        fact.updated_at = now
        decayed += 1
        if fact.confidence < min_confidence:
            fact.is_active = False
            deactivated += 1
    db.commit()
    return {"checked": len(candidates), "decayed": decayed, "deactivated": deactivated}

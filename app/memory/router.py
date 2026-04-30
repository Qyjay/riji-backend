"""记忆系统路由。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from uuid import uuid4

from app.dependencies import get_current_user, get_db
from app.memory import schemas
from app.config import settings
from app.memory.extractor import extract_facts_from_document
from app.memory.indexer import get_embedding_status, get_vector_backend_status
from app.memory.maintenance import decay_memory_facts, detect_memory_conflicts
from app.memory.privacy import build_agent_context
from app.memory.profiler import memory_profile_to_dict, regenerate_memory_profile
from app.memory.retriever import retrieve_memories
from app.memory.service import _decode, get_memory_document, list_memory_documents, soft_delete_memory_document
from app.models.memory import AgentAction, AvatarCard, MemoryChunk, MemoryDocument, MemoryFact, MemoryProfile
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_INVALID, success

router = APIRouter(prefix="/memory", tags=["记忆系统"])


@router.get("/health", summary="记忆向量健康检查")
def memory_health():
    vector_status = get_vector_backend_status()
    embedding_status = get_embedding_status()
    return success({
        "memoryEnabled": bool(getattr(settings, "MEMORY_ENABLED", True)),
        "vector": vector_status,
        "embedding": embedding_status,
    })


def _document_to_out(document) -> dict:
    return schemas.MemoryDocumentOut(
        id=document.id,
        source_type=document.source_type,
        source_id=document.source_id,
        title=document.title or "",
        content=document.content or "",
        summary=document.summary or "",
        visibility=document.visibility or "private",
        memory_scope=document.memory_scope or "self",
        occurred_at=document.occurred_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
        tags=_decode(document.tags, []),
    ).model_dump(by_alias=True)


def _fact_to_out(fact: MemoryFact) -> dict:
    return schemas.MemoryFactOut(
        id=fact.id,
        category=fact.category or "",
        content=fact.content or "",
        subject=fact.subject or "",
        predicate=fact.predicate or "",
        object=fact.object or "",
        confidence=fact.confidence or 0.0,
        stability=fact.stability or "",
        is_active=fact.is_active if fact.is_active is not None else True,
        is_pinned=fact.is_pinned or False,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
    ).model_dump(by_alias=True)


def _export_memory_payload(db: Session, user_id: str) -> dict:
    documents = (
        db.query(MemoryDocument)
        .filter(MemoryDocument.user_id == user_id, MemoryDocument.is_deleted == False)  # noqa: E712
        .order_by(MemoryDocument.occurred_at.desc())
        .all()
    )
    facts = db.query(MemoryFact).filter(MemoryFact.user_id == user_id).all()
    profiles = db.query(MemoryProfile).filter(MemoryProfile.user_id == user_id).all()
    cards = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).all()
    actions = db.query(AgentAction).filter(AgentAction.user_id == user_id).all()
    return {
        "version": 1,
        "documents": [_document_to_out(item) for item in documents],
        "facts": [_fact_to_out(item) for item in facts],
        "profiles": [schemas.MemoryProfileOut(**memory_profile_to_dict(item)).model_dump(by_alias=True) for item in profiles],
        "avatarCards": [
            {
                "id": item.id,
                "displayName": item.display_name or "",
                "publicSummary": item.public_summary or "",
                "interestTags": _decode(item.interest_tags, []),
                "socialIntent": _decode(item.social_intent, []),
                "conversationStyle": _decode(item.conversation_style, {}),
                "boundaries": _decode(item.boundaries, []),
                "visibility": item.visibility or "private",
                "updatedAt": item.updated_at or 0,
            }
            for item in cards
        ],
        "agentActions": [
            {
                "id": item.id,
                "actionType": item.action_type or "",
                "targetType": item.target_type or "",
                "targetId": item.target_id or "",
                "inputContext": _decode(item.input_context, {}),
                "outputText": item.output_text or "",
                "status": item.status or "",
                "createdAt": item.created_at or 0,
                "updatedAt": item.updated_at or 0,
            }
            for item in actions
        ],
    }


@router.post("/search", summary="搜索当前用户记忆")
def search_memories(
    body: schemas.MemorySearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = retrieve_memories(
        db,
        user_id=current_user.id,
        query=body.query,
        scenario=body.scenario,
        top_k=body.top_k,
        source_types=body.source_types,
    )
    out = [schemas.MemorySearchItem(**item).model_dump(by_alias=True) for item in items]
    return success({"items": out})


@router.get("/export", summary="导出当前用户记忆数据")
def export_memories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(_export_memory_payload(db, current_user.id))


@router.delete("/all", summary="删除当前用户所有记忆数据")
def delete_all_memories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document_ids = [
        item.id
        for item in db.query(MemoryDocument).filter(MemoryDocument.user_id == current_user.id).all()
    ]
    if document_ids:
        db.query(MemoryChunk).filter(MemoryChunk.document_id.in_(document_ids)).delete(synchronize_session=False)
    db.query(MemoryDocument).filter(MemoryDocument.user_id == current_user.id).delete(synchronize_session=False)
    db.query(MemoryFact).filter(MemoryFact.user_id == current_user.id).delete(synchronize_session=False)
    db.query(MemoryProfile).filter(MemoryProfile.user_id == current_user.id).delete(synchronize_session=False)
    db.query(AvatarCard).filter(AvatarCard.user_id == current_user.id).delete(synchronize_session=False)
    db.query(AgentAction).filter(AgentAction.user_id == current_user.id).delete(synchronize_session=False)
    # 兼容旧分身记忆系统，避免前端清空后刷新又看到旧 AvatarMemory/AvatarProfile。
    from app.models.avatar import AvatarMemory, AvatarProfile

    db.query(AvatarMemory).filter(AvatarMemory.user_id == current_user.id).delete(synchronize_session=False)
    db.query(AvatarProfile).filter(AvatarProfile.user_id == current_user.id).delete(synchronize_session=False)
    db.commit()
    return success(None)


@router.post("/agent-context", summary="生成 agent-to-agent 安全上下文")
def agent_context(
    body: schemas.AgentContextRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    context = build_agent_context(
        db,
        owner_user_id=body.owner_user_id,
        viewer_user_id=current_user.id,
        query=body.query,
        top_k=body.top_k,
    )
    return success(context)


@router.get("/conflicts", summary="检测当前用户潜在记忆冲突")
def memory_conflicts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success({"items": detect_memory_conflicts(db, current_user.id)})


@router.post("/maintenance/decay", summary="淡化旧的低稳定性结构化记忆")
def decay_memories(
    body: schemas.DecayMemoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = decay_memory_facts(
        db,
        current_user.id,
        older_than_days=body.older_than_days,
        decay_factor=body.decay_factor,
        min_confidence=body.min_confidence,
    )
    return success(result)


@router.get("/documents", summary="记忆文档列表")
def list_documents(
    source_type: Optional[str] = Query(None, alias="sourceType"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    documents = list_memory_documents(
        db,
        current_user.id,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return success({"items": [_document_to_out(item) for item in documents]})


@router.get("/documents/{document_id}", summary="记忆文档详情")
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = get_memory_document(db, current_user.id, document_id)
    if not document:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)
    return success(_document_to_out(document))


@router.delete("/documents/{document_id}", summary="删除记忆文档")
def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deleted = soft_delete_memory_document(db, current_user.id, document_id)
    if not deleted:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)
    db.commit()
    return success(None)


@router.post("/documents/{document_id}/extract", summary="从记忆文档抽取结构化记忆")
async def extract_document_facts(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = get_memory_document(db, current_user.id, document_id)
    if not document:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)
    facts = await extract_facts_from_document(db, document.id)
    return success({"items": [_fact_to_out(item) for item in facts]})


@router.get("/facts", summary="结构化记忆列表")
def list_facts(
    category: Optional[str] = Query(None),
    active_only: bool = Query(True, alias="activeOnly"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(MemoryFact).filter(MemoryFact.user_id == current_user.id)
    if category:
        query = query.filter(MemoryFact.category == category)
    if active_only:
        query = query.filter(MemoryFact.is_active == True)  # noqa: E712
    facts = query.order_by(MemoryFact.is_pinned.desc(), MemoryFact.updated_at.desc()).all()
    return success({"items": [_fact_to_out(item) for item in facts]})


@router.post("/facts", summary="手动创建结构化记忆")
def create_fact(
    body: schemas.CreateMemoryFactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import time

    content = (body.content or "").strip()
    if not content:
        raise ApiException(code=PARAM_INVALID, message="记忆内容不能为空", status_code=400)

    now = int(time.time() * 1000)
    fact = MemoryFact(
        id=str(uuid4()),
        user_id=current_user.id,
        category=(body.category or "profile").strip(),
        content=content,
        subject=(body.subject or "user").strip(),
        predicate=(body.predicate or "has_fact").strip(),
        object=(body.object or content[:80]).strip(),
        confidence=body.confidence,
        stability=(body.stability or "stable").strip(),
        source_type="manual",
        valid_from=now,
        is_active=True,
        is_pinned=body.is_pinned,
        created_at=now,
        updated_at=now,
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return success(_fact_to_out(fact))


@router.put("/facts/{fact_id}", summary="更新结构化记忆")
def update_fact(
    fact_id: str,
    body: schemas.UpdateMemoryFactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import time

    fact = db.query(MemoryFact).filter(MemoryFact.id == fact_id, MemoryFact.user_id == current_user.id).first()
    if not fact:
        raise ApiException(code=NOT_FOUND, message="结构化记忆不存在", status_code=404)
    data = body.model_dump(exclude_unset=True)
    if "content" in data and data["content"] is not None:
        fact.content = data["content"]
    if "category" in data and data["category"] is not None:
        fact.category = data["category"]
    if "confidence" in data and data["confidence"] is not None:
        fact.confidence = data["confidence"]
    if "is_active" in data and data["is_active"] is not None:
        fact.is_active = data["is_active"]
    if "is_pinned" in data and data["is_pinned"] is not None:
        fact.is_pinned = data["is_pinned"]
    fact.updated_at = int(time.time() * 1000)
    db.commit()
    db.refresh(fact)
    return success(_fact_to_out(fact))


@router.delete("/facts/{fact_id}", summary="删除结构化记忆")
def delete_fact(
    fact_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fact = db.query(MemoryFact).filter(MemoryFact.id == fact_id, MemoryFact.user_id == current_user.id).first()
    if not fact:
        raise ApiException(code=NOT_FOUND, message="结构化记忆不存在", status_code=404)
    db.delete(fact)
    db.commit()
    return success(None)


@router.post("/profile/regenerate", summary="重新生成统一记忆画像")
async def regenerate_profile(
    profile_type: str = Query("avatar", alias="profileType"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = await regenerate_memory_profile(db, current_user.id, profile_type=profile_type)
    return success(schemas.MemoryProfileOut(**memory_profile_to_dict(profile)).model_dump(by_alias=True))

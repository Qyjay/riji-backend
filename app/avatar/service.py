"""
AI 分身模块服务层
实现记忆 CRUD、状态管理、推荐匹配、侧写生成业务逻辑
"""
import json
import time
from typing import List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.avatar import AvatarMemory, AvatarMatch, AvatarProfile, AvatarStatus
from app.models.memory import AgentAction, AvatarCard, MemoryFact
from app.models.plaza import PlazaComment, PlazaPost
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_INVALID


def _now_ms() -> int:
    return int(time.time() * 1000)


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = []
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _memory_to_dict(m: AvatarMemory) -> dict:
    """AvatarMemory ORM → 响应字典"""
    return {
        "id": m.id,
        "category": m.category or "",
        "content": m.content or "",
        "source": m.source or "manual",
        "source_ref": m.source_ref or None,
        "confidence": m.confidence if m.confidence is not None else 1.0,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "is_active": m.is_active if m.is_active is not None else True,
        "is_pinned": m.is_pinned or False,
        "need_type": m.need_type or None,
        "urgency": m.urgency or None,
        "expiry": m.expiry or None,
        "match_status": m.match_status or None,
        "tags": _decode(m.tags, []),
    }


def _default_match_range() -> dict:
    return {
        "school": "",
        "distanceKm": 10,
        "autoReplyDailyLimit": 5,
        "autoReplyIntervalMinutes": 30,
        "autoReplyMinScore": 55,
    }


def _status_to_dict(s: AvatarStatus) -> dict:
    """AvatarStatus ORM → 响应字典"""
    return {
        "is_active": s.is_active if s.is_active is not None else True,
        "browsed_count": s.browsed_count or 0,
        "matched_count": s.matched_count or 0,
        "chatting_count": s.chatting_count or 0,
        "last_active_at": s.last_active_at or 0,
        "enabled_channels": _decode(s.enabled_channels, ["buddy", "help", "share", "dating"]),
        "enabled_actions": _decode(s.enabled_actions, ["browse", "match", "comment"]),
        "match_range": {**_default_match_range(), **_decode(s.match_range, {})},
    }


# ==================== 记忆 CRUD ====================

def list_memories(db: Session, user_id: str, category: Optional[str] = None) -> List[dict]:
    """记忆列表，可按 category 筛选"""
    query = db.query(AvatarMemory).filter(AvatarMemory.user_id == user_id)
    if category:
        query = query.filter(AvatarMemory.category == category)
    memories = query.order_by(AvatarMemory.created_at.desc()).all()
    return [_memory_to_dict(m) for m in memories]


def add_memory(db: Session, user_id: str, data: dict) -> dict:
    """添加记忆"""
    now = _now_ms()
    memory = AvatarMemory(
        id=str(uuid4()),
        user_id=user_id,
        category=data["category"],
        content=data["content"],
        source="manual",
        source_ref="",
        confidence=1.0,
        is_active=True,
        is_pinned=False,
        tags=_encode([]),
        created_at=now,
        updated_at=now,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return _memory_to_dict(memory)


def update_memory(db: Session, user_id: str, memory_id: str, data: dict) -> dict:
    """更新记忆"""
    m = db.query(AvatarMemory).filter(
        AvatarMemory.id == memory_id,
        AvatarMemory.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)

    if "content" in data and data["content"] is not None:
        m.content = data["content"]
    if "is_active" in data and data["is_active"] is not None:
        m.is_active = data["is_active"]
    if "is_pinned" in data and data["is_pinned"] is not None:
        m.is_pinned = data["is_pinned"]
    if "category" in data and data["category"] is not None:
        m.category = data["category"]
    if "tags" in data and data["tags"] is not None:
        m.tags = _encode(data["tags"])

    m.updated_at = _now_ms()
    db.commit()
    db.refresh(m)
    return _memory_to_dict(m)


def delete_memory(db: Session, user_id: str, memory_id: str) -> None:
    """删除记忆"""
    m = db.query(AvatarMemory).filter(
        AvatarMemory.id == memory_id,
        AvatarMemory.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)
    db.delete(m)
    db.commit()


# ==================== 分身状态 ====================

def _get_or_create_status(db: Session, user_id: str) -> AvatarStatus:
    """获取分身状态，首次访问自动创建默认记录"""
    status = db.query(AvatarStatus).filter(AvatarStatus.user_id == user_id).first()
    if not status:
        status = AvatarStatus(
            id=str(uuid4()),
            user_id=user_id,
            is_active=True,
            browsed_count=0,
            matched_count=0,
            chatting_count=0,
            last_active_at=0,
            enabled_channels=_encode(["buddy", "help", "share", "dating"]),
            enabled_actions=_encode(["browse", "match", "comment"]),
            match_range=_encode(_default_match_range()),
        )
        db.add(status)
        db.commit()
        db.refresh(status)
    return status


def get_status(db: Session, user_id: str) -> dict:
    """获取分身状态"""
    status = _get_or_create_status(db, user_id)
    return _status_to_dict(status)


def update_status(db: Session, user_id: str, data: dict) -> dict:
    """更新分身状态"""
    status = _get_or_create_status(db, user_id)

    if "is_active" in data and data["is_active"] is not None:
        status.is_active = data["is_active"]
    if "enabled_channels" in data and data["enabled_channels"] is not None:
        status.enabled_channels = _encode(data["enabled_channels"])
    if "enabled_actions" in data and data["enabled_actions"] is not None:
        status.enabled_actions = _encode(data["enabled_actions"])
    if "match_range" in data and data["match_range"] is not None:
        status.match_range = _encode(data["match_range"])

    db.commit()
    db.refresh(status)
    return _status_to_dict(status)


# ==================== 分身推荐 ====================

def _post_to_dict(post: PlazaPost, user: User) -> dict:
    """复用广场帖子序列化（避免循环导入，独立实现）"""
    return {
        "id": post.id,
        "author_id": post.user_id,
        "author_name": user.name or user.username,
        "author_avatar": user.avatar or "",
        "author_school": user.school or "",
        "author_major": user.major or "",
        "author_grade": user.grade or "",
        "type": post.type,
        "content": post.content or "",
        "images": _decode(post.images, []),
        "location": post.location or "",
        "tags": _decode(post.tags, []),
        "likes": post.likes or 0,
        "comments": post.comments or 0,
        "agent_responses": post.agent_responses or 0,
        "created_at": post.created_at,
        "is_from_agent": post.is_from_agent or False,
        "allow_agent_reply": post.allow_agent_reply if post.allow_agent_reply is not None else True,
        "school_only": post.school_only or False,
    }


def _tokenize_text(value: str) -> list[str]:
    import re

    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", str(value or "").lower())
    return list(dict.fromkeys(tokens))


def _collect_match_keywords(db: Session, user_id: str) -> dict:
    card = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    facts = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user_id, MemoryFact.is_active == True)  # noqa: E712
        .order_by(MemoryFact.is_pinned.desc(), MemoryFact.updated_at.desc())
        .limit(40)
        .all()
    )
    memories = (
        db.query(AvatarMemory)
        .filter(AvatarMemory.user_id == user_id, AvatarMemory.is_active == True)  # noqa: E712
        .order_by(AvatarMemory.is_pinned.desc(), AvatarMemory.updated_at.desc())
        .limit(20)
        .all()
    )
    interests = _decode(card.interest_tags, []) if card else []
    intents = _decode(card.social_intent, []) if card else []
    boundaries = _decode(card.boundaries, []) if card else []
    profile_summary = card.public_summary if card else ""

    for fact in facts:
        text = (fact.content or "").strip()
        if not text:
            continue
        if fact.category in {"interest", "preference", "habit"} and len(interests) < 16:
            interests.append(text[:30])
        elif fact.category == "need" and len(intents) < 8:
            intents.append(text[:40])
        elif fact.category == "boundary" and len(boundaries) < 8:
            boundaries.append(text[:60])

    if len(interests) < 16:
        for memory in memories:
            if memory.category in {"interest", "habit", "need"}:
                interests.append((memory.content or "")[:30])

    interest_tokens = set()
    for item in interests:
        interest_tokens.update(_tokenize_text(item))
    intent_tokens = set()
    for item in intents:
        intent_tokens.update(_tokenize_text(item))
    profile_tokens = set(_tokenize_text(profile_summary))

    return {
        "card": card,
        "interests": list(dict.fromkeys([item for item in interests if item])),
        "intents": list(dict.fromkeys([item for item in intents if item])),
        "boundaries": list(dict.fromkeys([item for item in boundaries if item])),
        "interest_tokens": interest_tokens,
        "intent_tokens": intent_tokens,
        "profile_tokens": profile_tokens,
    }


def _match_channel_reason(post_type: str, intents: list[str]) -> Optional[str]:
    text = " ".join(intents)
    mapping = {
        "buddy": ["搭子", "一起", "陪伴", "结伴", "自习"],
        "help": ["帮助", "求助", "建议", "支持"],
        "share": ["分享", "交流", "记录", "看看"],
        "dating": ["恋爱", "心动", "约会", "认识"],
    }
    if any(keyword in text for keyword in mapping.get(post_type, [])):
        return f"你的社交意图里包含和「{post_type}」频道相近的需求"
    return None


def _build_match_for_post(db: Session, current_user: User, post: PlazaPost, author: User, inputs: dict) -> Optional[dict]:
    from app.memory.retriever import retrieve_shared_memories

    reasons = []
    score = 0
    seen = set()
    post_tags = _decode(post.tags, [])
    post_text = f"{post.content or ''} {' '.join(post_tags)} {post.location or ''}".lower()
    post_tokens = set(_tokenize_text(post_text))

    def _push_reason(reason: str, delta: int) -> None:
        nonlocal score
        if reason and reason not in seen:
            reasons.append(reason)
            seen.add(reason)
            score += delta

    if (author.school or "") and (author.school or "") == (current_user.school or ""):
        _push_reason("你们在同一所学校，线下交流成本更低", 18)

    channel_reason = _match_channel_reason(post.type or "", inputs["intents"])
    if channel_reason:
        _push_reason(channel_reason, 14)

    shared_interest_tokens = sorted(inputs["interest_tokens"].intersection(post_tokens))
    if shared_interest_tokens:
        _push_reason(f"帖子内容命中了你的兴趣关键词：{' / '.join(shared_interest_tokens[:3])}", 20)

    author_card = db.query(AvatarCard).filter(AvatarCard.user_id == post.user_id).first()
    if author_card:
        author_interests = set(_tokenize_text(" ".join(_decode(author_card.interest_tags, []))))
        overlap = sorted(inputs["interest_tokens"].intersection(author_interests))
        if overlap:
            _push_reason(f"你和对方分身名片里都提到了：{' / '.join(overlap[:3])}", 16)

    shared_memories = retrieve_shared_memories(
        db,
        owner_user_id=post.user_id,
        query=" ".join(list(inputs["interest_tokens"])[:6] + list(inputs["intent_tokens"])[:4]),
        scenario="plaza_match",
        top_k=2,
        source_types=["plaza_post_index"],
        viewer_school=current_user.school or "",
        owner_school=author.school or "",
    )
    for memory in shared_memories[:2]:
        title = memory.get("title") or "对方公开记忆"
        snippet = (memory.get("summary") or memory.get("content") or "").strip()
        if snippet:
            _push_reason(f"{title} 里也出现了与你相关的话题：{snippet[:24]}", 12)

    if post.allow_agent_reply:
        _push_reason("这条帖子允许分身先打个招呼，适合低压力开启互动", 6)

    if score < 20 or not reasons:
        return None

    conversation = []
    if author_card and inputs["card"]:
        conversation = [
            {
                "from": "my_agent",
                "content": f"我主人可能会对这条内容感兴趣，尤其是 {', '.join(inputs['interests'][:2]) or '你们的共同话题'}。",
                "timestamp": _now_ms(),
            },
            {
                "from": "their_agent",
                "content": f"我的主人最近也愿意聊聊 {', '.join(_decode(author_card.interest_tags, [])[:2]) or '这些话题'}。",
                "timestamp": _now_ms(),
            },
        ]

    return {
        "score": min(score, 99),
        "reasons": reasons[:4],
        "agent_conversation": conversation[:2],
    }


def _refresh_matches(db: Session, user_id: str) -> None:
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return
    status = _get_or_create_status(db, user_id)
    if status.is_active is False:
        return

    inputs = _collect_match_keywords(db, user_id)
    enabled_channels = _decode(status.enabled_channels, ["buddy", "help", "share", "dating"])
    dismissed_ids = {
        item.post_id
        for item in db.query(AvatarMatch)
        .filter(AvatarMatch.user_id == user_id, AvatarMatch.status == "dismissed")
        .all()
    }
    rows = (
        db.query(PlazaPost, User)
        .join(User, PlazaPost.user_id == User.id)
        .filter(PlazaPost.user_id != user_id, PlazaPost.type.in_(enabled_channels))
        .order_by(PlazaPost.created_at.desc())
        .limit(60)
        .all()
    )

    browsed_count = 0
    matched_count = 0
    now = _now_ms()
    for post, author in rows:
        if post.id in dismissed_ids:
            continue
        if post.school_only and (author.school or "") != (current_user.school or ""):
            continue
        browsed_count += 1
        match_data = _build_match_for_post(db, current_user, post, author, inputs)
        if not match_data:
            continue
        matched_count += 1
        existing = (
            db.query(AvatarMatch)
            .filter(AvatarMatch.user_id == user_id, AvatarMatch.post_id == post.id)
            .first()
        )
        if not existing:
            existing = AvatarMatch(
                id=str(uuid4()),
                user_id=user_id,
                post_id=post.id,
                match_score=match_data["score"],
                match_reasons=_encode(match_data["reasons"]),
                agent_conversation=_encode(match_data["agent_conversation"]),
                status="new",
                created_at=now,
            )
            db.add(existing)
        elif existing.status != "dismissed":
            existing.match_score = match_data["score"]
            existing.match_reasons = _encode(match_data["reasons"])
            existing.agent_conversation = _encode(match_data["agent_conversation"])

    status.browsed_count = max(status.browsed_count or 0, browsed_count)
    status.matched_count = matched_count
    status.last_active_at = now
    db.commit()


def list_matches(db: Session, user_id: str) -> List[dict]:
    """分身推荐列表，排除 dismissed，按 match_score DESC"""
    _refresh_matches(db, user_id)
    rows = (
        db.query(AvatarMatch, PlazaPost, User)
        .join(PlazaPost, AvatarMatch.post_id == PlazaPost.id)
        .join(User, PlazaPost.user_id == User.id)
        .filter(AvatarMatch.user_id == user_id)
        .filter(AvatarMatch.status != "dismissed")
        .order_by(AvatarMatch.match_score.desc())
        .all()
    )

    result = []
    for match, post, user in rows:
        result.append({
            "id": match.id,
            "post_id": match.post_id,
            "post": _post_to_dict(post, user),
            "match_score": match.match_score or 0,
            "match_reasons": _decode(match.match_reasons, []),
            "agent_conversation": _decode(match.agent_conversation, []),
            "status": match.status or "new",
            "created_at": match.created_at,
        })
    return result


def match_action(db: Session, user_id: str, match_id: str, action: str) -> None:
    """分身匹配操作：dismiss / chat"""
    if action not in ("dismiss", "chat"):
        raise ApiException(code=PARAM_INVALID, message="action 只能是 dismiss 或 chat")

    match = db.query(AvatarMatch).filter(
        AvatarMatch.id == match_id,
        AvatarMatch.user_id == user_id,
    ).first()
    if not match:
        raise ApiException(code=NOT_FOUND, message="匹配记录不存在", status_code=404)

    status_map = {"dismiss": "dismissed", "chat": "chatting"}
    match.status = status_map[action]
    db.commit()


# ==================== 分身行动草稿/审批 ====================

def list_actions(db: Session, user_id: str, status: Optional[str] = None) -> List[dict]:
    query = db.query(AgentAction).filter(AgentAction.user_id == user_id)
    if status:
        query = query.filter(AgentAction.status == status)
    actions = query.order_by(AgentAction.created_at.desc()).limit(100).all()
    return [_action_to_dict(action) for action in actions]


async def create_plaza_comment_draft(
    db: Session,
    current_user: User,
    post_id: str,
    parent_comment_id: Optional[str] = None,
    input_context_extra: Optional[dict] = None,
) -> dict:
    """生成广场分身评论草稿，不直接发布。"""
    from app.ai.minimax_client import get_minimax_client
    from app.memory.prompts import format_memory_context
    from app.memory.retriever import retrieve_memories

    post = db.query(PlazaPost).filter(PlazaPost.id == post_id).first()
    if not post:
        raise ApiException(code=NOT_FOUND, message="帖子不存在", status_code=404)
    if not post.allow_agent_reply:
        raise ApiException(code=PARAM_INVALID, message="该帖子不允许分身回复", status_code=400)

    parent_comment = None
    parent_user = None
    if parent_comment_id:
        row = (
            db.query(PlazaComment, User)
            .join(User, PlazaComment.user_id == User.id)
            .filter(PlazaComment.id == parent_comment_id, PlazaComment.post_id == post_id)
            .first()
        )
        if not row:
            raise ApiException(code=NOT_FOUND, message="要回复的评论不存在", status_code=404)
        parent_comment, parent_user = row

    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == current_user.id).first()
    if not profile or not (profile.summary or "").strip():
        raise ApiException(code=PARAM_INVALID, message="请先生成分身侧写", status_code=400)

    memories = retrieve_memories(
        db,
        user_id=current_user.id,
        query=post.content or "",
        scenario="avatar_comment",
        top_k=8,
        source_types=["diary", "chat_session", "plaza_post", "plaza_comment", "social_message", "material"],
    )
    memory_context = format_memory_context(memories, scenario="avatar_comment") or "暂无"

    system_prompt = (
        "你是用户的 AI 分身，负责生成广场评论草稿。"
        "评论要像用户本人可能会说的话，自然、友善、低压力。"
        "不要暴露自己是 AI，不要泄露日记、私聊、AI 对话等私密原文。"
    )
    parent_context = ""
    if parent_comment:
        parent_author_name = parent_user.name or parent_user.username if parent_user else "对方"
        if parent_comment.is_agent:
            parent_author_name = f"{parent_author_name}的分身"
        parent_context = f"\n【你正在回复的评论】{parent_author_name}：{parent_comment.content}\n"

    user_prompt = (
        f"【用户侧写】\n{profile.summary}\n\n"
        f"【相关长期记忆（仅供理解，不可原文外泄）】\n{memory_context}\n\n"
        f"【帖子类型】{post.type}\n"
        f"【帖子内容】{post.content}\n\n"
        f"{parent_context}"
        "请生成 1-3 句话的评论草稿，只输出评论正文。"
    )
    client = get_minimax_client()
    reply = await client.chat_completion(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.85,
    )
    reply = reply.strip().strip('"').strip("'")
    now = _now_ms()
    action = AgentAction(
        id=str(uuid4()),
        user_id=current_user.id,
        agent_id="default-avatar",
        action_type="comment_post",
        target_type="plaza_post",
        target_id=post.id,
        input_context=_encode(
            {
                "post_id": post.id,
                "post_type": post.type,
                "memory_count": len(memories),
                "parent_comment_id": parent_comment_id,
                **(input_context_extra or {}),
            }
        ),
        output_text=reply,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return _action_to_dict(action)


def approve_action(db: Session, user_id: str, action_id: str) -> dict:
    """批准分身行动。当前支持发布广场评论草稿。"""
    action = db.query(AgentAction).filter(AgentAction.id == action_id, AgentAction.user_id == user_id).first()
    if not action:
        raise ApiException(code=NOT_FOUND, message="分身行动不存在", status_code=404)
    if action.status != "draft":
        raise ApiException(code=PARAM_INVALID, message="该分身行动不是待审批状态", status_code=400)

    now = _now_ms()
    if action.action_type == "comment_post" and action.target_type == "plaza_post":
        post = db.query(PlazaPost).filter(PlazaPost.id == action.target_id).first()
        if not post:
            raise ApiException(code=NOT_FOUND, message="帖子不存在", status_code=404)
        input_context = _decode(action.input_context, {})
        parent_comment_id = input_context.get("parent_comment_id") or None
        if parent_comment_id:
            parent = db.query(PlazaComment).filter(
                PlazaComment.id == parent_comment_id,
                PlazaComment.post_id == post.id,
            ).first()
            if not parent:
                raise ApiException(code=NOT_FOUND, message="要回复的评论不存在", status_code=404)
        comment = PlazaComment(
            id=str(uuid4()),
            post_id=post.id,
            user_id=user_id,
            parent_comment_id=parent_comment_id,
            content=action.output_text,
            is_agent=True,
            created_at=now,
        )
        db.add(comment)
        post.comments = (post.comments or 0) + 1
        post.agent_responses = (post.agent_responses or 0) + 1
        action.status = "published"
        action.updated_at = now
        db.commit()
        db.refresh(action)
        from app.memory.ingestion import ingest_plaza_comment

        ingest_plaza_comment(db, comment)
        return _action_to_dict(action)

    raise ApiException(code=PARAM_INVALID, message="暂不支持该分身行动类型", status_code=400)


def reject_action(db: Session, user_id: str, action_id: str) -> dict:
    action = db.query(AgentAction).filter(AgentAction.id == action_id, AgentAction.user_id == user_id).first()
    if not action:
        raise ApiException(code=NOT_FOUND, message="分身行动不存在", status_code=404)
    if action.status != "draft":
        raise ApiException(code=PARAM_INVALID, message="该分身行动不是待审批状态", status_code=400)
    action.status = "rejected"
    action.updated_at = _now_ms()
    db.commit()
    db.refresh(action)
    return _action_to_dict(action)


async def auto_surf_comments(db: Session, current_user: User, limit: int = 1) -> dict:
    """触发一次分身冲浪：按匹配度、开关和频率限制自动生成评论草稿或直接发布。"""
    status_obj = _get_or_create_status(db, current_user.id)
    status = _status_to_dict(status_obj)
    enabled_actions = status.get("enabled_actions", [])
    settings = status.get("match_range", {})
    if status_obj.is_active is False:
        return {"actions": [], "published_count": 0, "draft_count": 0, "skipped_reason": "分身当前未开启"}
    if "comment" not in enabled_actions or "auto_surf_comment" not in enabled_actions:
        return {"actions": [], "published_count": 0, "draft_count": 0, "skipped_reason": "未开启自动冲浪回复"}

    now = _now_ms()
    start_of_day = now - (now + 8 * 60 * 60 * 1000) % (24 * 60 * 60 * 1000)
    daily_limit = int(settings.get("autoReplyDailyLimit") or 5)
    interval_ms = int(settings.get("autoReplyIntervalMinutes") or 30) * 60 * 1000
    min_score = int(settings.get("autoReplyMinScore") or 55)
    safe_limit = max(1, min(int(limit or 1), 5))

    today_count = (
        db.query(AgentAction)
        .filter(
            AgentAction.user_id == current_user.id,
            AgentAction.action_type == "comment_post",
            AgentAction.created_at >= start_of_day,
        )
        .count()
    )
    if today_count >= daily_limit:
        return {"actions": [], "published_count": 0, "draft_count": 0, "skipped_reason": "已达到今日自动回复上限"}

    latest = (
        db.query(AgentAction)
        .filter(AgentAction.user_id == current_user.id, AgentAction.action_type == "comment_post")
        .order_by(AgentAction.created_at.desc())
        .first()
    )
    if latest and interval_ms > 0 and now - (latest.created_at or 0) < interval_ms:
        return {"actions": [], "published_count": 0, "draft_count": 0, "skipped_reason": "距离上次回复太近，已按频率限制跳过"}

    matches = list_matches(db, current_user.id)
    actions: list[dict] = []
    published_count = 0
    draft_count = 0
    for match in matches:
        if len(actions) >= safe_limit or today_count + len(actions) >= daily_limit:
            break
        if int(match.get("match_score") or 0) < min_score:
            continue
        post = match.get("post") or {}
        post_id = post.get("id") or match.get("post_id")
        if not post_id or not post.get("allow_agent_reply", True):
            continue
        existing = (
            db.query(AgentAction)
            .filter(
                AgentAction.user_id == current_user.id,
                AgentAction.action_type == "comment_post",
                AgentAction.target_id == post_id,
                AgentAction.status.in_(["draft", "published"]),
            )
            .first()
        )
        if existing:
            continue
        action = await create_plaza_comment_draft(
            db,
            current_user,
            post_id,
            input_context_extra={
                "auto_surf": True,
                "match_id": match.get("id"),
                "match_score": match.get("match_score"),
                "match_reasons": match.get("match_reasons", []),
            },
        )
        if "auto_approve_comment" in enabled_actions:
            action = approve_action(db, current_user.id, action["id"])
            published_count += 1
        else:
            draft_count += 1
        actions.append(action)

    skipped = "" if actions else "没有找到达到兴趣阈值且未回复过的帖子"
    return {
        "actions": actions,
        "published_count": published_count,
        "draft_count": draft_count,
        "skipped_reason": skipped,
    }


# ==================== 分身侧写 ====================

def _profile_to_dict(p: AvatarProfile) -> dict:
    """AvatarProfile ORM → 响应字典"""
    return {
        "summary": p.summary or "",
        "diary_count": p.diary_count or 0,
        "chat_count": p.chat_count or 0,
        "generated_at": p.generated_at or 0,
    }


def _card_to_dict(card: AvatarCard) -> dict:
    return {
        "display_name": card.display_name or "",
        "public_summary": card.public_summary or "",
        "interest_tags": _decode(card.interest_tags, []),
        "social_intent": _decode(card.social_intent, []),
        "conversation_style": _decode(card.conversation_style, {}),
        "boundaries": _decode(card.boundaries, []),
        "visibility": card.visibility or "private",
        "updated_at": card.updated_at or 0,
    }


def _action_to_dict(action: AgentAction) -> dict:
    return {
        "id": action.id,
        "action_type": action.action_type or "",
        "target_type": action.target_type or "",
        "target_id": action.target_id or "",
        "input_context": _decode(action.input_context, {}),
        "output_text": action.output_text or "",
        "status": action.status or "draft",
        "created_at": action.created_at or 0,
        "updated_at": action.updated_at or 0,
    }


def get_profile(db: Session, user_id: str) -> dict:
    """获取分身侧写，不存在返回默认空侧写"""
    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    if not profile:
        return {"summary": "", "diary_count": 0, "chat_count": 0, "generated_at": 0}
    return _profile_to_dict(profile)


def get_avatar_card(db: Session, user_id: str) -> dict:
    """获取分身名片，不存在返回空名片。"""
    card = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    if not card:
        return {
            "display_name": "",
            "public_summary": "",
            "interest_tags": [],
            "social_intent": [],
            "conversation_style": {},
            "boundaries": [],
            "visibility": "private",
            "updated_at": 0,
        }
    return _card_to_dict(card)


def regenerate_avatar_card(db: Session, user_id: str) -> dict:
    """基于当前画像和结构化记忆生成一个保守的分身名片。"""
    user = db.query(User).filter(User.id == user_id).first()
    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    facts = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user_id, MemoryFact.is_active == True)  # noqa: E712
        .order_by(MemoryFact.is_pinned.desc(), MemoryFact.updated_at.desc())
        .limit(50)
        .all()
    )
    interests = []
    boundaries = []
    intents = []
    for fact in facts:
        text = (fact.content or "").strip()
        if not text:
            continue
        if fact.category in {"interest", "preference", "habit"} and len(interests) < 12:
            interests.append(text[:24])
        elif fact.category == "boundary" and len(boundaries) < 6:
            boundaries.append(text[:60])
        elif fact.category == "need" and len(intents) < 6:
            intents.append(text[:40])

    summary = (profile.summary if profile else "") or ""
    public_summary = summary[:160] if summary else "这个分身还在学习主人的兴趣和社交偏好。"
    now = _now_ms()
    card = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    if not card:
        card = AvatarCard(
            id=str(uuid4()),
            user_id=user_id,
            display_name=f"{(user.name or user.username) if user else '我'}的分身",
            public_summary=public_summary,
            interest_tags=_encode(interests),
            social_intent=_encode(intents),
            conversation_style=_encode({"tone": "自然、友善、低压力"}),
            boundaries=_encode(boundaries),
            visibility="private",
            updated_at=now,
        )
        db.add(card)
    else:
        card.display_name = card.display_name or f"{(user.name or user.username) if user else '我'}的分身"
        card.public_summary = public_summary
        card.interest_tags = _encode(interests)
        card.social_intent = _encode(intents)
        card.conversation_style = _encode({"tone": "自然、友善、低压力"})
        card.boundaries = _encode(boundaries)
        card.updated_at = now
    db.commit()
    db.refresh(card)
    return _card_to_dict(card)


async def regenerate_profile(db: Session, user_id: str) -> dict:
    """重新生成分身侧写：读取记忆+日记+聊天 → 调用 AI 生成摘要"""
    from app.models.diary import Diary
    from app.models.chat import ChatMessage
    from app.models.memory import MemoryDocument
    from app.ai.minimax_client import get_minimax_client

    # 收集用户记忆
    memories = (
        db.query(AvatarMemory)
        .filter(AvatarMemory.user_id == user_id, AvatarMemory.is_active == True)  # noqa: E712
        .order_by(AvatarMemory.created_at.desc())
        .limit(50)
        .all()
    )
    memory_text = "\n".join([
        f"- [{m.category}] {m.content}" for m in memories
    ]) if memories else "暂无记忆"

    # 统一记忆系统中的相关原文证据，优先作为新侧写依据。
    try:
        from app.memory.prompts import format_memory_context
        from app.memory.retriever import retrieve_memories

        retrieved_memories = retrieve_memories(
            db,
            user_id=user_id,
            query="用户的性格 兴趣 生活习惯 社交偏好 写作风格 近期状态",
            scenario="profile_generation",
            top_k=30,
            source_types=["diary", "chat_session", "plaza_post", "plaza_comment", "social_message", "material"],
        )
        retrieved_memory_text = format_memory_context(retrieved_memories, scenario="profile_generation")
    except Exception:
        retrieved_memory_text = ""

    # 收集近期日记（最近 10 篇）
    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user_id)
        .order_by(Diary.created_at.desc())
        .limit(10)
        .all()
    )
    diary_count = len(diaries)
    diary_text = "\n".join([
        f"- {d.title or '无标题'}: {(d.content or '')[:100]}" for d in diaries
    ]) if diaries else "暂无日记"

    # 收集近期聊天（最近 30 条）
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.role == "user")
        .order_by(ChatMessage.timestamp.desc())
        .limit(30)
        .all()
    )
    chat_count = len(messages)
    chat_text = "\n".join([
        f"- {msg.content[:80]}" for msg in messages
    ]) if messages else "暂无对话"
    memory_doc_count = (
        db.query(MemoryDocument)
        .filter(MemoryDocument.user_id == user_id, MemoryDocument.is_deleted == False)  # noqa: E712
        .count()
    )

    # 调用 AI 生成侧写
    system_prompt = (
        "你是一个用户画像分析师。根据用户的记忆库、日记摘要和聊天记录，"
        "生成一段简洁的人格侧写（150-300字），描述用户的性格特征、兴趣爱好、"
        "社交偏好和生活习惯。语言要自然温暖，像朋友之间的了解。"
    )
    user_prompt = (
        f"【统一长期记忆检索结果】\n{retrieved_memory_text or '暂无长期记忆检索结果'}\n\n"
        f"【手动/结构化记忆库】\n{memory_text}\n\n"
        f"【近期日记摘要】\n{diary_text}\n\n"
        f"【近期聊天内容】\n{chat_text}\n\n"
        "请基于以上信息生成用户人格侧写："
    )

    client = get_minimax_client()
    summary = await client.chat_completion(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.7,
    )

    # 写入/更新 avatar_profiles 表
    now = _now_ms()
    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    if profile:
        profile.summary = summary
        profile.diary_count = diary_count
        profile.chat_count = chat_count or memory_doc_count
        profile.generated_at = now
    else:
        profile = AvatarProfile(
            id=str(uuid4()),
            user_id=user_id,
            summary=summary,
            diary_count=diary_count,
            chat_count=chat_count or memory_doc_count,
            generated_at=now,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)
    return _profile_to_dict(profile)

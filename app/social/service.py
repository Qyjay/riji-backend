# app/social/service.py
# 社交模块业务逻辑
import json
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.social import Match, SocialMessage
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_ERROR


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _match_to_dict(m: Match) -> dict:
    return {
        "id": m.id,
        "user_id": m.user_id,
        "target_id": m.target_id,
        "common_tags": json.loads(m.common_tags) if m.common_tags else [],
        "status": m.status,
        "match_type": m.match_type or "long_term",
        "match_report": m.match_report or "",
        "created_at": m.created_at,
    }


def list_matches(db: Session, user_id: str) -> dict:
    """获取当前用户的所有匹配（含已接受/待处理）"""
    matches = db.query(Match).filter(
        (Match.user_id == user_id) | (Match.target_id == user_id)
    ).order_by(Match.created_at.desc()).all()
    return {"items": [_match_to_dict(m) for m in matches], "total": len(matches)}


async def get_match_report(db: Session, user_id: str, match_id: str) -> dict:
    """获取/生成 AI 匹配报告"""
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    if m.user_id != user_id and m.target_id != user_id:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)

    if m.match_report:
        return {"report": m.match_report}

    from app.models.user_profile import UserProfile
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    other_id = m.target_id if m.user_id == user_id else m.user_id
    profile_a = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    profile_b = db.query(UserProfile).filter(UserProfile.user_id == other_id).first()

    def _profile_dict(p) -> dict:
        if not p:
            return {}
        return {
            "personality": p.personality or "",
            "interests": json.loads(p.interests) if p.interests else [],
        }

    report = await client.generate_match_report(_profile_dict(profile_a), _profile_dict(profile_b))
    m.match_report = report
    db.commit()
    return {"report": report}


def create_match_request(
    db: Session, user_id: str, target_id: str, match_type: str, common_tags: list
) -> dict:
    """向目标用户发起匹配申请"""
    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    existing = db.query(Match).filter(
        ((Match.user_id == user_id) & (Match.target_id == target_id)) |
        ((Match.user_id == target_id) & (Match.target_id == user_id))
    ).first()
    if existing:
        raise ApiException(code=PARAM_ERROR, message="已存在匹配请求", status_code=400)

    m = Match(
        id=_uuid(),
        user_id=user_id,
        target_id=target_id,
        common_tags=json.dumps(common_tags, ensure_ascii=False),
        status="pending",
        match_type=match_type,
        created_at=_now_ms(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _match_to_dict(m)


def respond_match(db: Session, user_id: str, match_id: str, accept: bool) -> dict:
    """接受或拒绝匹配申请"""
    m = db.query(Match).filter(Match.id == match_id, Match.target_id == user_id).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="匹配请求不存在", status_code=404)

    m.status = "accepted" if accept else "rejected"
    db.commit()
    db.refresh(m)
    return _match_to_dict(m)


def apply_buddy(db: Session, user_id: str, target_id: str, reason: str = "") -> dict:
    """发起短期搭子申请"""
    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    m = Match(
        id=_uuid(),
        user_id=user_id,
        target_id=target_id,
        common_tags=json.dumps([], ensure_ascii=False),
        status="pending",
        match_type="buddy",
        match_report=reason,
        created_at=_now_ms(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _match_to_dict(m)


def respond_buddy(db: Session, user_id: str, match_id: str, accept: bool) -> dict:
    """同意或拒绝搭子申请"""
    m = db.query(Match).filter(
        Match.id == match_id,
        Match.target_id == user_id,
        Match.match_type == "buddy",
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="搭子申请不存在", status_code=404)

    m.status = "accepted" if accept else "rejected"
    db.commit()
    db.refresh(m)
    return _match_to_dict(m)


def get_messages(db: Session, user_id: str, match_id: str) -> dict:
    """获取指定匹配的聊天记录"""
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    if m.user_id != user_id and m.target_id != user_id:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)

    messages = (
        db.query(SocialMessage)
        .filter(SocialMessage.match_id == match_id)
        .order_by(SocialMessage.timestamp.asc())
        .all()
    )
    return {
        "items": [
            {
                "id": msg.id,
                "match_id": msg.match_id,
                "from_uid": msg.from_uid,
                "content": msg.content,
                "timestamp": msg.timestamp,
            }
            for msg in messages
        ],
        "total": len(messages),
    }

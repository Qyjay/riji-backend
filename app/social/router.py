"""
社交模块路由 v2
prefix="/api/social", tags=["社交"]
"""
import json
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.social import Match, SocialMessage
from app.response import ok, ApiException, NOT_FOUND, PARAM_ERROR

router = APIRouter(prefix="/social", tags=["社交"])


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


class MatchRequest(BaseModel):
    target_id: str
    match_type: str = "long_term"   # "long_term" | "buddy"
    common_tags: list = []


class MatchActionRequest(BaseModel):
    accept: bool


class BuddyRequest(BaseModel):
    target_id: str
    reason: str = ""


class SendMessageRequest(BaseModel):
    match_id: str
    content: str


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


@router.get("/matches", summary="匹配推荐列表")
def list_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的所有匹配（含已接受/待处理）"""
    matches = db.query(Match).filter(
        (Match.user_id == current_user.id) | (Match.target_id == current_user.id)
    ).order_by(Match.created_at.desc()).all()
    return ok({"items": [_match_to_dict(m) for m in matches], "total": len(matches)})


@router.get("/matches/{match_id}/report", summary="AI 匹配报告")
async def get_match_report(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取/生成 AI 匹配报告"""
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    if m.user_id != current_user.id and m.target_id != current_user.id:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)

    # 如果已有报告直接返回
    if m.match_report:
        return ok({"report": m.match_report})

    # 生成报告
    from app.models.user_profile import UserProfile
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    other_id = m.target_id if m.user_id == current_user.id else m.user_id
    profile_a = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
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
    return ok({"report": report})


@router.post("/match-requests", summary="发起匹配")
def create_match_request(
    body: MatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """向目标用户发起匹配申请"""
    # 检查目标用户存在
    target = db.query(User).filter(User.id == body.target_id).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    # 检查是否已存在匹配
    existing = db.query(Match).filter(
        ((Match.user_id == current_user.id) & (Match.target_id == body.target_id)) |
        ((Match.user_id == body.target_id) & (Match.target_id == current_user.id))
    ).first()
    if existing:
        raise ApiException(code=PARAM_ERROR, message="已存在匹配请求", status_code=400)

    m = Match(
        id=_uuid(),
        user_id=current_user.id,
        target_id=body.target_id,
        common_tags=json.dumps(body.common_tags, ensure_ascii=False),
        status="pending",
        match_type=body.match_type,
        created_at=_now_ms(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return ok(_match_to_dict(m))


@router.post("/match-requests/{match_id}/respond", summary="接受/拒绝匹配")
def respond_match_request(
    match_id: str,
    body: MatchActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """接受或拒绝匹配申请"""
    m = db.query(Match).filter(Match.id == match_id, Match.target_id == current_user.id).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="匹配请求不存在", status_code=404)

    m.status = "accepted" if body.accept else "rejected"
    db.commit()
    db.refresh(m)
    return ok(_match_to_dict(m))


@router.post("/buddy", summary="短期搭子申请")
def apply_buddy(
    body: BuddyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发起短期搭子申请"""
    target = db.query(User).filter(User.id == body.target_id).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    m = Match(
        id=_uuid(),
        user_id=current_user.id,
        target_id=body.target_id,
        common_tags=json.dumps([], ensure_ascii=False),
        status="pending",
        match_type="buddy",
        match_report=body.reason,
        created_at=_now_ms(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return ok(_match_to_dict(m))


@router.post("/buddy/{match_id}/respond", summary="同意/拒绝搭子")
def respond_buddy(
    match_id: str,
    body: MatchActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """同意或拒绝搭子申请"""
    m = db.query(Match).filter(
        Match.id == match_id,
        Match.target_id == current_user.id,
        Match.match_type == "buddy",
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="搭子申请不存在", status_code=404)

    m.status = "accepted" if body.accept else "rejected"
    db.commit()
    db.refresh(m)
    return ok(_match_to_dict(m))


@router.get("/messages/{match_id}", summary="聊天记录")
def get_messages(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定匹配的聊天记录"""
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    if m.user_id != current_user.id and m.target_id != current_user.id:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)

    messages = (
        db.query(SocialMessage)
        .filter(SocialMessage.match_id == match_id)
        .order_by(SocialMessage.timestamp.asc())
        .all()
    )
    return ok({
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
    })

"""
社交模块路由 v2
prefix="/api/social", tags=["社交"]
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import ok
from app.social import service

router = APIRouter(prefix="/social", tags=["社交"])


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


@router.get("/matches", summary="匹配推荐列表")
def list_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的所有匹配（含已接受/待处理）"""
    return ok(service.list_matches(db, current_user.id))


@router.get("/matches/{match_id}/report", summary="AI 匹配报告")
async def get_match_report(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取/生成 AI 匹配报告"""
    return ok(await service.get_match_report(db, current_user.id, match_id))


@router.post("/match-requests", summary="发起匹配")
def create_match_request(
    body: MatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """向目标用户发起匹配申请"""
    return ok(service.create_match_request(
        db, current_user.id, body.target_id, body.match_type, body.common_tags
    ))


@router.post("/match-requests/{match_id}/respond", summary="接受/拒绝匹配")
def respond_match_request(
    match_id: str,
    body: MatchActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """接受或拒绝匹配申请"""
    return ok(service.respond_match(db, current_user.id, match_id, body.accept))


@router.post("/buddy", summary="短期搭子申请")
def apply_buddy(
    body: BuddyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发起短期搭子申请"""
    return ok(service.apply_buddy(db, current_user.id, body.target_id, body.reason))


@router.post("/buddy/{match_id}/respond", summary="同意/拒绝搭子")
def respond_buddy(
    match_id: str,
    body: MatchActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """同意或拒绝搭子申请"""
    return ok(service.respond_buddy(db, current_user.id, match_id, body.accept))


@router.get("/messages/{match_id}", summary="聊天记录")
def get_messages(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定匹配的聊天记录"""
    return ok(service.get_messages(db, current_user.id, match_id))

"""
社交模块路由
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.social.schemas import (
    MatchRequestBody, RespondRequest, BuddyRequest,
    MatchOut, MatchRequestOut, MessageOut, MatchReportOut, BuddyRequestOut,
    SendMessageBody,
)
from app.social import service

router = APIRouter(prefix="/social", tags=["社交"])


@router.get("/matches", summary="已匹配列表（裸数组）")
def list_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取已接受的匹配列表，返回裸数组"""
    matches = service.list_matches(db, current_user.id)
    result = [MatchOut(**match).model_dump(by_alias=True) for match in matches]
    return success(result)


@router.post("/match-requests", summary="发送匹配请求")
def create_match_request(
    body: MatchRequestBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """向目标用户发起匹配申请"""
    match = service.create_match_request(db, current_user.id, body.toUid)

    out = MatchRequestOut(
        id=match.id,
        from_uid=match.user_id,
        to_uid=match.target_id,
        status=match.status,
        created_at=match.created_at,
    )
    return success(out.model_dump(by_alias=True))


@router.get("/messages/{match_id}", summary="匹配消息（裸数组）")
def get_messages(
    match_id: str,
    limit: int = Query(50, ge=1, le=200, description="获取条数"),
    before: Optional[str] = Query(None, description="此消息 ID 之前的消息"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定匹配的聊天记录，返回裸数组"""
    messages = service.get_messages(db, current_user.id, match_id, limit=limit, before=before)

    result = [
        MessageOut(
            id=msg.id,
            match_id=msg.match_id,
            from_uid=msg.from_uid,
            content=msg.content,
            timestamp=msg.timestamp,
        ).model_dump(by_alias=True)
        for msg in reversed(messages)
    ]
    return success(result)


@router.post("/messages/{match_id}", summary="发送消息")
def send_message(
    match_id: str,
    body: SendMessageBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """向已通过的匹配对象发送消息"""
    message = service.send_message(db, current_user.id, match_id, body.content)
    out = MessageOut(
        id=message.id,
        match_id=message.match_id,
        from_uid=message.from_uid,
        content=message.content,
        timestamp=message.timestamp,
    )
    return success(out.model_dump(by_alias=True))


@router.get("/matches/{match_id}/report", summary="匹配报告")
async def get_match_report(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取/生成 AI 匹配报告"""
    report = await service.get_match_report(db, current_user.id, match_id)
    out = MatchReportOut(**report)
    return success(out.model_dump(by_alias=True))


@router.post("/match-requests/{request_id}/respond", summary="响应匹配请求")
def respond_match_request(
    request_id: str,
    body: RespondRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """接受或拒绝匹配申请"""
    service.respond_match_request(db, current_user.id, request_id, body.accept)
    return success(None)


@router.post("/buddy", summary="申请搭子")
def apply_buddy(
    body: BuddyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发起短期搭子申请"""
    match = service.apply_buddy(db, current_user.id, body.target_user_id, body.reason)

    out = BuddyRequestOut(
        id=match.id,
        from_uid=match.user_id,
        to_uid=match.target_id,
        reason=body.reason,
        status=match.status,
        created_at=match.created_at,
    )
    return success(out.model_dump(by_alias=True))


@router.post("/buddy/{request_id}/respond", summary="响应搭子申请")
def respond_buddy(
    request_id: str,
    body: RespondRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """同意或拒绝搭子申请"""
    service.respond_buddy(db, current_user.id, request_id, body.accept)
    return success(None)

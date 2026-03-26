"""
社交模块路由
"""
import json
import time
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.social import Match, SocialMessage
from app.response import success, ApiException, NOT_FOUND, PARAM_ERROR
from app.social.schemas import (
    MatchRequestBody, RespondRequest, BuddyRequest,
    MatchOut, MatchRequestOut, MessageOut, MatchReportOut, BuddyRequestOut,
)
from app.social import service

router = APIRouter(prefix="/social", tags=["社交"])


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


@router.get("/matches", summary="已匹配列表（裸数组）")
def list_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取已接受的匹配列表，返回裸数组"""
    matches = db.query(Match).filter(
        ((Match.user_id == current_user.id) | (Match.target_id == current_user.id)),
        Match.status == "accepted",
    ).order_by(Match.created_at.desc()).all()

    result = []
    for m in matches:
        out = service.match_to_out(m, current_user.id, db)
        result.append(MatchOut(**out).model_dump(by_alias=True))
    return success(result)


@router.post("/match-requests", summary="发送匹配请求")
def create_match_request(
    body: MatchRequestBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """向目标用户发起匹配申请"""
    target_uid = body.toUid
    if not target_uid:
        raise ApiException(code=PARAM_ERROR, message="toUid 不能为空", status_code=400)

    target = db.query(User).filter(User.id == target_uid).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    existing = db.query(Match).filter(
        ((Match.user_id == current_user.id) & (Match.target_id == target_uid)) |
        ((Match.user_id == target_uid) & (Match.target_id == current_user.id))
    ).first()
    if existing:
        raise ApiException(code=PARAM_ERROR, message="已存在匹配请求", status_code=400)

    m = Match(
        id=_uuid(),
        user_id=current_user.id,
        target_id=target_uid,
        common_tags=json.dumps([], ensure_ascii=False),
        status="pending",
        match_type="long_term",
        created_at=_now_ms(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)

    out = MatchRequestOut(
        id=m.id,
        from_uid=m.user_id,
        to_uid=m.target_id,
        status=m.status,
        created_at=m.created_at,
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
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    if m.user_id != current_user.id and m.target_id != current_user.id:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)

    query = db.query(SocialMessage).filter(SocialMessage.match_id == match_id)
    if before:
        # 游标分页：取 before 消息之前的
        pivot = db.query(SocialMessage).filter(SocialMessage.id == before).first()
        if pivot:
            query = query.filter(SocialMessage.timestamp < pivot.timestamp)
    messages = query.order_by(SocialMessage.timestamp.desc()).limit(limit).all()

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


@router.get("/matches/{match_id}/report", summary="匹配报告")
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

    # 如果已有报告，解析返回
    if m.match_report:
        try:
            cached = json.loads(m.match_report)
            if isinstance(cached, dict) and "compatibility" in cached:
                return success(MatchReportOut(**cached).model_dump(by_alias=True))
        except Exception:
            pass

    from app.models.user_profile import UserProfile
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    other_id = service.get_other_user_id(m, current_user.id)
    profile_a = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    profile_b = db.query(UserProfile).filter(UserProfile.user_id == other_id).first()

    def _profile_dict(p) -> dict:
        if not p:
            return {}
        return {
            "personality": p.personality or "",
            "interests": json.loads(p.interests) if p.interests else [],
        }

    # generate_match_report 返回的是文本，我们需要结构化
    if client.mock:
        report_data = {
            "compatibility": 85,
            "analysis": "你们有很多共同点，在学习和生活方式上非常契合！",
            "common_points": ["都喜欢记录生活", "学习态度积极", "兴趣爱好相近"],
            "differences": ["作息时间略有差异", "对社交的需求程度不同"],
        }
    else:
        raw_report = await client.generate_match_report(_profile_dict(profile_a), _profile_dict(profile_b))
        import re
        try:
            json_match = re.search(r'\{.*\}', raw_report, re.DOTALL)
            if json_match:
                report_data = json.loads(json_match.group())
            else:
                report_data = {
                    "compatibility": 75,
                    "analysis": raw_report[:200] if raw_report else "匹配度较高，有共同语言。",
                    "common_points": ["有共同兴趣"],
                    "differences": ["性格略有差异"],
                }
        except Exception:
            report_data = {
                "compatibility": 75,
                "analysis": "你们有不少共同点，值得深入交流！",
                "common_points": ["有共同兴趣"],
                "differences": ["性格略有差异"],
            }

    # 缓存报告
    m.match_report = json.dumps(report_data, ensure_ascii=False)
    db.commit()

    out = MatchReportOut(
        compatibility=report_data.get("compatibility", 75),
        analysis=report_data.get("analysis", ""),
        common_points=report_data.get("common_points", report_data.get("commonPoints", [])),
        differences=report_data.get("differences", []),
    )
    return success(out.model_dump(by_alias=True))


@router.post("/match-requests/{request_id}/respond", summary="响应匹配请求")
def respond_match_request(
    request_id: str,
    body: RespondRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """接受或拒绝匹配申请"""
    m = db.query(Match).filter(Match.id == request_id, Match.target_id == current_user.id).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="匹配请求不存在", status_code=404)

    m.status = "accepted" if body.accept else "rejected"
    db.commit()
    return success(None)


@router.post("/buddy", summary="申请搭子")
def apply_buddy(
    body: BuddyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发起短期搭子申请"""
    target = db.query(User).filter(User.id == body.target_user_id).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    m = Match(
        id=_uuid(),
        user_id=current_user.id,
        target_id=body.target_user_id,
        common_tags=json.dumps([], ensure_ascii=False),
        status="pending",
        match_type="buddy",
        match_report=body.reason,
        created_at=_now_ms(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)

    out = BuddyRequestOut(
        id=m.id,
        from_uid=m.user_id,
        to_uid=m.target_id,
        reason=body.reason,
        status=m.status,
        created_at=m.created_at,
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
    m = db.query(Match).filter(
        Match.id == request_id,
        Match.target_id == current_user.id,
        Match.match_type == "buddy",
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="搭子申请不存在", status_code=404)

    m.status = "accepted" if body.accept else "rejected"
    db.commit()
    return success(None)

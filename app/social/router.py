"""
社交模块路由
恢复至之前版本代码
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.social.schemas import (
    BuddyRequest,
    BuddyRequestOut,
    ActivityRoomOut,
    CreateMissionRequest,
    MatchOut,
    MatchReportOut,
    MatchRequestBody,
    MatchRequestOut,
    MessageOut,
    MissionCandidateOut,
    MissionOut,
    MissionParseOut,
    MissionPostDraftOut,
    MissionProbeOut,
    MissionSearchOut,
    ParseMissionRequest,
    PublishMissionPostRequest,
    RespondRequest,
    SendMessageBody,
    UpdateMissionRequest,
)
from app.social import mission_service, service


router = APIRouter(prefix="/social", tags=["社交"])


def _serialize_mission(data: dict) -> dict:
    return MissionOut(**data).model_dump(by_alias=True)


def _serialize_candidate(data: dict) -> dict:
    return MissionCandidateOut(**data).model_dump(by_alias=True)


def _serialize_search(data: dict) -> dict:
    payload = {
        **data,
        "mission": MissionOut(**data["mission"]),
        "candidates": [MissionCandidateOut(**item) for item in data["candidates"]],
    }
    return MissionSearchOut(**payload).model_dump(by_alias=True)


@router.post("/missions/parse", summary="解析自然语言找人目的")
def parse_mission(
    body: ParseMissionRequest,
    current_user: User = Depends(get_current_user),
):
    """把一句话整理成可编辑的短期/长期找人任务，不直接开始搜索。"""
    result = mission_service.parse_mission_text(body.text, current_user)
    return success(MissionParseOut(**result).model_dump(by_alias=True))


@router.post("/missions", summary="创建找人任务")
def create_mission(
    body: CreateMissionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.create_mission(db, current_user, body.model_dump())
    return success(_serialize_mission(result))


@router.get("/missions", summary="找人任务列表")
def list_missions(
    status: Optional[str] = Query(None, description="按任务状态筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = mission_service.list_missions(db, current_user.id, status)
    return success([_serialize_mission(item) for item in items])


@router.get("/missions/{mission_id}", summary="找人任务详情")
def get_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(_serialize_mission(
        mission_service.get_mission(db, current_user.id, mission_id)
    ))


@router.patch("/missions/{mission_id}", summary="修改找人任务")
def update_mission(
    mission_id: str,
    body: UpdateMissionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    result = mission_service.update_mission(db, current_user, mission_id, data)
    return success(_serialize_mission(result))


@router.post("/missions/{mission_id}/start", summary="确认授权并开始寻找")
def start_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.start_mission(db, current_user, mission_id)
    return success(_serialize_search(result))


@router.post("/missions/{mission_id}/search", summary="定向搜索任务候选")
def search_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.search_mission(db, current_user, mission_id)
    return success(_serialize_search(result))


@router.post("/missions/{mission_id}/pause", summary="暂停找人任务")
def pause_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.set_mission_status(db, current_user.id, mission_id, "pause")
    return success(_serialize_mission(result))


@router.post("/missions/{mission_id}/resume", summary="恢复找人任务")
def resume_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.set_mission_status(db, current_user.id, mission_id, "resume")
    return success(_serialize_mission(result))


@router.post("/missions/{mission_id}/close", summary="关闭找人任务")
def close_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.set_mission_status(db, current_user.id, mission_id, "close")
    return success(_serialize_mission(result))


@router.delete("/missions/{mission_id}", summary="删除找人任务")
def delete_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mission_service.delete_mission(db, current_user.id, mission_id)
    return success(None)


@router.get("/missions/{mission_id}/candidates", summary="任务候选列表")
def list_mission_candidates(
    mission_id: str,
    status: Optional[str] = Query(None, description="按候选状态筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = mission_service.list_candidates(db, current_user.id, mission_id, status)
    return success([_serialize_candidate(item) for item in items])


@router.post("/missions/{mission_id}/candidates/{candidate_id}/probe", summary="让分身核验任务候选")
async def probe_mission_candidate(
    mission_id: str,
    candidate_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = await mission_service.probe_candidate(
        db, current_user, mission_id, candidate_id
    )
    return success(MissionProbeOut(
        candidate=MissionCandidateOut(**result["candidate"]),
        interaction_id=result["interaction_id"],
        session_id=result["session_id"],
    ).model_dump(by_alias=True))


@router.post("/missions/{mission_id}/candidates/{candidate_id}/skip", summary="跳过任务候选")
def skip_mission_candidate(
    mission_id: str,
    candidate_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.skip_candidate(
        db, current_user.id, mission_id, candidate_id
    )
    return success(_serialize_candidate(result))


@router.post("/missions/{mission_id}/post-draft", summary="生成任务招募帖草稿")
def create_mission_post_draft(
    mission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.build_post_draft(db, current_user.id, mission_id)
    return success(MissionPostDraftOut(**result).model_dump(by_alias=True))


@router.post("/missions/{mission_id}/publish", summary="确认并发布任务招募帖")
def publish_mission_post(
    mission_id: str,
    body: PublishMissionPostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = mission_service.publish_mission_post(
        db, current_user, mission_id, body.model_dump()
    )
    from app.plaza.schemas import PlazaPostOut

    return success(PlazaPostOut(**result).model_dump(by_alias=True))


@router.get("/matches", summary="已匹配列表（裸数组）")
def list_matches(
    include_pending: bool = Query(
        False,
        description="为 true 时返回 accepted 与 pending（含分身 start-chat 未通过的搭子申请）；默认仅 accepted",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取匹配列表：默认仅已接受；可带 include_pending 查看待处理搭子/匹配"""
    matches = service.list_matches(db, current_user.id, include_pending=include_pending)
    result = [MatchOut(**match).model_dump(by_alias=True) for match in matches]
    return success(result)


@router.get("/activity-rooms/{match_id}", summary="短期搭子活动房间")
def get_activity_room(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = service.get_activity_room(db, current_user.id, match_id)
    return success(ActivityRoomOut(**result).model_dump(by_alias=True))


@router.post("/activity-rooms/{match_id}/complete", summary="确认活动已完成")
def complete_activity_room(
    match_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = service.complete_activity_room(db, current_user.id, match_id)
    return success(ActivityRoomOut(**result).model_dump(by_alias=True))


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

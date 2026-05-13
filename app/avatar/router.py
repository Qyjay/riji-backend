"""
AI 分身模块路由
prefix="/api/avatar", tags=["AI分身"]
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user
from app.database import get_db
from app.models.avatar import AvatarMatch
from app.models.plaza import PlazaPost
from app.models.user import User
from app.response import success
from app.avatar import schemas, service
from app.social import service as social_service
from app.avatar.schemas import (
    AgentActionOut,
    AtoaSessionOut,
    AutoSurfResultOut,
    AvatarCardOut,
    AvatarMemoryOut,
    AvatarProfileOut,
    AvatarStatusOut,
    ContinueAtoaChatResultOut,
    DecideAtoaRequest,
    DecideAtoaResultOut,
    MatchActionRequest,
    MutualMatchItemOut,
    ProbeLogItemOut,
    SurfLogsOut,
    TriggerSurfResultOut,
    UsageEventOut,
)

router = APIRouter(prefix="/avatar", tags=["AI分身"])


def _serialize_memory(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarMemoryOut(**d).model_dump(by_alias=True)


def _serialize_status(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarStatusOut(**d).model_dump(by_alias=True)


def _serialize_profile(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarProfileOut(**d).model_dump(by_alias=True)


def _serialize_card(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarCardOut(**d).model_dump(by_alias=True)


def _serialize_action(d: dict) -> dict:
    """转 camelCase 输出"""
    return AgentActionOut(**d).model_dump(by_alias=True)


def _serialize_auto_surf_result(d: dict) -> dict:
    return AutoSurfResultOut(**d).model_dump(by_alias=True)


def _serialize_usage_event(d: dict) -> dict:
    return UsageEventOut(**d).model_dump(by_alias=True)


def _serialize_surf_logs(d: dict) -> dict:
    return SurfLogsOut(**d).model_dump(by_alias=True)


@router.get("/matches", summary="分身推荐列表（旧版兼容）")
def list_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兼容旧前端的分身推荐接口。"""
    return success(service.list_matches(db, current_user.id, refresh=False))


@router.post("/matches/{match_id}/action", summary="分身推荐操作（旧版兼容）")
def handle_match_action(
    match_id: str,
    body: MatchActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兼容旧前端的推荐操作：dismiss / chat。"""
    match = db.query(AvatarMatch).filter(
        AvatarMatch.id == match_id,
        AvatarMatch.user_id == current_user.id,
    ).first()
    if not match:
        raise service.ApiException(code=service.NOT_FOUND, message="推荐不存在", status_code=404)

    if body.action == "dismiss":
        match.status = "dismissed"
        db.commit()
        return success(None)

    if body.action == "chat":
        target_user_id = match.target_user_id
        if not target_user_id:
            post = db.query(PlazaPost).filter(PlazaPost.id == match.post_id).first()
            target_user_id = post.user_id if post else None
        if not target_user_id:
            raise service.ApiException(code=service.PARAM_INVALID, message="无法找到推荐对象", status_code=400)

        social_match = social_service.apply_buddy(db, current_user.id, target_user_id, "")
        match.status = "chatting"
        db.commit()
        return success({"socialMatchId": social_match.id})

    raise service.ApiException(code=service.PARAM_INVALID, message="action 只能是 dismiss 或 chat", status_code=400)


# ==================== 记忆 CRUD ====================

@router.get("/memories", summary="分身记忆列表")
def list_memories(
    category: Optional[str] = Query(None, description="按类别筛选：fact/interest/personality/need/habit/relation"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取分身记忆列表，可按 category 筛选"""
    items = service.list_memories(db, current_user.id, category)
    return success([_serialize_memory(item) for item in items])


@router.post("/memories", summary="添加记忆")
def add_memory(
    body: schemas.AddMemoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动添加一条分身记忆"""
    result = service.add_memory(db, current_user.id, body.model_dump())
    return success(_serialize_memory(result))


@router.put("/memories/{memory_id}", summary="更新记忆")
def update_memory(
    memory_id: str,
    body: schemas.UpdateMemoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新分身记忆字段"""
    result = service.update_memory(
        db, current_user.id, memory_id, body.model_dump(exclude_unset=True)
    )
    return success(_serialize_memory(result))


@router.delete("/memories/{memory_id}", summary="删除记忆")
def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除一条分身记忆"""
    service.delete_memory(db, current_user.id, memory_id)
    return success(None)


# ==================== 分身状态 ====================

@router.get("/status", summary="获取分身状态")
def get_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的分身状态，首次访问自动创建"""
    result = service.get_status(db, current_user.id)
    return success(_serialize_status(result))


@router.put("/status", summary="更新分身状态")
def update_status(
    body: schemas.UpdateStatusRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新分身状态配置"""
    result = service.update_status(
        db, current_user.id, body.model_dump(exclude_unset=True)
    )
    return success(_serialize_status(result))


@router.post("/usage-events", summary="记录 App 使用事件")
def record_usage_event(
    body: schemas.RecordUsageEventRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """聚合用户 App 使用时间与页面习惯，用于生成个性化分身冲浪计划。"""
    result = service.record_usage_event(db, current_user.id, body.model_dump())
    return success(_serialize_usage_event(result))


@router.post("/surf/trigger", summary="【调试】立即触发一次完整分身冲浪（跳过时间窗口限制）")
async def trigger_surf(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    调试专用接口：等价于外部调度脚本 `python scripts/run_avatar_scheduler.py --user <username>`，
    但跳过 next_surf_at 时间窗口检查，可在 Swagger 中随时触发。

    完整执行链路：
    - AtoA 探针通道（Phase 8A）
    - 写入 AvatarSurfLog
    - 更新 last_surf_at / daily_surf_count / next_surf_at
    - Bandit 记录一次 pull（Phase 3）
    """
    from app.models.avatar import AvatarStatus
    # 跳过 next_surf_at 检查：将其置为 0 后再调 service
    status_row = db.query(AvatarStatus).filter(AvatarStatus.user_id == current_user.id).first()
    if status_row:
        status_row.next_surf_at = 0
        db.commit()

    result = await service.run_avatar_surf_for_user(db, current_user.id, trigger="manual")
    out = TriggerSurfResultOut(
        status=result.get("status", "skipped"),
        generated_matches=result.get("generated_matches", 0),
        atoa_scanned=result.get("atoa_scanned", 0),
        atoa_mutual=result.get("atoa_mutual", 0),
        surf_report=result.get("surf_report", ""),
        top10_session_id=result.get("top10_session_id"),
        skipped_reason=result.get("reason", ""),
    )
    return success(out.model_dump(by_alias=True))


@router.get("/surf-logs", summary="分身冲浪日志")
def list_surf_logs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查看分身定时冲浪的执行结果和跳过原因。"""
    result = service.list_surf_logs(db, current_user.id, limit)
    return success(_serialize_surf_logs(result))


# ==================== 分身侧写 ====================

@router.get("/profile", summary="获取分身侧写")
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的分身侧写"""
    result = service.get_profile(db, current_user.id)
    return success(_serialize_profile(result))


@router.post("/profile/regenerate", summary="重新生成侧写")
async def regenerate_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """调用 AI 重新生成分身侧写"""
    result = await service.regenerate_profile(db, current_user.id)
    return success(_serialize_profile(result))


@router.get("/card", summary="获取分身名片")
def get_avatar_card(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户可用于匹配/agent-to-agent 的分身名片"""
    result = service.get_avatar_card(db, current_user.id)
    return success(_serialize_card(result))


@router.post("/card/regenerate", summary="重新生成分身名片")
def regenerate_avatar_card(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """基于画像和结构化记忆重新生成分身名片"""
    result = service.regenerate_avatar_card(db, current_user.id)
    return success(_serialize_card(result))


# ==================== Phase 8A: AtoA 探针监察接口 ====================

@router.get("/probe-log", summary="分身探针日志（我发起的 AtoA 互动）")
def get_probe_log(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    outcome: Optional[str] = Query(None, description="按 outcome 筛选，如 pending_user_decision / blocked / connected"),
    session_id: Optional[str] = Query(None, description="按 AtoaSession ID 筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    默认仅返回 **最近一次成功冲浪** 对应会话中的探针；同一对方用户只保留最新一条。
    传入 `session_id` 可查看指定历史会话（仍按对方用户去重）。
    支持 `outcome` 筛选。
    """
    items = service.get_probe_log(db, current_user.id, limit, offset, outcome, session_id)
    return success([ProbeLogItemOut(**item).model_dump(by_alias=True) for item in items])


@router.get("/atoa/sessions", summary="AtoA 搭子模式会话列表（Phase 8A）")
def get_atoa_sessions(
    limit: int = Query(5, ge=1, le=20),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    仅返回 **最近一次成功冲浪** 对应的 Top-10 会话（0～1 条）；pending/decided 按对方用户去重统计。
    """
    items = service.get_atoa_sessions(db, current_user.id, limit, offset)
    return success([AtoaSessionOut(**item).model_dump(by_alias=True) for item in items])


@router.get("/mutual-matches", summary="AtoA 双向匹配列表")
def get_mutual_matches(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取 AtoA 双向达标的推荐匹配（两个分身都感兴趣的候选）。
    这是 Phase 8 的主推荐入口，优先级高于普通帖子/用户型匹配。
    """
    items = service.get_mutual_matches(db, current_user.id, limit, offset)
    return success([MutualMatchItemOut(**item).model_dump(by_alias=True) for item in items])


@router.post("/atoa/{interaction_id}/continue", summary="继续 AtoA 分身对话（Phase 8B）")
async def continue_atoa_chat(
    interaction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    用户选择「继续聊」后，触发分身续聊 ≤3 轮，追加到现有对话记录。
    返回新增的对话轮次（new_turns）及完整对话（conversation）。
    只有发起方（user_a）可操作；outcome=blocked/connected 时不允许继续。
    """
    result = await service.continue_atoa_conversation(db, current_user.id, interaction_id)
    return success(ContinueAtoaChatResultOut(**result).model_dump(by_alias=True))


@router.post("/atoa/{interaction_id}/decide", summary="AtoA 最终决策（Phase 8C）")
async def decide_atoa(
    interaction_id: str,
    body: DecideAtoaRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    用户对 AtoA 互动做最终决策：
    - decision=block：禁止往下聊，关联推荐 dismissed，对方不可见。
    - decision=connect：结交搭子，发起社交申请，对方可见。
    openingMessage 仅 connect 时有效，留空则使用 AI 开场白。
    """
    result = await service.decide_atoa_outcome(
        db, current_user.id, interaction_id, body.decision, body.opening_message
    )
    return success(DecideAtoaResultOut(**result).model_dump(by_alias=True))


# ==================== 分身行动草稿/审批 ====================

@router.get("/actions", summary="分身行动列表")
def list_actions(
    status: Optional[str] = Query(None, description="按状态筛选：draft/published/rejected"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的分身行动草稿和历史记录。"""
    items = service.list_actions(db, current_user.id, status)
    return success([_serialize_action(item) for item in items])


@router.post("/actions/plaza-comment-draft", summary="生成广场评论草稿")
async def create_plaza_comment_draft(
    body: schemas.CreateAgentCommentDraftRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """基于帖子、侧写和长期记忆生成评论草稿，不会直接发布。"""
    result = await service.create_plaza_comment_draft(db, current_user, body.post_id, body.parent_comment_id)
    return success(_serialize_action(result))


@router.post("/actions/auto-surf", summary="触发一次分身自动冲浪评论")
async def auto_surf_comments(
    body: schemas.AutoSurfRequest = schemas.AutoSurfRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按用户设置的兴趣阈值、频率和上限，让分身自动挑选帖子生成评论。"""
    result = await service.auto_surf_comments(db, current_user, body.limit or 1)
    return success(_serialize_auto_surf_result(result))


@router.post("/actions/{action_id}/approve", summary="批准分身行动")
def approve_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批准草稿并执行分身行动。当前支持发布广场评论。"""
    result = service.approve_action(db, current_user.id, action_id)
    return success(_serialize_action(result))


@router.post("/actions/{action_id}/reject", summary="拒绝分身行动")
def reject_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """拒绝草稿，不执行任何外部发布动作。"""
    result = service.reject_action(db, current_user.id, action_id)
    return success(_serialize_action(result))

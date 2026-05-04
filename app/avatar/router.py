"""
AI 分身模块路由
prefix="/api/avatar", tags=["AI分身"]
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.response import success
from app.avatar import schemas, service
from app.avatar.schemas import (
    AgentActionOut,
    AutoSurfResultOut,
    AvatarCardOut,
    AvatarMemoryOut,
    AvatarMatchOut,
    AvatarProfileOut,
    AvatarStatusOut,
    RebuildMatchesResultOut,
    StartChatRequest,
    StartChatResultOut,
    SurfLogsOut,
    UsageEventOut,
)

router = APIRouter(prefix="/avatar", tags=["AI分身"])


def _serialize_memory(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarMemoryOut(**d).model_dump(by_alias=True)


def _serialize_status(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarStatusOut(**d).model_dump(by_alias=True)


def _serialize_match(d: dict) -> dict:
    """转 camelCase 输出（嵌套 post / target_user 也需要转换）"""
    from app.plaza.schemas import PlazaPostOut
    d = dict(d)
    if "post" in d and isinstance(d["post"], dict):
        d["post"] = PlazaPostOut(**d["post"]).model_dump(by_alias=True)
    return AvatarMatchOut(**d).model_dump(by_alias=True)


def _serialize_rebuild_result(d: dict) -> dict:
    return RebuildMatchesResultOut(**d).model_dump(by_alias=True)


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


@router.get("/surf-logs", summary="分身冲浪日志")
def list_surf_logs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查看分身定时冲浪的执行结果和跳过原因。"""
    result = service.list_surf_logs(db, current_user.id, limit)
    return success(_serialize_surf_logs(result))


# ==================== 分身推荐 ====================

@router.get("/matches", summary="分身推荐列表")
def list_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取分身推荐列表，排除已忽略的，按匹配度降序"""
    items = service.list_matches(db, current_user.id)
    return success([_serialize_match(item) for item in items])


@router.post("/matches/rebuild", summary="重新生成分身推荐（规则召回 + AI精排）")
async def rebuild_avatar_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    主动触发一次完整的分身推荐重建：
    - Phase 5：帖子通道 + 用户通道双路规则宽召回
    - Phase 6：对 top-10 未精排匹配进行 AI 精排，生成自然理由和开场白
    返回本次执行统计摘要。
    """
    result = await service.rebuild_avatar_matches(db, current_user.id)
    return success(_serialize_rebuild_result(result))


@router.post("/matches/{match_id}/action", summary="分身匹配操作")
def match_action(
    match_id: str,
    body: schemas.MatchActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """对推荐匹配执行操作：dismiss（忽略）或 chat（发起聊天）"""
    service.match_action(db, current_user.id, match_id, body.action)
    return success(None)


@router.post("/matches/{match_id}/start-chat", summary="从分身推荐一键发起搭子申请")
def start_chat_from_match(
    match_id: str,
    body: StartChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Phase 7 社交闭环：将分身推荐转化为真实搭子申请。
    - 自动识别目标用户（用户型匹配用 target_user_id，帖子型用帖子作者）
    - 防重复：已有 pending/accepted 申请时直接复用，返回 isDuplicate=true
    - 可选传入 openingMessage 自定义开场白，不传则使用 AI 建议开场白
    - 成功发起后触发 Bandit 最强正向反馈（+10）
    """
    result = service.start_chat_from_match(
        db, current_user.id, match_id, body.opening_message
    )
    return success(StartChatResultOut(**result).model_dump(by_alias=True))


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

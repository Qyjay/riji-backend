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
from app.avatar.schemas import AvatarMemoryOut, AvatarMatchOut, AvatarProfileOut, AvatarStatusOut

router = APIRouter(prefix="/avatar", tags=["AI分身"])


def _serialize_memory(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarMemoryOut(**d).model_dump(by_alias=True)


def _serialize_status(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarStatusOut(**d).model_dump(by_alias=True)


def _serialize_match(d: dict) -> dict:
    """转 camelCase 输出（嵌套 post 也需要转换）"""
    from app.plaza.schemas import PlazaPostOut
    d = dict(d)
    if "post" in d and isinstance(d["post"], dict):
        d["post"] = PlazaPostOut(**d["post"]).model_dump(by_alias=True)
    return AvatarMatchOut(**d).model_dump(by_alias=True)


def _serialize_profile(d: dict) -> dict:
    """转 camelCase 输出"""
    return AvatarProfileOut(**d).model_dump(by_alias=True)


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


# ==================== 分身推荐 ====================

@router.get("/matches", summary="分身推荐列表")
def list_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取分身推荐列表，排除已忽略的，按匹配度降序"""
    items = service.list_matches(db, current_user.id)
    return success([_serialize_match(item) for item in items])


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

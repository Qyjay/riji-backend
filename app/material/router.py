"""
素材管理路由
prefix="/api/materials", tags=["素材管理"]
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.response import ok
from app.material import schemas, service

router = APIRouter(prefix="/materials", tags=["素材管理"])


@router.post("", summary="创建素材")
async def create_material(
    body: schemas.MaterialCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建一条素材记录"""
    result = service.create_material(db, current_user.id, body.model_dump())
    return ok(result)


@router.get("", summary="素材列表")
async def list_materials(
    date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按日期查询素材，不传 date 返回全部"""
    items = service.list_materials(db, current_user.id, date)
    return ok({"items": items, "total": len(items)})


@router.get("/{material_id}", summary="素材详情")
async def get_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单条素材"""
    result = service.get_material(db, current_user.id, material_id)
    return ok(result)


@router.put("/{material_id}", summary="编辑素材")
async def update_material(
    material_id: str,
    body: schemas.MaterialUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新素材字段"""
    result = service.update_material(
        db, current_user.id, material_id, body.model_dump(exclude_unset=True)
    )
    return ok(result)


@router.delete("/{material_id}", summary="删除素材")
async def delete_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除素材"""
    service.delete_material(db, current_user.id, material_id)
    return ok({"deleted": True})


@router.post("/{material_id}/emotion", summary="AI 情绪提取")
async def extract_emotion(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """调用 AI 提取素材情绪，结果写回数据库"""
    result = await service.extract_emotion(db, current_user.id, material_id)
    return ok(result)


@router.post("/{material_id}/polish", summary="AI 文字润色")
async def polish_text(
    material_id: str,
    body: schemas.PolishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按指定风格润色素材文字"""
    result = await service.polish_text(db, current_user.id, material_id, body.style)
    return ok(result)

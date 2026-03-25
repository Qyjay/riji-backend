"""
纪念日路由
prefix="/api/anniversaries", tags=["纪念日"]
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import ok
from app.anniversary import schemas, service

router = APIRouter(prefix="/anniversaries", tags=["纪念日"])


@router.get("", summary="纪念日列表")
def list_anniversaries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户所有纪念日"""
    items = service.list_anniversaries(db, current_user.id)
    return ok({"items": items, "total": len(items)})


@router.post("", summary="添加纪念日")
def create_anniversary(
    body: schemas.AnniversaryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动添加纪念日"""
    result = service.create_anniversary(db, current_user.id, body.model_dump())
    return ok(result)


@router.put("/{ann_id}", summary="编辑纪念日")
def update_anniversary(
    ann_id: str,
    body: schemas.AnniversaryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新纪念日信息"""
    result = service.update_anniversary(
        db, current_user.id, ann_id, body.model_dump(exclude_unset=True)
    )
    return ok(result)


@router.delete("/{ann_id}", summary="删除纪念日")
def delete_anniversary(
    ann_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除纪念日"""
    service.delete_anniversary(db, current_user.id, ann_id)
    return ok({"deleted": True})


@router.get("/today", summary="今日纪念日")
def get_today_anniversaries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取今日纪念日 + 那年今日的日记"""
    today = date.today().strftime("%Y-%m-%d")
    result = service.get_today_anniversaries(db, current_user.id, today)
    return ok(result)

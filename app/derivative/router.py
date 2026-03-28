"""
衍生内容路由
prefix="/api/derivatives", tags=["衍生内容"]
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.derivative import DiaryDerivative
from app.response import success, ApiException, NOT_FOUND
from app.diary.schemas import DerivativeOut

router = APIRouter(prefix="/derivatives", tags=["衍生内容"])


class ShareRequest(BaseModel):
    scope: str = "private"   # "private" | "friends" | "public"


def _deriv_to_out(d: DiaryDerivative) -> dict:
    return DerivativeOut(
        id=d.id,
        diary_id=d.diary_id,
        type=d.type,
        content=d.content or "",
        media_url=d.media_url or "",
        share_scope=d.share_scope or "private",
        created_at=d.created_at,
    ).model_dump(by_alias=True)


@router.get("", summary="衍生内容列表（裸数组）")
def list_derivatives(
    diary_id: Optional[str] = Query(None, description="按日记 ID 筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户所有衍生内容，支持 diary_id 筛选，返回裸数组"""
    from app.models.diary import Diary
    diary_ids_q = db.query(Diary.id).filter(Diary.user_id == current_user.id)
    if diary_id:
        diary_ids_q = diary_ids_q.filter(Diary.id == diary_id)
    diary_ids = [d.id for d in diary_ids_q]

    items = (
        db.query(DiaryDerivative)
        .filter(DiaryDerivative.diary_id.in_(diary_ids))
        .order_by(DiaryDerivative.created_at.desc())
        .all()
    )
    return success([_deriv_to_out(d) for d in items])


@router.post("/{deriv_id}/share", summary="设置分享范围")
def set_share_scope(
    deriv_id: str,
    body: ShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """设置衍生内容的分享范围"""
    from app.models.diary import Diary
    d = db.query(DiaryDerivative).filter(DiaryDerivative.id == deriv_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="衍生内容不存在", status_code=404)
    diary = db.query(Diary).filter(Diary.id == d.diary_id, Diary.user_id == current_user.id).first()
    if not diary:
        raise ApiException(code=NOT_FOUND, message="衍生内容不存在", status_code=404)

    d.share_scope = body.scope
    db.commit()
    db.refresh(d)
    return success(None)

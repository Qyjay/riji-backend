"""
衍生内容路由
prefix="/api/derivatives", tags=["衍生内容"]
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.derivative import DiaryDerivative
from app.response import ok, ApiException, NOT_FOUND

router = APIRouter(prefix="/derivatives", tags=["衍生内容"])


class ShareRequest(BaseModel):
    """分享范围设置请求"""
    scope: str = "private"   # "private" | "friends" | "public"


def _deriv_to_dict(d: DiaryDerivative) -> dict:
    return {
        "id": d.id,
        "diary_id": d.diary_id,
        "type": d.type,
        "content": d.content or "",
        "media_url": d.media_url or "",
        "share_scope": d.share_scope or "private",
        "created_at": d.created_at,
    }


@router.get("", summary="衍生内容列表")
def list_derivatives(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户所有衍生内容"""
    # 通过 diary 关联查找属于当前用户的衍生内容
    from app.models.diary import Diary
    diary_ids = [d.id for d in db.query(Diary.id).filter(Diary.user_id == current_user.id)]
    items = (
        db.query(DiaryDerivative)
        .filter(DiaryDerivative.diary_id.in_(diary_ids))
        .order_by(DiaryDerivative.created_at.desc())
        .all()
    )
    return ok({"items": [_deriv_to_dict(d) for d in items], "total": len(items)})


@router.get("/{deriv_id}", summary="衍生内容详情")
def get_derivative(
    deriv_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单条衍生内容"""
    from app.models.diary import Diary
    d = db.query(DiaryDerivative).filter(DiaryDerivative.id == deriv_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="衍生内容不存在", status_code=404)
    # 验证归属
    diary = db.query(Diary).filter(Diary.id == d.diary_id, Diary.user_id == current_user.id).first()
    if not diary:
        raise ApiException(code=NOT_FOUND, message="衍生内容不存在", status_code=404)
    return ok(_deriv_to_dict(d))


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
    return ok(_deriv_to_dict(d))

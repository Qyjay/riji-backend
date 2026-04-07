"""
衍生内容模块 - 路由层
prefix="/api/derivatives", tags=["衍生内容"]
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.derivative import service
from app.derivative.schemas import ShareRequest, DerivativeOut

router = APIRouter(prefix="/derivatives", tags=["衍生内容"])


@router.get("", summary="衍生内容列表（裸数组）")
def list_derivatives(
    diary_id: str = Query(None, description="按日记 ID 筛选"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取用户所有衍生内容，支持 diary_id 筛选，返回裸数组
    """
    items = service.list_derivatives(db, current_user.id, diary_id)
    # 将每个 dict 转为 CamelModel，输出 camelCase
    out_items = [DerivativeOut(**item).model_dump(by_alias=True) for item in items]
    return success(out_items)


@router.post("/{deriv_id}/share", summary="设置分享范围")
def set_share_scope(
    deriv_id: str,
    body: ShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    设置衍生内容的分享范围，返回更新后的对象
    """
    result = service.update_share_scope(db, current_user.id, deriv_id, body.scope)
    out = DerivativeOut(**result)
    return success(out.model_dump(by_alias=True))
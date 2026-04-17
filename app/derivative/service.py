"""
衍生内容模块 - 业务逻辑层
"""
import time
from sqlalchemy.orm import Session
from app.models.derivative import DiaryDerivative
from app.models.diary import Diary
from app.response import ApiException, NOT_FOUND, BUSINESS_ERROR


def list_derivatives(db: Session, user_id: str, diary_id: str = None) -> list:
    """
    获取用户的衍生内容列表
    - 如果 diary_id 不为空，只返回该日记下的衍生内容
    - 返回裸数组（list of dict）
    """
    # 只查当前用户的日记对应的衍生内容
    query = (
        db.query(DiaryDerivative)
        .join(Diary, DiaryDerivative.diary_id == Diary.id)
        .filter(Diary.user_id == user_id)
    )
    if diary_id:
        query = query.filter(DiaryDerivative.diary_id == diary_id)

    derivatives = query.order_by(DiaryDerivative.created_at.desc()).all()
    return [derivative_to_dict(der) for der in derivatives]


def update_share_scope(db: Session, user_id: str, deriv_id: str, scope: str) -> dict:
    """
    修改衍生内容的分享范围
    - 仅当衍生内容所属日记的作者为当前用户时才允许修改
    - 返回更新后的衍生内容字典
    """
    # 1. 查询衍生内容
    deriv = db.query(DiaryDerivative).filter(DiaryDerivative.id == deriv_id).first()
    if not deriv:
        raise ApiException(
            code=NOT_FOUND,
            message="衍生内容不存在",
            status_code=404
        )

    # 2. 权限校验：当前用户必须是日记的作者
    diary = db.query(Diary).filter(Diary.id == deriv.diary_id).first()
    if not diary or diary.user_id != user_id:
        raise ApiException(
            code=BUSINESS_ERROR,
            message="无权修改此衍生内容",
            status_code=403
        )

    # 3. 更新字段
    deriv.share_scope = scope
    deriv.updated_at = int(time.time() * 1000)   # 毫秒时间戳
    db.commit()
    db.refresh(deriv)

    return derivative_to_dict(deriv)


def derivative_to_dict(deriv: DiaryDerivative) -> dict:
    """将模型对象转为字典（供 service 返回）"""
    return {
        "id": deriv.id,
        "diary_id": deriv.diary_id,
        "type": deriv.type,
        "content": deriv.content or "",
        "media_url": deriv.media_url or "",
        "share_scope": deriv.share_scope or "private",
        "created_at": deriv.created_at,
    }
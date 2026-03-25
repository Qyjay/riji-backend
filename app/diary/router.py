"""
日记模块路由 v2
prefix="/api/diaries", tags=["日记管理"]
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import ok
from app.diary import schemas, service

router = APIRouter(prefix="/diaries", tags=["日记管理"])


@router.post("/generate", summary="AI 生成当日日记")
async def generate_diary(
    body: schemas.GenerateDiaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从当天素材 AI 生成标题+正文+情绪汇总，自动创建日记记录"""
    result = await service.generate_diary(db, current_user.id, body.date, body.weather or "")
    return ok(result)


@router.get("", summary="日记列表")
def list_diaries(
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(10, ge=1, le=50, description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分页获取当前用户的日记列表"""
    result = service.list_diaries(db, current_user.id, page, pageSize)
    return ok(result)


@router.get("/{diary_id}", summary="日记详情")
def get_diary(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单篇日记详情（含关联素材 ID 列表）"""
    result = service.get_diary(db, current_user.id, diary_id)
    return ok(result)


@router.put("/{diary_id}", summary="修改日记")
def update_diary(
    diary_id: str,
    body: schemas.UpdateDiaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改日记（检查 edit_count < max_edits，超出返回错误）"""
    result = service.update_diary(
        db, current_user.id, diary_id, body.model_dump(exclude_unset=True)
    )
    return ok(result)


@router.get("/{diary_id}/emotion-trend", summary="当日情绪趋势")
def get_emotion_trend(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从关联素材的情绪数据聚合情绪趋势"""
    result = service.get_emotion_trend(db, current_user.id, diary_id)
    return ok(result)


@router.post("/{diary_id}/extract", summary="AI 提取信息")
async def extract_diary_info(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI 提取纪念日/人物关系/偏好，结果写入 anniversaries + user_profiles"""
    result = await service.extract_diary_info(db, current_user.id, diary_id)
    return ok(result)


@router.post("/{diary_id}/derivative", summary="生成衍生内容")
async def generate_derivative(
    diary_id: str,
    body: schemas.DerivativeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成衍生内容：漫画(comic) | 小说(novel) | 分享卡(share_card)"""
    result = await service.generate_derivative(db, current_user.id, diary_id, body.type)
    return ok(result)

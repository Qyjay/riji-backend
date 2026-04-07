"""
日记模块路由 v2
prefix="/api/diaries", tags=["日记管理"]
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.diary import schemas, service

router = APIRouter(prefix="/diaries", tags=["日记管理"])

# ⚠️ today-summary 必须在 /{diary_id} 之前注册
@router.get("/today-summary", summary="今日概要")
def get_today_summary(
    date: str = Query(..., description="日期 YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """首页用：今日素材数 + 是否已生成日记 + 日记ID"""
    result = service.get_today_summary(db, current_user.id, date)
    return success(result)


@router.post("/generate", summary="AI 生成当日日记")
async def generate_diary(
    body: schemas.GenerateDiaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从当天素材 AI 生成标题+正文+情绪汇总，自动创建日记记录"""
    result = await service.generate_diary(
        db,
        current_user.id,
        body.date,
        body.weather or "",
        body.allow_fallback,
    )
    return success(result)


@router.get("", summary="日记列表")
def list_diaries(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页条数（snake_case）"),
    pageSize: int = Query(None, ge=1, le=50, description="每页条数（camelCase）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分页获取当前用户的日记列表，返回 {items, total}"""
    effective_page_size = pageSize if pageSize is not None else page_size
    result = service.list_diaries(db, current_user.id, page, effective_page_size)
    return success(result)


@router.get("/search", summary="搜索日记")
def search_diaries_endpoint(
    params: schemas.DiarySearchParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """多维度组合搜索：关键词/情绪/标签/天气/日期范围。"""
    result = service.search_diaries(db, current_user.id, params)
    return success(result)


@router.get("/{diary_id}", summary="日记详情")
def get_diary(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单篇日记详情"""
    result = service.get_diary(db, current_user.id, diary_id)
    return success(result)


@router.put("/{diary_id}", summary="修改日记")
def update_diary(
    diary_id: str,
    body: schemas.UpdateDiaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改日记（检查 edit_count < max_edits，超出返回错误）"""
    result = service.update_diary(
        db, current_user.id, diary_id, body.model_dump()
    )
    return success(result)


@router.get("/{diary_id}/emotion-trend", summary="当日情绪趋势")
def get_emotion_trend(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从关联素材的情绪数据聚合情绪趋势"""
    result = service.get_emotion_trend(db, current_user.id, diary_id)
    return success(result)


@router.post("/{diary_id}/extract", summary="AI 提取信息")
async def extract_diary_info(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI 提取纪念日/人物关系/偏好"""
    result = await service.extract_diary_info(db, current_user.id, diary_id)
    return success(result)


@router.post("/{diary_id}/derivative", summary="生成衍生内容")
async def generate_derivative(
    diary_id: str,
    body: schemas.DerivativeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成衍生内容：漫画(comic) | 小说(novel) | 分享卡(share_card)"""
    result = await service.generate_derivative(db, current_user.id, diary_id, body.type)
    return success(result)

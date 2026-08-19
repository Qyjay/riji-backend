"""
日记模块路由 v2
prefix="/api/diaries", tags=["日记管理"]
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse
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
        body.weather_periods,
        body.allow_fallback,
    )
    return success(result)


@router.post("/backfill-task", summary="创建异步补写日记任务")
async def create_backfill_task(
    body: schemas.BackfillDiaryRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """根据批量照片素材异步补写一篇历史日记，返回任务 ID 供前端轮询。"""
    result = service.start_backfill_task(db, current_user.id, body)
    background_tasks.add_task(service.run_backfill_task, result["task_id"])
    out = schemas.BackfillTaskOut(**result)
    return success(out.model_dump(by_alias=True))


@router.get("/backfill-task/{task_id}", summary="查询补写日记任务")
async def get_backfill_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询异步补写日记任务状态。"""
    result = service.get_backfill_task(current_user.id, task_id)
    out = schemas.BackfillTaskOut(**result)
    return success(out.model_dump(by_alias=True))


@router.post("/backfill-interview/stream", summary="AI 分身追问扩展补写素材")
async def stream_backfill_interview(
    body: schemas.BackfillInterviewRequest,
    current_user: User = Depends(get_current_user),
):
    """AI 分身基于已上传照片与回忆，流式追问帮助用户补充细节。"""
    return StreamingResponse(
        service.stream_backfill_interview(current_user.id, body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/backfill-questions", summary="预生成补写访谈问题")
async def generate_backfill_questions(
    body: schemas.BackfillQuestionsRequest,
    current_user: User = Depends(get_current_user),
):
    """根据已上传照片与回忆，一次性预生成 3~5 个访谈问题，供问卷式收集。"""
    result = await service.generate_backfill_questions(current_user.id, body)
    out = schemas.BackfillQuestionsOut(**result)
    return success(out.model_dump(by_alias=True))


@router.get("", summary="日记列表")
def list_diaries(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=366, description="每页条数（snake_case）"),
    pageSize: int = Query(None, ge=1, le=366, description="每页条数（camelCase）"),
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


@router.delete("/{diary_id}", summary="删除日记")
def delete_diary(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除指定日记"""
    service.delete_diary(db, current_user.id, diary_id)
    return success(None)


@router.get("/{diary_id}/emotion-trend", summary="当日情绪趋势")
def get_emotion_trend(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从关联素材的情绪数据聚合情绪趋势"""
    result = service.get_emotion_trend(db, current_user.id, diary_id)
    return success(result)


@router.post("/{diary_id}/ai-comment", summary="生成日记 AI 点评")
async def generate_diary_ai_comment(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """为日记生成并保存真实 AI 分身点评；已存在时直接返回。"""
    result = await service.generate_diary_ai_comment(db, current_user.id, diary_id)
    return success(result)


@router.post("/{diary_id}/ai-comment/stream", summary="流式生成日记 AI 点评")
async def stream_diary_ai_comment(
    diary_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """流式生成 AI 分身点评；前端可边生成边展示，完成后自动保存。"""
    return StreamingResponse(
        service.stream_diary_ai_comment(current_user.id, diary_id, bind=db.get_bind()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    result = await service.generate_derivative(
        db, current_user.id, diary_id, body.type, body.style
    )
    return success(result)


@router.post("/{diary_id}/derivatives", summary="生成衍生内容（兼容别名）")
async def generate_derivative_alias(
    diary_id: str,
    body: schemas.DerivativeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兼容旧版前端复数路径：/diaries/{id}/derivatives。"""
    result = await service.generate_derivative(
        db, current_user.id, diary_id, body.type, body.style
    )
    return success(result)


@router.post("/{diary_id}/derivative-task", summary="创建异步衍生内容任务")
async def create_derivative_task(
    diary_id: str,
    body: schemas.DerivativeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建异步衍生内容任务，当前用于漫画生成。"""
    result = service.start_derivative_task(db, current_user.id, diary_id, body.type)
    background_tasks.add_task(service.run_derivative_task, result["task_id"])
    out = schemas.DerivativeTaskOut(**result)
    return success(out.model_dump(by_alias=True))

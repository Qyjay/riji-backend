"""
我的小传模块路由
prefix="/api/biography", tags=["我的小传"]
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.biography import schemas, service

router = APIRouter(prefix="/biography", tags=["我的小传"])


@router.get("", summary="获取小传目录与进度")
def get_biography(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.get_biography(db, current_user.id)
    return success(schemas.BiographyOut(**data).model_dump(by_alias=True))


@router.get("/chapters/{chapter_id}", summary="获取章节详情")
def get_chapter(
    chapter_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.get_chapter(db, current_user.id, chapter_id)
    return success(schemas.ChapterOut(**data).model_dump(by_alias=True))


@router.post("/chapters/task", summary="创建异步生成下一章任务")
def create_chapter_task(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = service.start_generate_task(db, current_user.id)
    background_tasks.add_task(service.run_generate_task, result["task_id"])
    return success(schemas.TaskOut(**result).model_dump(by_alias=True))


@router.get("/tasks/{task_id}", summary="查询生成任务状态")
def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = service.get_task(current_user.id, task_id)
    return success(schemas.TaskOut(**result).model_dump(by_alias=True))

"""
学习模块路由骨架（番茄钟 + 待办）
组员 A 负责实现
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.study.schemas import CreatePomodoroRequest, CreateTodoRequest

router = APIRouter(prefix="/study", tags=["学习"])


# ==================== 番茄钟 ====================

@router.get("/pomodoros", summary="获取番茄钟列表")
def list_pomodoros(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 E1（GET）
    获取当前用户的番茄钟历史记录
    按 created_at DESC 排序
    """
    pass


@router.post("/pomodoros", summary="创建番茄钟")
def create_pomodoro(
    req: CreatePomodoroRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 E1（POST）
    创建新的番茄钟记录
    completed_at 初始为 None（表示进行中）
    """
    pass


@router.post("/pomodoros/{pomodoro_id}/complete", summary="完成番茄钟")
def complete_pomodoro(
    pomodoro_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 E1（完成）
    标记番茄钟为已完成
    1. 查询并验证归属
    2. 设置 completed_at 为当前时间戳
    3. 更新 User.pomodoro_count += 1
    4. 可触发成就检查（如完成第 10 个番茄）
    """
    pass


# ==================== 待办 ====================

@router.get("/todos", summary="获取待办列表")
def list_todos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 E2（GET）
    获取当前用户的待办列表
    按 priority（high > medium > low）和 created_at 排序
    """
    pass


@router.post("/todos", summary="创建待办")
def create_todo(
    req: CreateTodoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 E2（POST）
    创建新待办事项
    """
    pass


@router.post("/todos/{todo_id}/toggle", summary="切换待办完成状态")
def toggle_todo(
    todo_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 A 实现 - 接口 E2（切换）
    切换待办的完成状态（completed: False → True 或 True → False）
    """
    pass

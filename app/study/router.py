"""
学习模块路由（番茄钟 + 待办）
"""
import time
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.study import Pomodoro, Todo
from app.response import success, ApiException, NOT_FOUND
from app.study.schemas import CreatePomodoroRequest, CreateTodoRequest, PomodoroOut, TodoOut

router = APIRouter(prefix="/study", tags=["学习"])


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _pomo_to_out(p: Pomodoro) -> dict:
    return PomodoroOut(
        id=p.id,
        task=p.task or "新任务",
        subject=p.subject or "其他",
        duration=p.duration or 25,
        completed_at=p.completed_at,
        created_at=p.created_at,
    ).model_dump(by_alias=True)


def _todo_to_out(t: Todo) -> dict:
    return TodoOut(
        id=t.id,
        content=t.content or "",
        completed=t.completed or False,
        priority=t.priority or "medium",
        created_at=t.created_at,
    ).model_dump(by_alias=True)


# ==================== 番茄钟 ====================

@router.get("/pomodoros", summary="获取番茄钟列表（裸数组）")
def list_pomodoros(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(Pomodoro)
        .filter(Pomodoro.user_id == current_user.id)
        .order_by(Pomodoro.created_at.desc())
        .all()
    )
    return success([_pomo_to_out(p) for p in items])


@router.post("/pomodoros", summary="创建番茄钟")
def create_pomodoro(
    req: CreatePomodoroRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = Pomodoro(
        id=_uuid(),
        user_id=current_user.id,
        task=req.task,
        subject=req.subject or "其他",
        duration=req.duration or 25,
        completed_at=None,
        created_at=_now_ms(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return success(_pomo_to_out(p))


@router.post("/pomodoros/{pomodoro_id}/complete", summary="完成番茄钟")
def complete_pomodoro(
    pomodoro_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.query(Pomodoro).filter(
        Pomodoro.id == pomodoro_id, Pomodoro.user_id == current_user.id
    ).first()
    if not p:
        raise ApiException(code=NOT_FOUND, message="番茄钟不存在", status_code=404)

    p.completed_at = _now_ms()
    # 更新用户番茄钟数量
    user = db.query(User).filter(User.id == current_user.id).first()
    if user:
        user.pomodoro_count = (user.pomodoro_count or 0) + 1
    db.commit()
    return success(None)


# ==================== 待办 ====================

@router.get("/todos", summary="获取待办列表（裸数组）")
def list_todos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(Todo)
        .filter(Todo.user_id == current_user.id)
        .order_by(Todo.created_at.desc())
        .all()
    )
    return success([_todo_to_out(t) for t in items])


@router.post("/todos", summary="创建待办")
def create_todo(
    req: CreateTodoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = Todo(
        id=_uuid(),
        user_id=current_user.id,
        content=req.content,
        completed=False,
        priority=req.priority or "medium",
        created_at=_now_ms(),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return success(_todo_to_out(t))


@router.post("/todos/{todo_id}/toggle", summary="切换待办完成状态")
def toggle_todo(
    todo_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.query(Todo).filter(
        Todo.id == todo_id, Todo.user_id == current_user.id
    ).first()
    if not t:
        raise ApiException(code=NOT_FOUND, message="待办不存在", status_code=404)

    t.completed = not (t.completed or False)
    db.commit()
    db.refresh(t)
    return success(_todo_to_out(t))

"""
学习模块 Pydantic Schema
"""
from typing import Optional
from pydantic import BaseModel
from app.serializers import CamelModel


class CreatePomodoroRequest(BaseModel):
    """创建番茄钟请求"""
    task: str = "新任务"
    subject: Optional[str] = "其他"
    duration: Optional[int] = 25


class CreateTodoRequest(BaseModel):
    """创建待办请求"""
    content: str
    priority: Optional[str] = "medium"


class PomodoroOut(CamelModel):
    """番茄钟响应"""
    id: str
    task: str
    subject: str
    duration: int
    completed_at: Optional[int] = None
    created_at: int


class TodoOut(CamelModel):
    """待办响应"""
    id: str
    content: str
    completed: bool
    priority: str
    created_at: int

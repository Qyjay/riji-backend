"""
学习模块 Pydantic Schema（组员 A 根据需要扩展）
"""
from typing import Optional
from pydantic import BaseModel


class CreatePomodoroRequest(BaseModel):
    """创建番茄钟请求"""
    task: str
    subject: Optional[str] = ""
    duration: Optional[int] = 25  # 分钟


class CreateTodoRequest(BaseModel):
    """创建待办请求"""
    content: str
    priority: Optional[str] = "medium"  # low / medium / high

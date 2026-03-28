"""
学习相关数据模型
- Pomodoro: 番茄钟记录
- Todo: 待办事项
"""
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Integer, String

from app.database import Base


class Pomodoro(Base):
    """番茄钟记录表"""
    __tablename__ = "pomodoros"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    task = Column(String, nullable=False)
    subject = Column(String, default="")
    duration = Column(Integer, default=25)              # 分钟
    completed_at = Column(BigInteger, nullable=True)    # 完成时间，None 表示未完成
    created_at = Column(BigInteger, nullable=False)


class Todo(Base):
    """待办事项表"""
    __tablename__ = "todos"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(String, nullable=False)
    completed = Column(Boolean, default=False)
    priority = Column(String, default="medium")  # low / medium / high
    created_at = Column(BigInteger, nullable=False)

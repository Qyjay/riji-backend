"""
纪念日数据模型
Anniversary: 用户的重要纪念日（手动添加或 AI 提取）
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String

from app.database import Base


def _uuid():
    """生成字符串 UUID"""
    return str(uuid4())


class Anniversary(Base):
    """纪念日表"""
    __tablename__ = "anniversaries"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)                          # 纪念日名称
    date = Column(String, nullable=False)                           # 月-日，如 "03-25"
    year = Column(Integer, nullable=True)                           # 发生年份（可选）
    source = Column(String, default="manual")                       # "manual" | "ai_extracted"
    related_person = Column(String, default="")                     # 相关人物
    diary_id = Column(String, ForeignKey("diaries.id"), nullable=True)  # 关联日记（可选）
    created_at = Column(BigInteger, nullable=False)                 # 毫秒时间戳

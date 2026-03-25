"""
日记数据模型
"""
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Index, String, Text

from app.database import Base


class Diary(Base):
    """日记表"""
    __tablename__ = "diaries"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    images = Column(Text, default="[]")         # JSON array: [url, ...]
    emotion = Column(Text, default="{}")        # JSON: {emoji, label, score}
    tags = Column(Text, default="[]")           # JSON array: [tag, ...]
    location = Column(String, default="")
    weather = Column(String, default="")
    style = Column(String, default="日记式")
    has_comic = Column(Boolean, default=False)
    has_bgm = Column(Boolean, default=False)
    comic_url = Column(String, default="")
    bgm_url = Column(String, default="")
    created_at = Column(BigInteger, nullable=False)  # 毫秒时间戳
    updated_at = Column(BigInteger, nullable=False)  # 毫秒时间戳

    __table_args__ = (
        # 按用户和时间排序索引，提升列表查询性能
        Index("ix_diaries_user_created", "user_id", "created_at"),
    )

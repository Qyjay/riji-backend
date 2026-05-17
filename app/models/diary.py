"""
日记数据模型
"""
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint

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
    image_understandings = Column(Text, default="[]")  # JSON array: [视觉理解文本, ...]
    created_at = Column(BigInteger, nullable=False)  # 毫秒时间戳
    updated_at = Column(BigInteger, nullable=False)  # 毫秒时间戳

    # v2 新增字段
    title = Column(String, default="")                  # 日记标题（AI 生成）
    special_date = Column(String, default="")           # 特殊日期标注（如纪念日名称）
    ai_comment = Column(Text, default="")               # AI 分身对本篇日记的点评
    emotion_summary = Column(Text, default="{}")        # JSON: 情绪汇总 {dominant, distribution}
    material_ids = Column(Text, default="[]")           # JSON: 关联素材 ID 列表
    edit_count = Column(Integer, default=0)             # 已修改次数
    max_edits = Column(Integer, default=3)              # 最大允许修改次数
    status = Column(String, default="draft")            # "draft" | "published"
    date = Column(String, default="")                   # 所属日期 "2026-03-25"

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_diaries_user_date"),
        # 按用户和时间排序索引，提升列表查询性能
        Index("ix_diaries_user_created", "user_id", "created_at"),
    )

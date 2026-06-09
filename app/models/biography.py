"""
我的小传数据模型
BiographyChapter: 由用户日记/帖子/素材/记忆聚合自动生成的自传章节
- 每章覆盖一段日期区间，消耗若干篇日记后解锁
- 复用已生成漫画作为插图，并为每章生成封面图
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text

from app.database import Base


def _uuid():
    """生成字符串 UUID"""
    return str(uuid4())


class BiographyChapter(Base):
    """自传章节表"""
    __tablename__ = "biography_chapters"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    chapter_index = Column(Integer, nullable=False)        # 章节序号 1,2,3...

    title = Column(String, default="")                     # 章节标题
    content = Column(Text, default="")                     # 正文（含分段）
    preview = Column(Text, default="")                     # 摘要预览（目录展示）
    word_count = Column(Integer, default=0)                # 字数
    summary = Column(Text, default="")                     # 章节梗概，供下一章续写时保持连贯

    cover_image_url = Column(String, default="")           # 本章封面图（AI 生成）
    illustrations = Column(Text, default="[]")             # JSON: [{diary_id, image_url, anchor_para}] 复用漫画

    date_range_start = Column(String, default="")          # 覆盖日期区间起 "2026-03-25"
    date_range_end = Column(String, default="")            # 覆盖日期区间止

    source_diary_ids = Column(Text, default="[]")          # JSON: 已消耗日记 id，避免重复
    source_material_count = Column(Integer, default=0)
    source_post_count = Column(Integer, default=0)

    status = Column(String, default="generating")          # "generating" | "done" | "failed"
    created_at = Column(BigInteger, nullable=False)        # 毫秒时间戳
    updated_at = Column(BigInteger, nullable=False)

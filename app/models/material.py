"""
素材数据模型
RawMaterial: 用户记录的原始素材（图片/语音/文字）
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Column, ForeignKey, Index, String, Text

from app.database import Base


def _uuid():
    """生成字符串 UUID"""
    return str(uuid4())


class RawMaterial(Base):
    """原始素材表 — 用户日常记录的碎片化内容"""
    __tablename__ = "raw_materials"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)           # "image" | "voice" | "text"
    content = Column(Text, default="")              # 文字内容 / 语音转文字结果
    media_url = Column(String, default="")          # 媒体 URL 数组（JSON string）
    thumbnail_url = Column(String, default="")      # 缩略图 URL 数组（JSON string）
    location = Column(Text, default="{}")           # JSON: {lat, lng, address}
    emotion = Column(Text, default="{}")            # JSON: {label, score, emoji}
    tags = Column(Text, default="[]")              # JSON array: 自动提取的标签
    date = Column(String, nullable=False)           # 所属日期 "2026-03-25"
    created_at = Column(BigInteger, nullable=False)  # 毫秒时间戳

    # chat 类型专属字段
    chat_session_id = Column(String, nullable=True)    # 仅 chat 类型使用
    start_time = Column(BigInteger, nullable=True)     # 对话开始时间
    end_time = Column(BigInteger, nullable=True)       # 对话结束时间

    __table_args__ = (
        # 按用户+日期查询索引
        Index("ix_raw_materials_user_date", "user_id", "date"),
    )

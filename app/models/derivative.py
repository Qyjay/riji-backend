"""
日记衍生内容数据模型
DiaryDerivative: 由日记生成的二次创作内容（漫画/小说/分享卡等）
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Column, ForeignKey, String, Text

from app.database import Base


def _uuid():
    """生成字符串 UUID"""
    return str(uuid4())


class DiaryDerivative(Base):
    """日记衍生内容表"""
    __tablename__ = "diary_derivatives"

    id = Column(String, primary_key=True, default=_uuid)
    diary_id = Column(String, ForeignKey("diaries.id"), nullable=False)  # 源日记
    type = Column(String, nullable=False)               # "comic" | "novel" | "video" | "share_card"
    content = Column(Text, default="")                  # 文字型衍生内容（小说/share_card 文案）
    media_url = Column(String, default="")              # 媒体文件 URL（漫画图片/视频）
    share_scope = Column(String, default="private")     # "private" | "friends" | "public"
    created_at = Column(BigInteger, nullable=False)     # 毫秒时间戳

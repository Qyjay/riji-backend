"""
用户 AI 画像数据模型
UserProfile: 由 AI 分析日记和聊天记录生成的用户画像
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Column, ForeignKey, String, Text, UniqueConstraint

from app.database import Base


def _uuid():
    """生成字符串 UUID"""
    return str(uuid4())


class UserProfile(Base):
    """用户 AI 画像表（每用户一条）"""
    __tablename__ = "user_profiles"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)  # 唯一关联用户
    preferences = Column(Text, default="{}")    # JSON: 用户偏好（食物/音乐/活动等）
    personality = Column(Text, default="")      # 性格描述（文本）
    writing_style = Column(Text, default="")    # 写作风格描述（文本）
    relations = Column(Text, default="{}")      # JSON: 人物关系图谱 {name: relation}
    interests = Column(Text, default="[]")      # JSON array: 兴趣标签
    updated_at = Column(BigInteger, nullable=False)  # 毫秒时间戳

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_profile"),
    )

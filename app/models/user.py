"""
用户相关数据模型
- User: 用户基本信息
- UserSettings: 用户设置
- UserAchievement: 用户成就
"""
from uuid import uuid4

from sqlalchemy import (
    BigInteger, Boolean, Column, ForeignKey,
    Integer, String, UniqueConstraint
)

from app.database import Base


def _uuid():
    """生成字符串 UUID"""
    return str(uuid4())


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    username = Column(String, unique=True, nullable=False, index=True)  # 4-20 字符
    password = Column(String, nullable=False)                            # bcrypt hash
    name = Column(String, default="")
    school = Column(String, default="")
    major = Column(String, default="")
    grade = Column(String, default="")          # 大一~研三
    avatar = Column(String, default="")
    signature = Column(String, default="")
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    diary_count = Column(Integer, default=0)
    streak_days = Column(Integer, default=0)
    pomodoro_count = Column(Integer, default=0)
    created_at = Column(BigInteger, nullable=False)  # 毫秒时间戳
    updated_at = Column(BigInteger, nullable=False)  # 毫秒时间戳


class UserSettings(Base):
    """用户设置表（每个用户一条记录）"""
    __tablename__ = "user_settings"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    theme = Column(String, default="light")
    notifications = Column(Boolean, default=True)
    auto_bgm = Column(Boolean, default=False)
    diary_privacy = Column(String, default="private")
    language = Column(String, default="zh-CN")


class UserAchievement(Base):
    """用户成就表"""
    __tablename__ = "user_achievements"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(String, nullable=False)
    unlocked_at = Column(BigInteger, nullable=False)  # 毫秒时间戳

    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

"""
用户相关数据模型
- User: 用户基本信息
- UserSettings: 用户设置
- UserAchievement: 用户成就
"""
from uuid import uuid4

from sqlalchemy import (
    BigInteger, Boolean, Column, ForeignKey,
    Integer, String, Text, UniqueConstraint
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

    # v2 新增字段
    openclaw_agent_id = Column(String, default="")      # OpenClaw AI 代理 ID
    style_tags = Column(Text, default="[]")             # JSON: 用户写作风格标签
    custom_style_prompt = Column(Text, default="")      # 自定义写作风格 Prompt


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

    # 对话自动转素材相关设置
    chat_material_enabled = Column(Boolean, default=True)      # 对话自动转素材开关
    chat_silence_threshold = Column(Integer, default=30)        # 静默阈值（分钟）
    chat_material_toast = Column(Boolean, default=True)         # toast 提示开关
    chat_min_rounds = Column(Integer, default=3)                # 最小轮数（user 消息数）
    chat_model_id = Column(String, default="")                  # 聊天默认模型 ID


class UserLlmModel(Base):
    """用户自定义聊天模型配置"""
    __tablename__ = "user_llm_models"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    provider_type = Column(String, nullable=False)              # openai_compatible | anthropic_compatible
    base_url = Column(String, nullable=False)
    model = Column(String, nullable=False)
    api_key_ciphertext = Column(Text, default="")
    is_enabled = Column(Boolean, default=True, index=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


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

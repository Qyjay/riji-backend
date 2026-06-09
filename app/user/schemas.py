"""
用户模块 Pydantic Schema
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from app.serializers import CamelModel


class UpdateProfileRequest(BaseModel):
    """更新用户资料请求（前端发 snake_case）"""
    name: Optional[str] = None
    school: Optional[str] = None
    major: Optional[str] = None
    avatar: Optional[str] = None
    style_tags: Optional[List[str]] = None
    custom_style_prompt: Optional[str] = None


class UpdateSettingsRequest(BaseModel):
    """更新用户设置请求"""
    theme: Optional[str] = None
    notifications: Optional[bool] = None
    auto_bgm: Optional[bool] = None
    diary_privacy: Optional[str] = None
    language: Optional[str] = None
    chat_material_enabled: Optional[bool] = None
    chat_silence_threshold: Optional[int] = Field(default=None, ge=15, le=120)
    chat_material_toast: Optional[bool] = None
    chat_min_rounds: Optional[int] = Field(default=None, ge=1, le=20)
    chat_model_id: Optional[str] = None


class UserProfileOut(CamelModel):
    """用户资料响应（camelCase 输出）"""
    name: str
    school: str
    major: str
    level: int
    diary_count: int
    streak_days: int
    pomodoro_count: int
    avatar: str
    style_tags: Optional[List[str]] = None
    custom_style_prompt: Optional[str] = None


class AchievementOut(CamelModel):
    """成就响应"""
    id: str
    title: str
    description: str
    icon: str
    unlocked: bool
    unlocked_at: Optional[int] = None


class GrowthDataOut(CamelModel):
    """成长数据响应"""
    level: int
    title: str
    total_xp: int
    current_level_xp: int
    next_level_xp: int
    xp_in_current_level: int
    xp_to_next_level: int
    progress_percent: int
    stats: dict
    skills: list
    chart: list
    milestones: list
    timeline: list
    today_xp: int
    xp_breakdown: list
    # legacy 兼容字段
    diaries: list
    emotions: list
    tags: list
    pomodoros: list
    streak: list


class SettingsOut(CamelModel):
    """设置响应（特殊：autoBGM）"""
    theme: str
    notifications: bool
    auto_bgm: bool = Field(alias="autoBGM", default=False)
    diary_privacy: str
    language: str
    chat_material_enabled: bool = True
    chat_silence_threshold: int = 30
    chat_material_toast: bool = True
    chat_min_rounds: int = 3
    chat_model_id: str = ""

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }


class SemesterReportOut(CamelModel):
    """学期报告响应"""
    total_diaries: int
    total_pomodoros: int
    top_emotions: list
    top_tags: list
    writing_time: int
    avg_emotion: int
    streak: int
    achievements: int
    highlights: list

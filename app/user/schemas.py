"""
用户模块 Pydantic Schema（组员 A 根据需要扩展）
"""
from typing import Optional
from pydantic import BaseModel


class UpdateProfileRequest(BaseModel):
    """更新用户资料请求"""
    name: Optional[str] = None
    school: Optional[str] = None
    major: Optional[str] = None
    grade: Optional[str] = None
    signature: Optional[str] = None


class UpdateSettingsRequest(BaseModel):
    """更新用户设置请求"""
    theme: Optional[str] = None
    notifications: Optional[bool] = None
    auto_bgm: Optional[bool] = None
    diary_privacy: Optional[str] = None
    language: Optional[str] = None

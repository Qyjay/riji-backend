"""
认证相关 Pydantic 模型（请求/响应 Schema）
"""
import re
from typing import Optional
from pydantic import BaseModel, field_validator


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str
    password: str
    name: Optional[str] = ""
    school: Optional[str] = ""
    major: Optional[str] = ""

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 4 or len(v) > 20:
            raise ValueError("用户名长度必须在 4-20 字符之间")
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6 or len(v) > 32:
            raise ValueError("密码长度必须在 6-32 字符之间")
        return v


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class UserInfo(BaseModel):
    """用户信息（返回给前端）"""
    id: str
    username: str
    name: str
    school: str
    major: str
    avatar: str
    level: int

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """认证响应（注册/登录成功后返回）"""
    token: str
    user: UserInfo

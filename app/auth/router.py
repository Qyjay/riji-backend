"""
认证路由
- POST /auth/register  注册
- POST /auth/login     登录
"""
import time
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserSettings
from app.response import (
    success, ApiException,
    AUTH_USERNAME_EXISTS, AUTH_INVALID_CREDENTIALS, PARAM_INVALID
)
from app.auth.schemas import RegisterRequest, LoginRequest, AuthResponse, UserInfo
from app.auth.service import hash_password, verify_password, create_token

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=dict, summary="用户注册")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    注册新用户
    1. 校验用户名格式（已在 Schema 中完成）
    2. 检查用户名是否重复
    3. 创建用户 + 默认设置
    4. 签发 JWT
    5. 返回 AuthResponse
    """
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise ApiException(
            code=AUTH_USERNAME_EXISTS,
            message="用户名已被占用",
            status_code=400,
        )

    now = int(time.time() * 1000)  # 毫秒时间戳

    # 创建用户
    user = User(
        id=str(uuid4()),
        username=req.username,
        password=hash_password(req.password),
        name=req.name or "",
        school=req.school or "",
        major=req.major or "",
        created_at=now,
        updated_at=now,
    )
    db.add(user)

    # 创建默认用户设置
    user_settings = UserSettings(
        id=str(uuid4()),
        user_id=user.id,
    )
    db.add(user_settings)
    db.commit()
    db.refresh(user)

    # 签发 JWT
    token = create_token(user.id)

    return success(
        data=AuthResponse(
            token=token,
            user=UserInfo.model_validate(user),
        ).model_dump(),
        message="注册成功",
    )


@router.post("/login", response_model=dict, summary="用户登录")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    用户登录
    1. 查询用户
    2. 验证密码
    3. 签发 JWT
    4. 返回 AuthResponse
    """
    # 查询用户
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        raise ApiException(
            code=AUTH_INVALID_CREDENTIALS,
            message="用户名或密码错误",
            status_code=400,
        )

    # 验证密码
    if not verify_password(req.password, user.password):
        raise ApiException(
            code=AUTH_INVALID_CREDENTIALS,
            message="用户名或密码错误",
            status_code=400,
        )

    # 签发 JWT
    token = create_token(user.id)

    return success(
        data=AuthResponse(
            token=token,
            user=UserInfo.model_validate(user),
        ).model_dump(),
        message="登录成功",
    )

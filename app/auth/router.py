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


@router.get("/health", summary="健康检查")
def health_check():
    """前端「测试连接」按钮调用此接口，用于验证后端是否可达"""
    return success(data={"status": "ok"}, message="日迹后端运行中")


def _build_auth_response(user: User, token: str) -> dict:
    user_info = UserInfo(
        id=user.id,
        username=user.username,
        name=user.name or "",
        school=user.school or "",
        major=user.major or "",
        avatar=user.avatar or "",
        level=user.level or 1,
    )
    resp = AuthResponse(token=token, user=user_info)
    return resp.model_dump(by_alias=True)


@router.post("/register", summary="用户注册")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise ApiException(
            code=AUTH_USERNAME_EXISTS,
            message="用户名已被占用",
            status_code=400,
        )

    now = int(time.time() * 1000)

    user = User(
        id=str(uuid4()),
        username=req.username,
        password=hash_password(req.password),
        name=req.name or req.username,
        school=req.school or "",
        major=req.major or "",
        avatar="",
        level=1,
        xp=0,
        diary_count=0,
        streak_days=0,
        pomodoro_count=0,
        created_at=now,
        updated_at=now,
    )
    db.add(user)

    user_settings = UserSettings(
        id=str(uuid4()),
        user_id=user.id,
        theme="light",
        notifications=True,
        auto_bgm=False,
        diary_privacy="private",
        language="zh-CN",
    )
    db.add(user_settings)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    return success(data=_build_auth_response(user, token), message="注册成功")


@router.post("/login", summary="用户登录")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        raise ApiException(
            code=AUTH_INVALID_CREDENTIALS,
            message="用户名或密码错误",
            status_code=400,
        )

    if not verify_password(req.password, user.password):
        raise ApiException(
            code=AUTH_INVALID_CREDENTIALS,
            message="用户名或密码错误",
            status_code=400,
        )

    token = create_token(user.id)
    return success(data=_build_auth_response(user, token), message="登录成功")

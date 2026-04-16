"""
认证服务：密码哈希 + JWT 签发/验证
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, ExpiredSignatureError, jwt

from app.config import settings
from app.response import ApiException, AUTH_UNAUTHORIZED, AUTH_TOKEN_EXPIRED


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_token(user_id: str) -> str:
    """
    签发 JWT Token
    payload: {sub: user_id, exp: 过期时间}
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    return token


def decode_token(token: str) -> str:
    """
    解码并验证 JWT Token
    返回 user_id
    无效 → raise ApiException(AUTH_UNAUTHORIZED)
    过期 → raise ApiException(AUTH_TOKEN_EXPIRED)
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if not user_id:
            raise ApiException(code=AUTH_UNAUTHORIZED, message="无效的 Token", status_code=401)
        return user_id
    except ExpiredSignatureError:
        raise ApiException(code=AUTH_TOKEN_EXPIRED, message="Token 已过期，请重新登录", status_code=401)
    except JWTError:
        raise ApiException(code=AUTH_UNAUTHORIZED, message="无效的 Token", status_code=401)


def verify_token(token: str) -> Optional[dict]:
    """
    验证 JWT Token，返回 payload 字典或 None（无效/过期不抛异常）
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except (ExpiredSignatureError, JWTError):
        return None

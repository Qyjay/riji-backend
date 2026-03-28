"""
公共依赖注入
- get_db: 数据库会话
- get_current_user: 从 JWT Token 获取当前登录用户
"""
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.response import ApiException, AUTH_UNAUTHORIZED

# HTTPBearer 用于从 Authorization 头提取 Bearer token
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """
    从请求头 Authorization: Bearer <token> 提取并验证 JWT
    返回当前登录的 User 对象
    token 缺失/无效/过期 → 抛出 401 异常
    """
    from app.auth.service import decode_token
    from app.models.user import User

    # 检查 token 是否存在
    if not credentials or not credentials.credentials:
        raise ApiException(
            code=AUTH_UNAUTHORIZED,
            message="请先登录",
            status_code=401,
        )

    token = credentials.credentials

    # 解码 JWT，失败会抛出 ApiException
    user_id = decode_token(token)

    # 查询用户
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ApiException(
            code=AUTH_UNAUTHORIZED,
            message="用户不存在或已注销",
            status_code=401,
        )

    return user

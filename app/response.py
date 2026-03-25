"""
统一响应格式 + 错误码常量 + 自定义异常
"""
from typing import Any, Optional
from fastapi.responses import JSONResponse


# ==================== 错误码常量 ====================

# 认证相关 401xx
AUTH_USERNAME_EXISTS = 40001       # 用户名已存在
AUTH_INVALID_CREDENTIALS = 40002   # 用户名或密码错误
AUTH_UNAUTHORIZED = 40003          # 未授权（未登录）
AUTH_TOKEN_EXPIRED = 40004         # Token 过期

# 参数相关 401xx
PARAM_INVALID = 40101              # 参数无效
PARAM_ERROR = 40102                # 参数错误（如超过限制）

# 业务相关 402xx
BUSINESS_ERROR = 40201             # 业务错误
NOT_FOUND = 40202                  # 资源不存在

# 服务端错误 5xxxx
SERVER_ERROR = 50001               # 服务器内部错误
AI_SERVICE_ERROR = 50101           # AI 服务错误


# ==================== 自定义异常 ====================

class ApiException(Exception):
    """统一业务异常，FastAPI 全局异常处理器会捕获并转换为 JSON 响应"""

    def __init__(self, code: int, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ==================== 响应工具函数 ====================

def success(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应"""
    return {"code": 0, "data": data, "message": message}


# ok 是 success 的别名，供新模块使用
ok = success


def error(code: int, message: str) -> dict:
    """构造错误响应"""
    return {"code": code, "data": None, "message": message}


def api_exception_handler(request, exc: ApiException):
    """全局 ApiException 处理器，注册到 FastAPI"""
    return JSONResponse(
        status_code=exc.status_code,
        content=error(exc.code, exc.message),
    )

"""
FastAPI 应用入口
- CORS 配置
- 全局异常处理
- 静态文件挂载
- 路由注册（严格按 API-SPEC.md 52 个接口）
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.response import ApiException, api_exception_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭生命周期"""
    from app.database import init_db
    init_db()
    yield


# 创建 FastAPI 应用
app = FastAPI(
    title="日迹 API",
    description="大学生 AI 生活伙伴 App 后端",
    version="2.0.0",
    lifespan=lifespan,
)

# ==================== 中间件 ====================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 全局异常处理 ====================

app.add_exception_handler(ApiException, api_exception_handler)

# ==================== 静态文件 ====================

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# ==================== 路由注册 ====================

from app.auth.router import router as auth_router
from app.upload.router import router as upload_router
from app.material.router import router as material_router
from app.diary.router import router as diary_router
from app.derivative.router import router as derivative_router
from app.ai.router import router as ai_router
from app.chat.router import router as chat_router
from app.user.router import router as user_router
from app.social.router import router as social_router
from app.anniversary.router import router as anniversary_router
from app.study.router import router as study_router

app.include_router(auth_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(material_router, prefix="/api")
app.include_router(diary_router, prefix="/api")
app.include_router(derivative_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(social_router, prefix="/api")
app.include_router(anniversary_router, prefix="/api")
app.include_router(study_router, prefix="/api")


@app.get("/")
def root():
    return {"message": "日迹 API 运行中", "docs": "/docs"}

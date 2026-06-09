"""
FastAPI 应用入口
- CORS 配置
- 全局异常处理
- 静态文件挂载
- 路由注册（严格按 API-SPEC.md 52 个接口）
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.response import ApiException, api_exception_handler


logger = logging.getLogger(__name__)

AUTO_DIARY_CHECK_INTERVAL_SEC = 300
AUTO_DIARY_START_HOUR = 22
AUTO_DIARY_TZ = ZoneInfo("Asia/Shanghai")


async def _run_auto_diary_generation_once() -> None:
    """22:00 后周期补生成当日日记（仅补尚未生成用户）。"""
    now_local = datetime.now(AUTO_DIARY_TZ)
    if now_local.hour < AUTO_DIARY_START_HOUR:
        return

    from app.database import SessionLocal
    from app.diary import service as diary_service

    date = now_local.strftime("%Y-%m-%d")
    db = SessionLocal()
    try:
        result = await diary_service.auto_generate_missing_diaries(db, date)
        if result.get("generated_count") or result.get("failed"):
            logger.info("auto diary generation result: %s", result)
    finally:
        db.close()


async def _auto_diary_generation_loop(stop_event: asyncio.Event) -> None:
    """后台循环：每 5 分钟检查一次是否需要自动补生成。"""
    while not stop_event.is_set():
        try:
            await _run_auto_diary_generation_once()
        except Exception:
            logger.exception("auto diary generation loop failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=AUTO_DIARY_CHECK_INTERVAL_SEC)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭生命周期"""
    from app.database import init_db
    init_db()

    auto_task = None
    auto_stop_event = asyncio.Event()

    if not os.getenv("PYTEST_CURRENT_TEST"):
        auto_task = asyncio.create_task(_auto_diary_generation_loop(auto_stop_event))

    try:
        yield
    finally:
        if auto_task:
            auto_stop_event.set()
            auto_task.cancel()
            with suppress(asyncio.CancelledError):
                await auto_task


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
from app.chat.websocket import router as chat_ws_router
from app.user.router import router as user_router
from app.social.router import router as social_router
from app.anniversary.router import router as anniversary_router
from app.study.router import router as study_router
from app.plaza.router import router as plaza_router
from app.avatar.router import router as avatar_router
from app.memory.router import router as memory_router
from app.location.router import router as location_router
from app.biography.router import router as biography_router

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
app.include_router(plaza_router, prefix="/api")
app.include_router(avatar_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(location_router, prefix="/api")
app.include_router(biography_router, prefix="/api")
app.include_router(chat_ws_router)  # WebSocket 路由（/ws/chat）


@app.get("/")
def root():
    return {"message": "日迹 API 运行中", "docs": "/docs"}

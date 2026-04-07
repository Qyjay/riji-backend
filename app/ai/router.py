# app/ai/router.py（修改后）
import os
import time
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.ai import service as ai_service
from app.ai.schemas import TtsRequest, FortuneOut   # 注意 FortuneOut 现在在 schemas 中

router = APIRouter(prefix="/ai", tags=["AI 功能"])


@router.post("/tts", summary="文字转语音")
async def text_to_speech(
    req: TtsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),   # db 暂时没用，但保留便于未来扩展
):
    url = await ai_service.text_to_speech_service(current_user.id, req.text, req.voice)
    return success(url)


@router.get("/fortune", summary="AI 今日运势")
async def get_fortune(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await ai_service.fortune_service()
    out = FortuneOut(**data)
    return success(out.model_dump(by_alias=True))
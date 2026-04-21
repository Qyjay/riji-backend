# app/ai/router.py（修改后）
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.ai import service as ai_service
from app.ai.schemas import (
    TtsRequest,
    FortuneOut,
)   # 注意 FortuneOut 现在在 schemas 中

router = APIRouter(prefix="/ai", tags=["AI 功能"])


@router.post("/tts", summary="文字转语音")
async def text_to_speech(
    req: TtsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),   # db 暂时没用，但保留便于未来扩展
):
    url = await ai_service.text_to_speech_service(current_user.id, req.text, req.voice)
    return success(url)


@router.post("/asr", summary="实时短语音识别")
async def speech_to_text_short(
    file: UploadFile = File(..., description="音频文件（仅支持 wav/pcm，建议 16kHz/16bit/单声道）"),
    punctuation: int = Query(1, ge=0, le=1, description="标点：0=关闭，1=开启"),
    chinese2digital: int = Query(1, ge=0, le=1, description="数字归一化：0=关闭，1=开启"),
    end_vad_time: int = Query(2000, ge=300, le=10000, description="尾静音切分时间，单位毫秒"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = db
    data = await ai_service.speech_to_text_short_service(
        user_id=current_user.id,
        file=file,
        punctuation=punctuation,
        chinese2digital=chinese2digital,
        end_vad_time=end_vad_time,
    )
    return success(data)


@router.get("/fortune", summary="AI 今日运势")
async def get_fortune(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await ai_service.fortune_service()
    out = FortuneOut(**data)
    return success(out.model_dump(by_alias=True))

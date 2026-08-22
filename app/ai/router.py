# app/ai/router.py（修改后）
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.ai import service as ai_service
from app.ai import model_service
from app.ai import voice_intent
from app.ai.schemas import (
    LlmModelCreateRequest,
    LlmModelListOut,
    LlmModelOut,
    LlmModelUpdateRequest,
    TtsRequest,
    FortuneOut,
    VoiceIntentOut,
    VoiceIntentRequest,
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


@router.post("/voice-intent", summary="小 V 语音指令意图识别")
async def parse_voice_intent(
    req: VoiceIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = db
    data = await voice_intent.resolve_voice_intent(req.utterance)
    return success(VoiceIntentOut(**data).model_dump(by_alias=True))


@router.get("/fortune", summary="AI 今日运势")
async def get_fortune(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await ai_service.fortune_service()
    out = FortuneOut(**data)
    return success(out.model_dump(by_alias=True))


@router.get("/models", summary="获取聊天模型列表")
def get_llm_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = [LlmModelOut(**item) for item in model_service.list_models(db, current_user.id)]
    out = LlmModelListOut(
        items=items,
        default_chat_model_id=model_service.get_default_chat_model_id(db, current_user.id),
    )
    return success(out.model_dump(by_alias=True))


@router.post("/models", summary="新增自定义聊天模型")
def create_llm_model(
    req: LlmModelCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = model_service.create_model(db, current_user.id, req.model_dump(by_alias=False))
    return success(LlmModelOut(**item).model_dump(by_alias=True))


@router.put("/models/{model_id}", summary="更新自定义聊天模型")
def update_llm_model(
    model_id: str,
    req: LlmModelUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = model_service.update_model(
        db,
        current_user.id,
        model_id,
        req.model_dump(by_alias=False, exclude_unset=True),
    )
    return success(LlmModelOut(**item).model_dump(by_alias=True))


@router.delete("/models/{model_id}", summary="删除自定义聊天模型")
def delete_llm_model(
    model_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model_service.delete_model(db, current_user.id, model_id)
    return success(None)

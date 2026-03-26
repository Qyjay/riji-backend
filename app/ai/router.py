"""
AI 功能路由
- POST /ai/tts       文字转语音
- GET  /ai/fortune   AI 运势
"""
import os
import time
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.response import success
from app.serializers import CamelModel

router = APIRouter(prefix="/ai", tags=["AI 功能"])


class TtsRequest(BaseModel):
    text: str
    voice: str = ""


class FortuneOut(CamelModel):
    overall: int
    study: int
    social: int
    health: int
    tip: str
    lucky_color: str
    lucky_number: int


@router.post("/tts", summary="文字转语音")
async def text_to_speech(
    req: TtsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """将文字转换为语音，返回音频文件 URL"""
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    audio_bytes = await client.text_to_speech(req.text, voice_id=req.voice or "female-shaonv")

    # 保存音频文件
    from app.config import settings
    user_dir = os.path.join(settings.UPLOAD_DIR, current_user.id, "tts")
    os.makedirs(user_dir, exist_ok=True)
    filename = f"{uuid4()}.mp3"
    file_path = os.path.join(user_dir, filename)

    if isinstance(audio_bytes, bytes) and audio_bytes:
        with open(file_path, "wb") as f:
            f.write(audio_bytes)
        url = f"/uploads/{current_user.id}/tts/{filename}"
    else:
        url = "/uploads/mock_audio.mp3"

    return success(url)


@router.get("/fortune", summary="AI 今日运势")
async def get_fortune(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成今日 AI 运势"""
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    if client.mock:
        fortune_data = {
            "overall": 4,
            "study": 5,
            "social": 3,
            "health": 4,
            "tip": "今天适合专注学习，保持积极心态！",
            "lucky_color": "暖橙色",
            "lucky_number": 7,
        }
    else:
        import json
        messages = [{
            "role": "user",
            "content": "请为我生成今日运势，以JSON格式返回，包含：overall(1-5整数)、study(1-5)、social(1-5)、health(1-5)、tip(今日提示字符串)、lucky_color(幸运颜色)、lucky_number(幸运数字整数)"
        }]
        try:
            raw = await client.chat_completion(messages)
            # 尝试解析 JSON
            import re
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                fortune_data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found")
        except Exception:
            fortune_data = {
                "overall": 4,
                "study": 4,
                "social": 3,
                "health": 4,
                "tip": "保持积极心态，今天会有好事发生！",
                "lucky_color": "蓝色",
                "lucky_number": 8,
            }

    out = FortuneOut(
        overall=fortune_data.get("overall", 3),
        study=fortune_data.get("study", 3),
        social=fortune_data.get("social", 3),
        health=fortune_data.get("health", 3),
        tip=fortune_data.get("tip", "今日运势良好"),
        lucky_color=fortune_data.get("lucky_color", "蓝色"),
        lucky_number=fortune_data.get("lucky_number", 8),
    )
    return success(out.model_dump(by_alias=True))

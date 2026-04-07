# app/ai/service.py
import os
import json
import re
from uuid import uuid4
from app.config import settings
from app.ai.minimax_client import get_minimax_client


async def text_to_speech_service(user_id: str, text: str, voice: str = "") -> str:
    """
    文字转语音，保存文件并返回访问 URL
    """
    client = get_minimax_client()
    voice_id = voice or "female-shaonv"
    audio_bytes = await client.text_to_speech(text, voice_id=voice_id)

    # 保存文件
    user_dir = os.path.join(settings.UPLOAD_DIR, user_id, "tts")
    os.makedirs(user_dir, exist_ok=True)
    filename = f"{uuid4()}.mp3"
    file_path = os.path.join(user_dir, filename)

    if isinstance(audio_bytes, bytes) and audio_bytes:
        with open(file_path, "wb") as f:
            f.write(audio_bytes)
        url = f"/uploads/{user_id}/tts/{filename}"
    else:
        # Mock 模式可能返回空或假数据，返回默认音频 URL
        url = "/uploads/mock_audio.mp3"
    return url


async def fortune_service() -> dict:
    """
    获取今日运势，返回符合前端格式的字典
    """
    client = get_minimax_client()

    if client.mock:
        # Mock 数据（与 router 中原有的一致）
        return {
            "overall": 4,
            "study": 5,
            "social": 3,
            "health": 4,
            "tip": "今天适合专注学习，保持积极心态！",
            "lucky_color": "暖橙色",
            "lucky_number": 7,
        }
    else:
        # 真实调用 AI
        messages = [{
            "role": "user",
            "content": "请为我生成今日运势，以JSON格式返回，包含：overall(1-5整数)、study(1-5)、social(1-5)、health(1-5)、tip(今日提示字符串)、lucky_color(幸运颜色)、lucky_number(幸运数字整数)"
        }]
        try:
            raw = await client.chat_completion(messages)
            # 提取 JSON
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found")
            # 确保字段完整
            return {
                "overall": data.get("overall", 3),
                "study": data.get("study", 3),
                "social": data.get("social", 3),
                "health": data.get("health", 3),
                "tip": data.get("tip", "今日运势良好"),
                "lucky_color": data.get("lucky_color", "蓝色"),
                "lucky_number": data.get("lucky_number", 8),
            }
        except Exception:
            # 降级返回默认数据
            return {
                "overall": 4,
                "study": 4,
                "social": 3,
                "health": 4,
                "tip": "保持积极心态，今天会有好事发生！",
                "lucky_color": "蓝色",
                "lucky_number": 8,
            }
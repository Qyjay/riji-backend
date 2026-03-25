"""
MiniMax AI API 封装客户端

覆盖 MiniMax 全模态能力：
1. chat_completion  - 非流式对话（M2.7，Anthropic 兼容格式）
2. stream_chat      - 流式对话（M2.7，SSE）
3. generate_image   - 文生图（image-01）
4. text_to_speech   - 文字转语音（speech-2.8-hd）
5. generate_music   - 音乐生成（music-2.5+）

所有接口使用同一个 TokenPlan API Key。
API 文档：https://platform.minimaxi.com/docs/guides/models-intro
"""
import json
from typing import AsyncGenerator, Optional

import httpx

from app.config import settings
from app.response import ApiException, AI_SERVICE_ERROR


class MiniMaxClient:
    """MiniMax API 客户端（全模态）"""

    def __init__(self, api_key: str, api_base: str, model: str):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")  # https://api.minimaxi.com
        self.model = model  # 默认文本模型，如 MiniMax-M2.7
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    # ==================== 文本对话（Anthropic 兼容格式）====================

    async def chat_completion(
        self,
        messages: list,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ) -> str:
        """
        非流式对话，返回完整的回复文本
        使用 Anthropic 兼容 API（M2.7/M2.5 系列）

        Args:
            messages: 对话历史 [{"role": "user", "content": "..."}, ...]
            system_prompt: 系统提示词
            temperature: 温度（0-1，越高越随机）
            max_tokens: 最大生成 token 数

        Returns:
            AI 回复的完整文本
        """
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            **self.headers,
            "anthropic-version": "2023-06-01",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.api_base}/anthropic/v1/messages",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                # Anthropic 格式：content 是一个 list，提取 text 类型的内容
                content_blocks = data.get("content", [])
                text_parts = [
                    block["text"]
                    for block in content_blocks
                    if block.get("type") == "text"
                ]
                return "".join(text_parts)
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"MiniMax API 请求失败: {e.response.status_code}",
                status_code=502,
            )
        except Exception as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"AI 服务异常: {str(e)}",
                status_code=502,
            )

    async def stream_chat(
        self,
        messages: list,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """
        流式对话，以 SSE 方式 yield 每个 chunk 的内容
        使用 Anthropic 兼容 API（M2.7/M2.5 系列）

        Usage:
            async for chunk in client.stream_chat(messages):
                yield f"data: {chunk}\\n\\n"

        Args:
            messages: 对话历史
            system_prompt: 系统提示词
            temperature: 温度
            max_tokens: 最大 token

        Yields:
            每个文本 chunk
        """
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            **self.headers,
            "anthropic-version": "2023-06-01",
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.api_base}/anthropic/v1/messages",
                    headers=headers,
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            event_type = data.get("type", "")
                            # Anthropic 流式格式：content_block_delta 事件
                            if event_type == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        yield text
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"MiniMax 流式请求失败: {e.response.status_code}",
                status_code=502,
            )

    # ==================== 图片生成 ====================

    async def generate_image(
        self,
        prompt: str,
        model: str = "image-01",
        aspect_ratio: str = "1:1",
        n: int = 1,
    ) -> str:
        """
        文生图，返回图片 URL

        Args:
            prompt: 图片描述提示词（最长 1500 字符）
            model: 模型名称，可选 image-01 / image-01-live
            aspect_ratio: 宽高比，可选 1:1 / 16:9 / 4:3 / 3:2 / 2:3 / 3:4 / 9:16
            n: 生成数量（1-9）

        Returns:
            生成的图片 URL（24 小时有效）
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "response_format": "url",
            "n": n,
            "prompt_optimizer": True,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.api_base}/v1/image_generation",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                # 返回第一张图片的 URL
                images = data.get("data", {}).get("image_urls", [])
                if not images:
                    raise ApiException(
                        code=AI_SERVICE_ERROR,
                        message="图片生成失败：未返回图片",
                        status_code=502,
                    )
                return images[0]
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"图片生成失败: {e.response.status_code}",
                status_code=502,
            )
        except ApiException:
            raise
        except Exception as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"图片生成异常: {str(e)}",
                status_code=502,
            )

    # ==================== 语音合成（TTS）====================

    async def text_to_speech(
        self,
        text: str,
        voice_id: str = "male-qn-qingse",
        model: str = "speech-2.8-hd",
        emotion: str = "neutral",
        speed: float = 1.0,
    ) -> bytes:
        """
        文字转语音（TTS），返回音频 bytes

        Args:
            text: 要转换的文字（最长 10000 字符）
            voice_id: 音色 ID，默认 male-qn-qingse
            model: 模型，可选 speech-2.8-hd / speech-2.8-turbo / speech-2.6-hd 等
            emotion: 情绪，如 happy / sad / neutral 等
            speed: 语速（0.5-2.0）

        Returns:
            音频数据（bytes，MP3 格式）
        """
        payload = {
            "model": model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": speed,
                "vol": 1.0,
                "pitch": 0,
                "emotion": emotion,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.api_base}/v1/t2a_v2",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

                # 检查状态
                base_resp = data.get("base_resp", {})
                if base_resp.get("status_code", 0) != 0:
                    raise ApiException(
                        code=AI_SERVICE_ERROR,
                        message=f"TTS 失败: {base_resp.get('status_msg', '未知错误')}",
                        status_code=502,
                    )

                # 音频数据是 hex 编码的字符串
                audio_hex = data.get("data", {}).get("audio", "")
                if not audio_hex:
                    raise ApiException(
                        code=AI_SERVICE_ERROR,
                        message="TTS 失败：未返回音频数据",
                        status_code=502,
                    )
                return bytes.fromhex(audio_hex)
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"TTS 失败: {e.response.status_code}",
                status_code=502,
            )
        except ApiException:
            raise
        except Exception as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"TTS 异常: {str(e)}",
                status_code=502,
            )

    # ==================== 音乐生成 ====================

    async def generate_music(
        self,
        prompt: str = "",
        lyrics: str = "",
        model: str = "music-2.5+",
        is_instrumental: bool = False,
    ) -> str:
        """
        音乐生成，返回音频 URL

        Args:
            prompt: 音乐描述（风格、情绪、场景），如 "流行音乐, 开心, 校园生活"
            lyrics: 歌词（用 \\n 分行，支持 [Verse] [Chorus] 等标签）
                    纯音乐模式下非必填
            model: 模型，可选 music-2.5+（推荐）/ music-2.5
            is_instrumental: 是否纯音乐（无人声），仅 music-2.5+ 支持

        Returns:
            音频 URL（24 小时有效）
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "output_format": "url",
            "is_instrumental": is_instrumental,
            "audio_setting": {
                "sample_rate": 44100,
                "bitrate": 256000,
                "format": "mp3",
            },
        }

        # 非纯音乐模式需要歌词
        if not is_instrumental and lyrics:
            payload["lyrics"] = lyrics
        elif not is_instrumental and not lyrics:
            # 没歌词就让 AI 自动生成
            payload["lyrics_optimizer"] = True

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:  # 音乐生成较慢
                resp = await client.post(
                    f"{self.api_base}/v1/music_generation",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

                # 检查状态
                base_resp = data.get("base_resp", {})
                if base_resp.get("status_code", 0) != 0:
                    raise ApiException(
                        code=AI_SERVICE_ERROR,
                        message=f"音乐生成失败: {base_resp.get('status_msg', '未知错误')}",
                        status_code=502,
                    )

                # 获取音频 URL
                audio_url = data.get("data", {}).get("audio", "")
                if not audio_url:
                    raise ApiException(
                        code=AI_SERVICE_ERROR,
                        message="音乐生成失败：未返回音频",
                        status_code=502,
                    )
                return audio_url
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"音乐生成失败: {e.response.status_code}",
                status_code=502,
            )
        except ApiException:
            raise
        except Exception as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"音乐生成异常: {str(e)}",
                status_code=502,
            )


# ==================== 全局单例 ====================

_minimax_client: Optional[MiniMaxClient] = None


def get_minimax_client() -> MiniMaxClient:
    """获取 MiniMax 客户端单例"""
    global _minimax_client
    if _minimax_client is None:
        _minimax_client = MiniMaxClient(
            api_key=settings.MINIMAX_API_KEY,
            api_base=settings.MINIMAX_API_BASE,
            model=settings.MINIMAX_MODEL,
        )
    return _minimax_client

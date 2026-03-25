"""
MiniMax AI API 封装客户端

提供 4 个基础方法供各模块调用：
1. chat_completion  - 非流式对话
2. stream_chat      - 流式对话（SSE）
3. generate_image   - 文生图
4. text_to_speech   - 文字转语音（TTS）
"""
import json
from typing import AsyncGenerator, Optional

import httpx

from app.config import settings
from app.response import ApiException, AI_SERVICE_ERROR


class MiniMaxClient:
    """MiniMax API 客户端"""

    def __init__(self, api_key: str, api_base: str, model: str):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def chat_completion(
        self,
        messages: list,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ) -> str:
        """
        非流式对话，返回完整的回复文本

        Args:
            messages: 对话历史 [{"role": "user", "content": "..."}, ...]
            system_prompt: 系统提示词
            temperature: 温度（0-1，越高越随机）
            max_tokens: 最大生成 token 数

        Returns:
            AI 回复的完整文本
        """
        # 构建消息列表（加入 system prompt）
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": all_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.api_base}/text/chatcompletion_v2",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                # 提取回复文本
                return data["choices"][0]["message"]["content"]
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
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": all_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.api_base}/text/chatcompletion_v2",
                    headers=self.headers,
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
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"MiniMax 流式请求失败: {e.response.status_code}",
                status_code=502,
            )

    async def generate_image(self, prompt: str) -> str:
        """
        文生图，返回图片 URL

        Args:
            prompt: 图片描述提示词

        Returns:
            生成的图片 URL
        """
        payload = {
            "model": "image-01",
            "prompt": prompt,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.api_base}/image/generation",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                # 提取图片 URL（根据实际 API 响应结构调整）
                return data.get("data", {}).get("image_urls", [""])[0]
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"图片生成失败: {e.response.status_code}",
                status_code=502,
            )
        except Exception as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"图片生成异常: {str(e)}",
                status_code=502,
            )

    async def text_to_speech(self, text: str, voice: str = "male-qn-qingse") -> bytes:
        """
        文字转语音（TTS），返回音频 bytes

        Args:
            text: 要转换的文字
            voice: 音色，默认 male-qn-qingse

        Returns:
            音频数据（bytes，MP3 格式）
        """
        payload = {
            "model": "speech-02-hd",
            "text": text,
            "voice": voice,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.api_base}/tts/generation",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.content
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"TTS 失败: {e.response.status_code}",
                status_code=502,
            )
        except Exception as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"TTS 异常: {str(e)}",
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

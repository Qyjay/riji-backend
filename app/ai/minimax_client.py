"""
MiniMax AI API 封装客户端

覆盖 MiniMax 全模态能力：
1. chat_completion  - 非流式对话（M2.7-highspeed，Anthropic 兼容格式）
2. stream_chat      - 流式对话（M2.7-highspeed，SSE）
3. generate_image   - 文生图（image-01）
4. text_to_speech   - 文字转语音（speech-2.8-hd）
5. generate_music   - 音乐生成（music-2.5+）

支持 Mock 模式：MINIMAX_MOCK=true 时返回模拟数据，不消耗 API 额度。
开发阶段默认开启 Mock，集成测试时关闭。

所有接口使用同一个 TokenPlan API Key。
API 文档：https://platform.minimaxi.com/docs/guides/models-intro
"""
import asyncio
import json
import random
import time
from typing import AsyncGenerator, Optional

import httpx

from app.config import settings
from app.response import ApiException, AI_SERVICE_ERROR


# ==================== Mock 数据 ====================

MOCK_CHAT_RESPONSES = [
    "你好呀！今天过得怎么样？有什么我可以帮你的吗？😊",
    "这是一个很好的问题！让我来帮你分析一下...\n\n首先，我觉得你可以从以下几个方面入手：\n1. 制定一个清晰的计划\n2. 每天坚持一点小进步\n3. 不要给自己太大压力\n\n加油！你一定可以的！",
    "今天的天气真不错呢！适合出去走走，放松一下心情。\n\n记得多喝水，保持好心情哦～",
    "我理解你的感受。大学生活有时候确实会让人感到压力很大，但这些都是成长的一部分。\n\n试试深呼吸，给自己一个拥抱。你已经做得很好了。",
    "哈哈，这个想法太有趣了！让我也来发挥一下想象力...\n\n如果我是一个会写诗的 AI，我会这样写：\n\n窗外细雨绵绵，\n书页轻轻翻转，\n青春的故事，\n藏在每一个平凡的日子里。",
]

MOCK_DIARY_EXPANSION = """今天是充实的一天。

早上起来阳光正好，透过窗帘洒在书桌上，给人一种温暖的感觉。吃完早餐后去了图书馆，坐在靠窗的位置，翻开了那本一直想看的书。

午后和室友去了食堂，点了最爱的番茄炒蛋。饭后在校园里散步，樱花开得正好，粉白色的花瓣随风飘落，像是春天在跟我们打招呼。

晚上回到宿舍，整理了一下笔记，和朋友聊了会天。虽然没有什么惊天动地的大事，但这种平淡的幸福，大概就是大学生活最美好的模样吧。

今天的心情：☀️ 晴朗"""

MOCK_FORTUNE = """🌟 今日运势

**整体运势：★★★★☆**
今天是适合学习和社交的一天！好运指数颇高。

**学业运：★★★★★**
思维活跃，适合攻克难题。下午 2-4 点是效率高峰期，抓住这段时间复习重点内容。

**社交运：★★★★☆**
会遇到聊得来的朋友，也许能收获一段有趣的对话。主动打个招呼吧！

**幸运色：** 淡蓝色
**幸运数字：** 7
**今日建议：** 试试去一个没去过的自习室，也许会有意外收获。

_来自日迹 AI · 仅供娱乐参考_"""

MOCK_IMAGE_URL = "https://placehold.co/1024x1024/EEE/31343C?text=Mock+Image&font=roboto"

MOCK_MUSIC_URL = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"


class MiniMaxClient:
    """MiniMax API 客户端（全模态，支持 Mock）"""

    def __init__(self, api_key: str, api_base: str, model: str, mock: bool = False):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.mock = mock
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    # ==================== 文本对话 ====================

    async def chat_completion(
        self,
        messages: list,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ) -> str:
        """
        非流式对话，返回完整的回复文本

        Mock 模式：返回随机测试回复
        真实模式：调用 M2.7-highspeed Anthropic 兼容 API
        """
        if self.mock:
            await asyncio.sleep(0.3)  # 模拟网络延迟
            # 根据消息内容返回不同的 mock 数据
            last_msg = messages[-1]["content"] if messages else ""
            if "运势" in last_msg or "fortune" in last_msg.lower():
                return MOCK_FORTUNE
            if "日记" in last_msg or "扩写" in last_msg:
                return MOCK_DIARY_EXPANSION
            return random.choice(MOCK_CHAT_RESPONSES)

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
        流式对话，yield 每个 chunk

        Mock 模式：逐字 yield 模拟流式效果
        真实模式：调用 M2.7-highspeed Anthropic 兼容 API（SSE）
        """
        if self.mock:
            response = random.choice(MOCK_CHAT_RESPONSES)
            for char in response:
                await asyncio.sleep(0.03)  # 模拟逐字输出
                yield char
            return

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

        Mock 模式：返回占位图 URL
        """
        if self.mock:
            await asyncio.sleep(0.5)
            # 根据 aspect_ratio 返回不同尺寸的占位图
            sizes = {
                "1:1": "1024x1024",
                "16:9": "1280x720",
                "4:3": "1152x864",
                "3:2": "1248x832",
                "2:3": "832x1248",
                "3:4": "864x1152",
                "9:16": "720x1280",
            }
            size = sizes.get(aspect_ratio, "1024x1024")
            return f"https://placehold.co/{size}/E8D5F5/6B21A8?text=Mock+AI+Image&font=roboto"

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
        文字转语音，返回音频 bytes

        Mock 模式：返回一段空白 MP3 数据
        """
        if self.mock:
            await asyncio.sleep(0.3)
            # 返回最小有效 MP3（静音帧）
            # 实际开发时前端能正常播放，只是没有声音
            return bytes.fromhex(
                "fff3e464000000000000000000000000"
                "000000000000000000000000000000"
                "00" * 100
            )

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

                base_resp = data.get("base_resp", {})
                if base_resp.get("status_code", 0) != 0:
                    raise ApiException(
                        code=AI_SERVICE_ERROR,
                        message=f"TTS 失败: {base_resp.get('status_msg', '未知错误')}",
                        status_code=502,
                    )

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

        Mock 模式：返回测试音频 URL
        """
        if self.mock:
            await asyncio.sleep(1.0)  # 音乐生成较慢，模拟更长延迟
            return MOCK_MUSIC_URL

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

        if not is_instrumental and lyrics:
            payload["lyrics"] = lyrics
        elif not is_instrumental and not lyrics:
            payload["lyrics_optimizer"] = True

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    f"{self.api_base}/v1/music_generation",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

                base_resp = data.get("base_resp", {})
                if base_resp.get("status_code", 0) != 0:
                    raise ApiException(
                        code=AI_SERVICE_ERROR,
                        message=f"音乐生成失败: {base_resp.get('status_msg', '未知错误')}",
                        status_code=502,
                    )

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
            mock=settings.MINIMAX_MOCK,
        )
    return _minimax_client

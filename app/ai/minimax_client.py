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

    # ==================== v2 新增方法 ====================

    async def extract_emotion(self, text: str) -> dict:
        """
        AI 情绪提取，输出 JSON {label, score, emoji}

        Mock 模式：返回固定情绪数据
        真实模式：调用 chat_completion，要求输出 JSON
        """
        if self.mock:
            await asyncio.sleep(0.2)
            import random
            emotions = [
                {"label": "开心", "score": 0.88, "emoji": "😊"},
                {"label": "平静", "score": 0.75, "emoji": "😌"},
                {"label": "感动", "score": 0.82, "emoji": "🥹"},
                {"label": "期待", "score": 0.70, "emoji": "🤩"},
            ]
            return random.choice(emotions)

        system = (
            "你是情绪分析助手。分析用户文本的主要情绪，"
            "严格返回如下 JSON 格式（无其他文字）：\n"
            '{"label": "情绪名称", "score": 0.85, "emoji": "😊"}\n'
            "情绪类型：开心、悲伤、愤怒、平静、感动、焦虑、期待、无聊。"
        )
        messages = [{"role": "user", "content": f"分析这段文字的情绪：{text}"}]
        try:
            resp = await self.chat_completion(messages, system_prompt=system, temperature=0.3)
            return json.loads(resp.strip())
        except Exception:
            return {"label": "平静", "score": 0.5, "emoji": "😌"}

    async def polish_text(self, text: str, style: str) -> str:
        """
        按风格润色文字

        Mock 模式：返回固定润色文本
        真实模式：调用 chat_completion
        """
        if self.mock:
            await asyncio.sleep(0.3)
            style_prefix = {
                "文艺": "在某个平凡而特别的午后，",
                "幽默": "好嘛，",
                "简洁": "",
                "温暖": "轻轻地，",
            }
            prefix = style_prefix.get(style, "")
            return f"{prefix}{text}（{style}风格·Mock）"

        system = (
            f"你是专业的文字润色师，擅长将普通文字改写成{style}风格。"
            "直接输出润色后的文字，不要解释，不要前缀。"
        )
        messages = [{"role": "user", "content": f"请将以下文字润色为{style}风格：\n\n{text}"}]
        return await self.chat_completion(messages, system_prompt=system, temperature=0.9)

    async def generate_diary(
        self,
        materials_text: str,
        weather: str = "",
        special_date: str = "",
        user_style: str = "",
    ) -> dict:
        """
        根据素材生成日记，返回 {title, content, emotion_summary}

        Mock 模式：返回固定日记数据
        """
        if self.mock:
            await asyncio.sleep(0.5)
            return {
                "title": "平凡日子里的小确幸",
                "content": MOCK_DIARY_EXPANSION,
                "emotion_summary": {
                    "dominant": "平静",
                    "distribution": {"开心": 0.4, "平静": 0.4, "感动": 0.2},
                },
            }

        style_hint = f"用户偏好{user_style}风格。" if user_style else ""
        weather_hint = f"今天天气：{weather}。" if weather else ""
        special_hint = f"今天是特殊的日子：{special_date}。" if special_date else ""

        system = (
            "你是日记写作助手，帮助用户将零散的生活素材整理成有温度的日记。\n"
            f"{style_hint}{weather_hint}{special_hint}\n"
            "请返回如下 JSON（无其他文字）：\n"
            '{"title": "日记标题", "content": "正文（300字以上）", '
            '"emotion_summary": {"dominant": "主要情绪", "distribution": {"情绪": 0.5}}}'
        )
        messages = [{"role": "user", "content": f"请根据以下素材生成今天的日记：\n\n{materials_text}"}]
        try:
            resp = await self.chat_completion(messages, system_prompt=system, temperature=0.85)
            return json.loads(resp.strip())
        except Exception:
            return {
                "title": "今日记录",
                "content": materials_text,
                "emotion_summary": {"dominant": "平静", "distribution": {}},
            }

    async def extract_info(self, diary_content: str) -> dict:
        """
        从日记提取纪念日/人物/偏好，返回 {anniversaries, persons, preferences}

        Mock 模式：返回固定提取结果
        """
        if self.mock:
            await asyncio.sleep(0.3)
            return {
                "anniversaries": [
                    {"title": "和朋友聚餐", "date": "03-25", "related_person": "室友"}
                ],
                "persons": [
                    {"name": "小明", "relation": "室友"}
                ],
                "preferences": ["美食", "散步", "图书馆"],
            }

        system = (
            "你是信息提取助手。从日记中提取关键信息，"
            "严格返回如下 JSON（无其他文字）：\n"
            '{"anniversaries": [{"title": "事件名", "date": "MM-DD", "related_person": ""}], '
            '"persons": [{"name": "姓名", "relation": "关系"}], '
            '"preferences": ["偏好1", "偏好2"]}'
        )
        messages = [{"role": "user", "content": f"从以下日记中提取信息：\n\n{diary_content}"}]
        try:
            resp = await self.chat_completion(messages, system_prompt=system, temperature=0.3)
            return json.loads(resp.strip())
        except Exception:
            return {"anniversaries": [], "persons": [], "preferences": []}

    async def generate_portrait(
        self, diary_summaries: str, chat_summaries: str = ""
    ) -> dict:
        """
        根据日记+聊天记录生成用户画像

        Mock 模式：返回固定画像
        """
        if self.mock:
            await asyncio.sleep(0.5)
            return {
                "personality": "开朗、细腻、对生活充满热情的理想主义者",
                "writing_style": "喜欢用细节描写日常，语言温暖而富有诗意",
                "interests": ["读书", "散步", "美食", "音乐"],
                "preferences": {"food": "日料", "activity": "图书馆", "music": "轻音乐"},
                "relations": {"室友小明": "好友", "导师": "亦师亦友"},
            }

        system = (
            "你是用户画像分析师。根据用户的日记和聊天记录，"
            "生成用户画像，严格返回如下 JSON：\n"
            '{"personality": "性格描述", "writing_style": "写作风格", '
            '"interests": ["兴趣1"], "preferences": {}, "relations": {}}'
        )
        content = f"日记摘要：\n{diary_summaries}"
        if chat_summaries:
            content += f"\n\n聊天摘要：\n{chat_summaries}"
        messages = [{"role": "user", "content": content}]
        try:
            resp = await self.chat_completion(messages, system_prompt=system, temperature=0.7)
            return json.loads(resp.strip())
        except Exception:
            return {
                "personality": "", "writing_style": "",
                "interests": [], "preferences": {}, "relations": {},
            }

    async def generate_match_report(self, portrait_a: dict, portrait_b: dict) -> str:
        """
        生成两个用户的 AI 匹配报告

        Mock 模式：返回固定报告
        """
        if self.mock:
            await asyncio.sleep(0.3)
            return (
                "🌟 你们的匹配度非常高！\n\n"
                "**共同兴趣：** 都喜欢读书和美食探店，很容易找到共同话题。\n"
                "**性格互补：** 一个沉稳细腻，一个活泼开朗，相处起来会很有趣。\n"
                "**建议：** 可以一起去试试新开的那家日料店，或者在图书馆相约自习。"
            )

        system = (
            "你是社交匹配分析师，根据两个用户的画像分析匹配度，"
            "给出友好、有温度的匹配报告（200字以内）。"
        )
        messages = [
            {
                "role": "user",
                "content": (
                    f"用户A画像：{json.dumps(portrait_a, ensure_ascii=False)}\n"
                    f"用户B画像：{json.dumps(portrait_b, ensure_ascii=False)}\n"
                    "请分析两人的匹配度并给出建议。"
                ),
            }
        ]
        return await self.chat_completion(messages, system_prompt=system, temperature=0.8)

    async def summarize_chat_session(self, messages: list) -> dict:
        """将一段对话概括为素材标题 + 摘要 + 情绪 + 标签"""
        if self.mock:
            await asyncio.sleep(0.3)
            return {
                "title": "和 AI 的一段对话",
                "summary": "用户和 AI 聊了一段有趣的对话，讨论了日常生活中的各种话题。",
                "mood": "平静",
                "mood_emoji": "😌",
                "tags": ["日常", "对话"]
            }

        conversation = "\n".join([
            f"{'用户' if m['role']=='user' else 'AI'}: {m['content']}"
            for m in messages
        ])

        system_prompt = """你是一个对话分析助手。请分析以下对话内容，提取结构化信息。
必须返回严格的 JSON 格式，不要包含任何其他文字：
{
  "title": "简短标题（10字以内，概括对话主题）",
  "summary": "2~3句话的摘要，描述对话的主要内容",
  "mood": "情绪标签（开心/难过/平静/吐槽/焦虑/兴奋/感动/无聊/困惑/释然）",
  "mood_emoji": "对应的emoji（一个）",
  "tags": ["话题标签1", "话题标签2"]
}"""

        user_prompt = f"对话内容：\n{conversation}"

        result_text = await self.chat_completion(
            [{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt
        )

        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            return {
                "title": "对话记录",
                "summary": conversation[:200],
                "mood": "平静",
                "mood_emoji": "😐",
                "tags": ["对话"]
            }


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

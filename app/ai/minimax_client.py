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
import re
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

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": full_messages,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                resp = await client.post(
                    f"{self.api_base}/v1/chat/completions",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"MiniMax API 请求失败: {e.response.status_code} {e.response.text[:200]}",
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

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": full_messages,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                async with client.stream(
                    "POST",
                    f"{self.api_base}/v1/chat/completions",
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
                            text = delta.get("content", "")
                            if text:
                                yield text
                        except (json.JSONDecodeError, IndexError):
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
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
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
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
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
            async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
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

    @staticmethod
    def _default_emotion_emoji(label: str) -> str:
        mapping = {
            "开心": "😊",
            "难过": "😢",
            "愤怒": "😠",
            "平静": "😌",
            "感动": "🥹",
            "焦虑": "😟",
            "期待": "🤩",
            "无聊": "😑",
        }
        return mapping.get(label, "😐")

    @classmethod
    def _heuristic_emotion(cls, text: str) -> dict:
        content = str(text or "").strip()
        if not content:
            return {"label": "平静", "score": 0.5, "emoji": "😌"}

        lowered = content.lower()
        rules = [
            ("难过", 0.86, "😢", ["想哭", "哭", "难过", "伤心", "悲伤", "委屈", "心碎", "崩溃", "低落", "沮丧", "失落", "难受", "emo"]),
            ("愤怒", 0.84, "😠", ["生气", "愤怒", "火大", "气死", "烦死", "暴躁", "恼火", "讨厌", "破防"]),
            ("焦虑", 0.82, "😟", ["焦虑", "紧张", "压力", "担心", "害怕", "慌", "忐忑", "不安", "睡不着"]),
            ("开心", 0.88, "😊", ["开心", "高兴", "快乐", "愉快", "幸福", "太棒", "好开心", "兴奋", "喜悦"]),
            ("感动", 0.83, "🥹", ["感动", "暖心", "泪目", "被治愈", "触动", "谢谢你", "温暖"]),
            ("期待", 0.8, "🤩", ["期待", "盼", "希望", "想要", "想去", "明天一定", "跃跃欲试"]),
            ("无聊", 0.72, "😑", ["无聊", "没劲", "空虚", "发呆", "不知道干嘛", "好闲"]),
            ("平静", 0.65, "😌", ["平静", "还行", "一般", "普通", "正常"]),
        ]

        for label, score, emoji, keywords in rules:
            if any(keyword in lowered for keyword in keywords):
                return {"label": label, "score": score, "emoji": emoji}

        return {"label": "平静", "score": 0.55, "emoji": "😌"}

    @staticmethod
    def _extract_first_json_object(raw: str) -> Optional[dict]:
        text = str(raw or "").strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None

        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    @classmethod
    def _normalize_emotion_payload(cls, payload: dict, fallback_text: str = "") -> dict:
        aliases = {
            "悲伤": "难过",
            "伤心": "难过",
            "生气": "愤怒",
            "平和": "平静",
            "紧张": "焦虑",
            "激动": "期待",
            "兴奋": "期待",
            "吐槽": "无聊",
        }
        allowed_labels = {"开心", "难过", "愤怒", "平静", "感动", "焦虑", "期待", "无聊"}

        raw_label = str((payload or {}).get("label") or "").strip()
        label = aliases.get(raw_label, raw_label)
        if label not in allowed_labels:
            label = cls._heuristic_emotion(fallback_text)["label"]

        try:
            score = float((payload or {}).get("score", 0.0))
        except Exception:
            score = 0.0

        if score > 1 and score <= 100:
            score /= 100
        if score <= 0:
            score = cls._heuristic_emotion(fallback_text)["score"]
        score = max(0.0, min(1.0, score))

        emoji = str((payload or {}).get("emoji") or "").strip()
        if not emoji:
            emoji = cls._default_emotion_emoji(label)

        return {
            "label": label,
            "score": round(score, 2),
            "emoji": emoji,
        }

    # ==================== v2 新增方法 ====================

    async def extract_emotion(self, text: str) -> dict:
        """
        AI 情绪提取，输出 JSON {label, score, emoji}

        Mock 模式：返回固定情绪数据
        真实模式：调用 chat_completion，要求输出 JSON
        """
        if self.mock:
            await asyncio.sleep(0.2)
            return self._heuristic_emotion(text)

        system = (
            "你是情绪分析助手。分析用户文本的主要情绪，"
            "严格返回如下 JSON 格式（无其他文字）：\n"
            '{"label": "情绪名称", "score": 0.85, "emoji": "😊"}\n'
            "情绪类型限定为：开心、难过、愤怒、平静、感动、焦虑、期待、无聊。"
        )
        messages = [{"role": "user", "content": f"分析这段文字的情绪：{text}"}]
        try:
            resp = await self.chat_completion(messages, system_prompt=system, temperature=0.3)
            payload = self._extract_first_json_object(resp)
            if not payload:
                return self._heuristic_emotion(text)
            return self._normalize_emotion_payload(payload, fallback_text=text)
        except Exception:
            return self._heuristic_emotion(text)

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

        style_system_prompts = {
            "文艺": (
                "你是中文文艺写作编辑。"
                "请在忠实原文事实的前提下，使用细腻、克制、具画面感的表达进行润色。"
                "可适度使用比喻与意象，但不得堆砌辞藻，不得改写事实。"
            ),
            "幽默": (
                "你是中文幽默文案编辑。"
                "请以轻松、俏皮、友好的口吻润色文本，允许自然的包袱和自嘲感。"
                "幽默要建立在原文事实之上，不得低俗，不得引入攻击性表达。"
            ),
            "简洁": (
                "你是中文简洁风格编辑。"
                "请压缩冗余表达，保留核心信息，语言清楚直接、节奏明快。"
                "优先短句，避免空泛修辞，不得遗漏关键事实。"
            ),
            "温暖": (
                "你是中文治愈系写作编辑。"
                "请用温柔、真诚、带有支持感的语气润色文本，重点传达情绪温度与人与人之间的连接。"
                "保持自然不过度抒情，不得新增原文不存在的情节。"
            ),
        }
        style_temperature = {
            "文艺": 0.7,
            "幽默": 0.75,
            "简洁": 0.35,
            "温暖": 0.6,
        }

        normalized_style = style if style in style_system_prompts else "简洁"
        system = style_system_prompts[normalized_style]

        user_prompt = (
            "请润色以下文本。\n"
            f"目标风格：{normalized_style}\n"
            "执行约束：\n"
            "1. 不改变人物、时间、地点、事件与结论。\n"
            "2. 不新增原文中不存在的信息。\n"
            "3. 不输出解释，不输出标题，只输出润色后的正文。\n"
            "4. 保持中文表达自然流畅。\n\n"
            f"原文：\n{text}"
        )

        messages = [{"role": "user", "content": user_prompt}]
        return await self.chat_completion(
            messages,
            system_prompt=system,
            temperature=style_temperature[normalized_style],
        )

    @staticmethod
    def _normalize_chat_summary_to_first_person(text: str) -> str:
        """将第三人称 chat 摘要归一成第一人称，便于写入素材/日记。"""
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        if not normalized:
            return ""

        replacements = [
            ("用户和AI", "我和AI"),
            ("用户与AI", "我和AI"),
            ("用户跟AI", "我和AI"),
            ("用户同AI", "我和AI"),
            ("用户和 AI", "我和AI"),
            ("用户与 AI", "我和AI"),
            ("用户跟 AI", "我和AI"),
            ("用户同 AI", "我和AI"),
            ("用户：", "我："),
            ("用户:", "我:"),
        ]
        for old, new in replacements:
            normalized = normalized.replace(old, new)

        return normalized

    @classmethod
    def _extract_material_snippets(cls, materials_text: str, max_items: int = 6) -> list[str]:
        """从素材提示词中提取可读片段，用于本地降级成文。"""
        snippets = []
        for raw_line in str(materials_text or "").splitlines():
            line = str(raw_line or "").strip()
            if not line:
                continue

            # 去掉常见前缀：[09:30] [文字] / [对话记录] / (09:00~09:20)
            line = re.sub(r"^\[[^\]]+\]\s*", "", line)
            line = re.sub(r"^\[[^\]]+\]\s*", "", line)
            line = re.sub(r"^\([^\)]+\)\s*", "", line)
            line = re.sub(r"\s+", " ", line).strip("；;，,。 ")
            line = cls._normalize_chat_summary_to_first_person(line)
            if not line:
                continue

            if line not in snippets:
                snippets.append(line)
            if len(snippets) >= max_items:
                break

        return snippets

    @classmethod
    def _build_fallback_diary_content(
        cls,
        materials_text: str,
        weather_hint: str = "",
        special_hint: str = "",
        dominant_emotion: str = "",
    ) -> str:
        """在模型失败时本地兜底生成连贯日记，避免原样拼接素材。"""
        snippets = cls._extract_material_snippets(materials_text)
        if not snippets:
            snippets = ["今天没有记录太多细节，我给自己留了一点安静整理思绪的时间"]

        intro = "今天我把一天里零散的片段慢慢回想了一遍。"
        if weather_hint:
            intro += f"{weather_hint}的天气，也让这一天有了更清晰的底色。"
        if special_hint:
            intro += f"对我来说，这一天还有一点特别：{special_hint}。"

        timeline = [f"开始的时候，{snippets[0]}。"]
        for item in snippets[1:-1]:
            timeline.append(f"后来，{item}。")
        if len(snippets) > 1:
            timeline.append(f"到一天快结束时，{snippets[-1]}。")

        mood = dominant_emotion or "平静"
        closing = (
            f"把这些经历串起来看，我的整体感受更偏向{mood}。"
            "和 AI 聊过、也重新梳理过之后，我更清楚自己今天真正记住了什么。"
        )

        return "\n\n".join([intro, "".join(timeline), closing])

    @staticmethod
    def _build_first_person_chat_fallback_summary(messages: list[dict]) -> str:
        """会话摘要 JSON 解析失败时，生成第一人称摘要兜底。"""
        user_lines = []
        ai_lines = []
        for item in messages or []:
            role = str((item or {}).get("role") or "")
            content = re.sub(r"\s+", " ", str((item or {}).get("content") or "").strip())
            if not content:
                continue
            if role == "user":
                user_lines.append(content)
            elif role == "assistant":
                ai_lines.append(content)

        parts = []
        if user_lines:
            parts.append(f"我和AI聊到了{user_lines[0][:60]}。")
        if len(user_lines) > 1:
            parts.append(f"我还提到了{user_lines[1][:60]}。")
        if ai_lines:
            parts.append(f"AI 的回应是{ai_lines[0][:60]}。")
        parts.append("这段对话让我把想法梳理得更清楚，也更知道接下来该怎么做。")

        return "".join(parts)

    async def generate_diary(
        self,
        materials_text: str,
        weather: str = "",
        special_date: str = "",
        user_style: str = "",
        daily_emotion_summary: Optional[dict] = None,
    ) -> dict:
        """
        根据素材生成日记，返回 {title, content, emotion_summary, ai_tags}

        Mock 模式：返回固定日记数据
        """
        def _calc_distribution(items: list, dominant_label: str) -> dict:
            """根据趋势条目计算各情绪占比，确保 distribution 总和为 1。"""
            counts = {}
            for item in items:
                label = str(item.get("label") or "").strip()
                if not label:
                    continue
                counts[label] = counts.get(label, 0) + 1

            total = sum(counts.values())
            if total <= 0:
                fallback = dominant_label or "平静"
                return {fallback: 1.0}

            distribution = {k: round(v / total, 4) for k, v in counts.items()}
            delta = round(1.0 - sum(distribution.values()), 4)
            if delta != 0:
                max_key = max(distribution, key=distribution.get)
                distribution[max_key] = round(distribution[max_key] + delta, 4)
            return distribution

        if self.mock:
            await asyncio.sleep(0.5)
            return {
                "title": "平凡日子里的小确幸",
                "content": MOCK_DIARY_EXPANSION,
                "emotion_summary": {
                    "dominant": "平静",
                    "distribution": {"平静": 1.0},
                },
                "ai_tags": ["日常记录", "校园生活", "今日心情"],
            }

        style_hint = user_style or "自然、真诚"
        weather_hint = weather.strip()
        special_hint = special_date.strip()

        dominant = ""
        trend_items = []
        if isinstance(daily_emotion_summary, dict):
            dominant = (daily_emotion_summary.get("dominant") or "").strip()
            trend_items = daily_emotion_summary.get("trend", []) or []
        distribution = _calc_distribution(trend_items, dominant)

        trend_lines = []
        for item in trend_items[:24]:
            try:
                hour = int(item.get("hour", 0))
            except Exception:
                hour = 0
            label = (item.get("label") or "").strip() or "平静"
            score = item.get("score", 50)
            trend_lines.append(f"- {hour:02d}:00 {label}（{score}）")
        trend_text = "\n".join(trend_lines) if trend_lines else "- 无有效趋势数据"

        weather_context = weather_hint if weather_hint else "未提供天气信息（严禁臆造具体天气）"
        special_context = special_hint if special_hint else "无"
        dominant_context = dominant if dominant else "未识别"

        system = (
            "你是“日迹”应用的日记整理助手，负责把用户当天素材整理成一篇完整、真实、连贯的中文日记。\n\n"
            "【写作目标】\n"
            "1. 严格基于素材事实写作，所有关键事件必须在素材中有依据。\n"
            "2. 将素材按时间线自然串联，形成有起承转合的完整叙事。\n"
            "3. 将当日情绪融入叙事过程，体现心境变化与内在感受。\n"
            "4. 若提供了天气信息，必须在正文中自然写入天气。\n\n"
            "【硬性约束】\n"
            "1. 不得逐条拼接素材，不得写成清单、流水账、分点罗列。\n"
            "2. 不得虚构素材中不存在的人、事、地点、时间、结论。\n"
            "3. 不得遗漏核心素材；每条素材都要被合理吸收进叙事。\n"
            "4. 语言要自然，有画面感，但保持事实忠实。\n"
            "5. 正文不少于 300 字。\n\n"
            "6. 若素材中包含“对话记录”，必须改写成第一人称经历（我和AI聊了什么、我怎么想），"
            "不得直接复制“用户: / AI:”对话原文。\n\n"
            "【输出格式】\n"
            "仅输出合法 JSON，不要输出 markdown 代码块，不要输出任何解释文字。\n"
            "JSON 结构如下：\n"
            '{"title": "日记标题（<=18字）", "content": "完整正文", "emotion_summary": {"dominant": "主要情绪", "distribution": {"开心": 0.6, "平静": 0.4}}, "ai_tags": ["标签1", "标签2", "标签3"]}'
        )

        user_prompt = (
            "请根据以下上下文生成今日日记：\n\n"
            f"- 用户偏好风格：{style_hint}\n"
            f"- 天气信息：{weather_context}\n"
            f"- 特殊日期：{special_context}\n"
            f"- 当日主情绪：{dominant_context}\n"
            "- 当日情绪趋势：\n"
            f"{trend_text}\n\n"
            "- 当日素材（已按时间排序）：\n"
            f"{materials_text}"
        )
        messages = [{"role": "user", "content": user_prompt}]
        try:
            resp = await self.chat_completion(messages, system_prompt=system, temperature=0.85)
            raw = resp.strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                import re
                match = re.search(r"\{[\s\S]*\}", raw)
                if match:
                    return json.loads(match.group(0))
                raise
        except Exception:
            fallback_content = self._build_fallback_diary_content(
                materials_text,
                weather_hint=weather_hint,
                special_hint=special_hint,
                dominant_emotion=dominant,
            )
            return {
                "title": "今日记录",
                "content": fallback_content,
                "emotion_summary": {"dominant": dominant or "平静", "distribution": distribution},
                "ai_tags": ["日常记录", "生活片段", "今日随记"],
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
            "你是日记信息提取助手，请从文本中提取结构化信息。\n"
            "重点识别：纪念日、周年、交往/相识天数、生日、首次事件等可纪念节点。\n\n"
            "【提取规则】\n"
            "1. anniversaries: 提取有纪念意义的事件，尤其包含“纪念日/周年/满X年/第X年/生日/首次”等表述。\n"
            "2. 若出现相对日期（如“今天是一周年”），可结合文意推断为可保存的简写日期；无法确定时可保留原文短语，但 date 字段不能为空。\n"
            "3. persons: 提取出现的人名与关系（室友/同学/家人/恋人/老师等）。\n"
            "4. preferences: 提取稳定偏好（食物、活动、地点、兴趣），去重后输出。\n"
            "5. 严禁编造；无信息则返回空数组。\n\n"
            "【输出要求】\n"
            "仅输出合法 JSON，不要输出解释或 markdown。\n"
            "字段结构固定为：\n"
            '{"anniversaries": [{"title": "事件名", "date": "MM-DD或可保存日期", "related_person": "相关人物"}], '
            '"persons": [{"name": "姓名", "relation": "关系"}], '
            '"preferences": ["偏好1", "偏好2"]}'
        )
        messages = [{"role": "user", "content": f"从以下日记中提取信息：\n\n{diary_content}"}]
        try:
            resp = await self.chat_completion(messages, system_prompt=system, temperature=0.3)
            raw = resp.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                import re
                # 兼容模型返回 ```json ... ``` 或前后有解释文本
                match = re.search(r"\{[\s\S]*\}", raw)
                if not match:
                    raise
                data = json.loads(match.group(0))

            anniversaries = data.get("anniversaries", []) if isinstance(data, dict) else []
            persons = data.get("persons", []) if isinstance(data, dict) else []
            preferences = data.get("preferences", []) if isinstance(data, dict) else []

            if not isinstance(anniversaries, list):
                anniversaries = []
            if not isinstance(persons, list):
                persons = []
            if not isinstance(preferences, list):
                preferences = []

            return {
                "anniversaries": anniversaries,
                "persons": persons,
                "preferences": preferences,
            }
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
                "summary": "我和 AI 聊了今天的状态，也把自己在意的事梳理了一遍，这段对话让我更清楚接下来该怎么做。",
                "mood": "平静",
                "mood_emoji": "😌",
                "tags": ["日常", "对话"]
            }

        conversation = "\n".join([
            f"{'用户' if m['role']=='user' else 'AI'}: {m['content']}"
            for m in messages
        ])

        system_prompt = """你是一个“对话素材整理助手”。请把对话整理为可沉淀到素材库的结构化信息。
其中 summary 字段必须满足：
1) 使用第一人称“我”来叙述；
2) 体现“我和 AI 聊了什么 + 我当时的想法/感受 + 对我产生的帮助或变化”；
3) 禁止使用“用户”作为主语，禁止写成“AI 总结/系统总结”的口吻。

必须返回严格的 JSON 格式，不要包含任何其他文字：
{
  "title": "简短标题（10字以内，概括对话主题）",
    "summary": "2~4句话，第一人称，描述这段对话对我的意义",
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
            payload = json.loads(result_text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", result_text)
            if match:
                try:
                    payload = json.loads(match.group(0))
                except Exception:
                    payload = None
            else:
                payload = None

        if isinstance(payload, dict):
            payload["summary"] = self._normalize_chat_summary_to_first_person(payload.get("summary", ""))
            return payload

        return {
            "title": "对话记录",
            "summary": self._build_first_person_chat_fallback_summary(messages),
            "mood": "平静",
            "mood_emoji": "😐",
            "tags": ["对话"]
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", "", str(text or "").strip().lower())

    @staticmethod
    def _tokenize_for_similarity(text: str) -> set[str]:
        raw = str(text or "")
        normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", raw.lower()).strip()
        words = [w for w in normalized.split() if w]
        if words:
            return set(words)

        # 中文短句兜底：按字比较相似度，过滤空白。
        return {ch for ch in raw if ch.strip()}

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        union = a | b
        if not union:
            return 0.0
        return len(a & b) / len(union)

    async def detect_duplicate_chat_material(
        self,
        candidate_summary: str,
        existing_materials: list[dict],
    ) -> dict:
        """
        判断对话摘要是否与当日已有素材重复。

        返回格式：
        {
          "is_duplicate": bool,
          "duplicate_material_id": "string|None",
          "reason": "string",
          "confidence": 0.0~1.0,
        }
        """
        candidates = [
            {
                "id": str(item.get("id") or ""),
                "type": str(item.get("type") or ""),
                "content": str(item.get("content") or "").strip(),
            }
            for item in (existing_materials or [])
            if str(item.get("content") or "").strip()
        ]

        if not candidate_summary.strip() or not candidates:
            return {
                "is_duplicate": False,
                "duplicate_material_id": None,
                "reason": "no-candidate-or-existing-materials",
                "confidence": 0.0,
            }

        if self.mock:
            target = self._normalize_text(candidate_summary)
            target_tokens = self._tokenize_for_similarity(candidate_summary)

            best_item = None
            best_score = 0.0

            for item in candidates:
                content = item["content"]
                normalized = self._normalize_text(content)
                if not normalized:
                    continue

                # 强重复：文本完全一致或包含关系（长度至少 12 字符避免误判）。
                if target == normalized:
                    return {
                        "is_duplicate": True,
                        "duplicate_material_id": item["id"] or None,
                        "reason": "exact-same-content",
                        "confidence": 1.0,
                    }

                if len(target) >= 12 and (target in normalized or normalized in target):
                    return {
                        "is_duplicate": True,
                        "duplicate_material_id": item["id"] or None,
                        "reason": "high-overlap-by-substring",
                        "confidence": 0.92,
                    }

                score = self._jaccard(target_tokens, self._tokenize_for_similarity(content))
                if score > best_score:
                    best_score = score
                    best_item = item

            if best_item and best_score >= 0.72:
                return {
                    "is_duplicate": True,
                    "duplicate_material_id": best_item["id"] or None,
                    "reason": "high-semantic-overlap-in-mock-heuristic",
                    "confidence": round(best_score, 3),
                }

            return {
                "is_duplicate": False,
                "duplicate_material_id": None,
                "reason": "mock-heuristic-not-duplicate",
                "confidence": round(best_score, 3),
            }

        materials_for_prompt = [
            {
                "id": item["id"],
                "type": item["type"],
                "content": item["content"],
            }
            for item in candidates[:30]
        ]

        id_set = {item["id"] for item in materials_for_prompt if item["id"]}

        system_prompt = (
            "你是素材去重助手。需要判断‘候选对话素材摘要’是否与‘已有素材列表’语义重复。"
            "重复定义：描述同一事件/同一体验，核心信息高度重合，即使措辞不同也算重复。"
            "必须只返回严格 JSON，不要返回任何额外文字："
            "{\"is_duplicate\": true|false, \"duplicate_material_id\": \"字符串或空字符串\","
            " \"reason\": \"简短原因\", \"confidence\": 0到1之间数字}"
        )

        user_prompt = (
            "候选对话素材摘要：\n"
            f"{candidate_summary.strip()}\n\n"
            "已有素材列表（JSON）：\n"
            f"{json.dumps(materials_for_prompt, ensure_ascii=False)}"
        )

        raw = await self.chat_completion(
            [{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=400,
        )

        try:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                match = re.search(r"\{[\s\S]*\}", raw)
                if not match:
                    raise
                payload = json.loads(match.group(0))
        except Exception:
            return {
                "is_duplicate": False,
                "duplicate_material_id": None,
                "reason": "json-parse-failed",
                "confidence": 0.0,
            }

        is_duplicate = bool(payload.get("is_duplicate", False))
        duplicate_id = str(payload.get("duplicate_material_id") or "").strip() or None
        reason = str(payload.get("reason") or "").strip() or "model-judgement"

        try:
            confidence = float(payload.get("confidence", 0.0))
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(confidence, 1.0))

        if duplicate_id and duplicate_id not in id_set:
            duplicate_id = None

        if is_duplicate and not duplicate_id and id_set:
            # 容错：模型判断重复但未返回 id 时，优先返回第一条已有素材 id。
            duplicate_id = next(iter(id_set))

        return {
            "is_duplicate": is_duplicate,
            "duplicate_material_id": duplicate_id,
            "reason": reason,
            "confidence": confidence,
        }


# ==================== 全局单例 ====================

_minimax_client: Optional[MiniMaxClient] = None


def get_minimax_client() -> MiniMaxClient:
    """获取 MiniMax 客户端单例（mock 模式切换时自动重建）"""
    global _minimax_client
    if _minimax_client is None or _minimax_client.mock != settings.MINIMAX_MOCK:
        _minimax_client = MiniMaxClient(
            api_key=settings.MINIMAX_API_KEY,
            api_base=settings.MINIMAX_API_BASE,
            model=settings.MINIMAX_MODEL,
            mock=settings.MINIMAX_MOCK,
        )
    return _minimax_client

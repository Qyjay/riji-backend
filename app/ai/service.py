# app/ai/service.py
import asyncio
import base64
import io
import os
import json
import re
import logging
import time
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import UploadFile
import httpx

from app.config import settings
from app.ai.minimax_client import get_minimax_client
from app.response import ApiException, PARAM_ERROR


logger = logging.getLogger("uvicorn.error")


_IMAGE_UNDERSTAND_CACHE: Dict[str, Dict[str, Any]] = {}


def _vision_enabled() -> bool:
    return bool(
        getattr(
            settings,
            "VIVO_VISION_ENABLED",
            getattr(settings, "ARK_VISION_ENABLED", True),
        )
    )


def _vision_api_key() -> str:
    return str(
        getattr(settings, "VIVO_APP_KEY", "")
        or getattr(settings, "ARK_API_KEY", "")
        or ""
    ).strip()


def _vision_model() -> str:
    return str(
        getattr(settings, "VIVO_VISION_MODEL", "")
        or getattr(settings, "VIVO_MODEL", "")
        or getattr(settings, "ARK_VISION_MODEL", "Doubao-Seed-2.0-mini")
    ).strip()


def _vision_prompt(default_prompt: str = "") -> str:
    return (
        str(default_prompt or "").strip()
        or str(
            getattr(settings, "VIVO_VISION_PROMPT", "")
            or getattr(settings, "ARK_VISION_PROMPT", "")
            or ""
        ).strip()
    )


def _vision_timeout_sec(override_timeout: Optional[int] = None) -> int:
    if override_timeout is not None:
        return max(1, int(override_timeout))
    return max(
        1,
        int(
            getattr(settings, "VIVO_VISION_TIMEOUT_SEC", 0)
            or getattr(settings, "ARK_VISION_TIMEOUT_SEC", 50)
            or 50
        ),
    )


def _vision_cache_ttl_sec() -> int:
    return max(
        int(
            getattr(settings, "VIVO_VISION_CACHE_TTL_SEC", 0)
            or getattr(settings, "ARK_VISION_CACHE_TTL_SEC", 21600)
            or 21600
        ),
        60,
    )


def _vision_max_images(default_value: int) -> int:
    return max(
        1,
        int(
            getattr(settings, "VIVO_VISION_MAX_IMAGES", 0)
            or getattr(settings, "ARK_VISION_MAX_IMAGES", default_value)
            or default_value
        ),
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _cleanup_image_understand_cache(now_ms: int) -> None:
    ttl_ms = _vision_cache_ttl_sec() * 1000
    expired_urls = [
        url
        for url, meta in _IMAGE_UNDERSTAND_CACHE.items()
        if now_ms - int(meta.get("cached_at", 0)) > ttl_ms
    ]
    for url in expired_urls:
        _IMAGE_UNDERSTAND_CACHE.pop(url, None)


def _get_cached_image_hint(url: str) -> tuple[bool, str]:
    now_ms = _now_ms()
    _cleanup_image_understand_cache(now_ms)
    meta = _IMAGE_UNDERSTAND_CACHE.get(url)
    if not meta:
        return False, ""
    return True, str(meta.get("hint") or "").strip()


def _set_cached_image_hint(url: str, hint: str) -> None:
    now_ms = _now_ms()
    _cleanup_image_understand_cache(now_ms)
    _IMAGE_UNDERSTAND_CACHE[url] = {
        "hint": str(hint or "").strip(),
        "cached_at": now_ms,
    }


def clear_image_understand_cache() -> None:
    """清空图片理解缓存。"""
    _IMAGE_UNDERSTAND_CACHE.clear()


async def text_to_speech_service(user_id: str, text: str, voice: str = "") -> str:
    """
    文字转语音，保存文件并返回访问 URL
    """
    client = get_minimax_client()
    voice_id = voice or "female-shaonv"
    audio_bytes = await client.text_to_speech(text, voice_id=voice_id, user_id=user_id)

    # 保存文件
    user_dir = os.path.join(settings.UPLOAD_DIR, user_id, "tts")
    os.makedirs(user_dir, exist_ok=True)
    is_wav = (
        isinstance(audio_bytes, bytes)
        and len(audio_bytes) >= 12
        and audio_bytes[:4] == b"RIFF"
        and audio_bytes[8:12] == b"WAVE"
    )
    ext = "wav" if is_wav else "mp3"
    filename = f"{uuid4()}.{ext}"
    file_path = os.path.join(user_dir, filename)

    if isinstance(audio_bytes, bytes) and audio_bytes:
        with open(file_path, "wb") as f:
            f.write(audio_bytes)
        url = f"/uploads/{user_id}/tts/{filename}"
    else:
        # Mock 模式可能返回空或假数据，返回默认音频 URL
        url = "/uploads/mock_audio.mp3"
    return url


def _looks_like_mp3(audio_bytes: bytes) -> bool:
    if audio_bytes.startswith(b"ID3"):
        return True
    if len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0:
        return True
    return False


def _resolve_asr_audio_format(file: UploadFile, audio_bytes: bytes) -> str:
    filename = str(file.filename or "").lower().strip()
    content_type = str(file.content_type or "").lower().strip()

    if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return "wav"
    if _looks_like_mp3(audio_bytes):
        return "mp3"
    if audio_bytes.startswith(b"OggS"):
        return "ogg"
    if audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp":
        return "m4a"

    if filename.endswith(".wav") or content_type in {"audio/wav", "audio/x-wav"}:
        return "wav"
    if filename.endswith(".pcm") or content_type in {
        "audio/pcm",
        "audio/l16",
    }:
        return "pcm"

    if filename.endswith(".mp3") or content_type in {"audio/mpeg", "audio/mp3"}:
        return "mp3"
    if filename.endswith(".m4a") or content_type in {"audio/mp4", "audio/x-m4a"}:
        return "m4a"
    if filename.endswith(".ogg") or content_type in {"audio/ogg", "application/ogg"}:
        return "ogg"
    if filename.endswith(".webm") or content_type in {"audio/webm", "video/webm"}:
        return "webm"

    return "unknown"


def _convert_audio_to_wav_16k_mono(audio_bytes: bytes, source_format: str) -> bytes:
    conda_bin = Path(sys.prefix) / "Library" / "bin"
    if conda_bin.exists():
        current_path = os.environ.get("PATH", "")
        conda_bin_text = str(conda_bin)
        if conda_bin_text.lower() not in current_path.lower():
            os.environ["PATH"] = f"{conda_bin_text}{os.pathsep}{current_path}"

    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise ApiException(
            code=PARAM_ERROR,
            message=(
                "当前服务未安装音频转码依赖，无法自动将压缩音频转换为 wav；"
                "请前端先转为 16kHz/16bit/单声道 wav 或 pcm。"
            ),
            status_code=400,
        ) from exc

    ffmpeg_exe = os.getenv("IMAGEIO_FFMPEG_EXE", "").strip()
    conda_ffmpeg = conda_bin / "ffmpeg.exe"
    if conda_ffmpeg.exists():
        ffmpeg_exe = str(conda_ffmpeg)
    if not ffmpeg_exe:
        try:
            import imageio_ffmpeg

            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_exe = ""
    if ffmpeg_exe:
        AudioSegment.converter = ffmpeg_exe

    format_hint = "mp4" if source_format == "m4a" else source_format
    temp_path = ""
    try:
        suffix = f".{source_format}" if source_format in {"mp3", "m4a", "ogg", "webm"} else ""
        if suffix:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = temp_file.name
            segment = AudioSegment.from_file(temp_path, format=format_hint)
        else:
            segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format=format_hint)
        normalized = segment.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        output = io.BytesIO()
        normalized.export(output, format="wav")
        converted = output.getvalue()
    except (FileNotFoundError, OSError) as exc:
        raise ApiException(
            code=PARAM_ERROR,
            message="后端缺少 ffmpeg，无法自动转换音频；请前端先转为 wav/pcm 后再上传。",
            status_code=400,
        ) from exc
    except Exception as exc:
        raise ApiException(
            code=PARAM_ERROR,
            message="音频自动转换失败，请上传标准 wav/pcm，或使用可识别的 mp3/m4a/ogg 文件。",
            status_code=400,
        ) from exc
    finally:
        if temp_path:
            with suppress(Exception):
                os.remove(temp_path)

    if not converted:
        raise ApiException(
            code=PARAM_ERROR,
            message="音频自动转换失败：未生成有效 wav 数据。",
            status_code=400,
        )

    return converted


async def speech_to_text_short_service(
    user_id: str,
    file: UploadFile,
    punctuation: int = 1,
    chinese2digital: int = 1,
    end_vad_time: int = 2000,
) -> dict:
    """短语音识别服务：支持 wav/pcm，压缩音频会尝试自动转为 16kHz/16bit/单声道 wav。"""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise ApiException(
            code=PARAM_ERROR,
            message="音频文件不能为空",
            status_code=400,
        )

    audio_format = _resolve_asr_audio_format(file, audio_bytes)
    if audio_format in {"mp3", "m4a", "ogg", "webm"}:
        audio_bytes = _convert_audio_to_wav_16k_mono(audio_bytes, source_format=audio_format)
        audio_format = "wav"
    elif audio_format == "unknown":
        raise ApiException(
            code=PARAM_ERROR,
            message="ASR 仅支持 wav/pcm，或可自动转换的 mp3/m4a/ogg/webm 音频。",
            status_code=400,
        )

    client = get_minimax_client()
    return await client.speech_to_text_short(
        audio_bytes=audio_bytes,
        audio_format=audio_format,
        user_id=user_id,
        punctuation=punctuation,
        chinese2digital=chinese2digital,
        end_vad_time=end_vad_time,
    )


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


def _extract_text_from_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("content")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        if chunks:
            return "\n".join(chunks).strip()

    return ""


def _extract_ark_text(response: Any) -> str:
    """从 VIVO chat/completions 返回中提取文本，同时兼容历史 Ark 输出格式。"""
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    if hasattr(response, "model_dump"):
        data = response.model_dump()
    else:
        data = response

    if isinstance(data, dict):
        choices = data.get("choices", [])
        if isinstance(choices, list):
            for item in choices:
                if not isinstance(item, dict):
                    continue
                message = item.get("message") or {}
                if isinstance(message, dict):
                    text = _extract_text_from_message_content(message.get("content"))
                    if text:
                        return text

        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        output = data.get("output", [])
        if isinstance(output, list):
            chunks = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content_blocks = item.get("content", [])
                if not isinstance(content_blocks, list):
                    continue
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    text = block.get("text") or block.get("output_text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
            if chunks:
                return "\n".join(chunks).strip()

    return ""


def _build_vivo_vision_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }


def _build_vivo_vision_endpoint() -> str:
    base_url = str(getattr(settings, "VIVO_API_BASE", "https://api-ai.vivo.com.cn") or "https://api-ai.vivo.com.cn")
    return f"{base_url.rstrip('/')}/v1/chat/completions"


def _build_vivo_vision_messages(image_urls: List[str], prompt: str) -> list[dict]:
    content_blocks: list[dict] = [
        {
            "type": "image_url",
            "image_url": {
                "url": image_url,
            },
        }
        for image_url in image_urls
    ]
    content_blocks.append(
        {
            "type": "text",
            "text": prompt,
        }
    )
    return [
        {
            "role": "user",
            "content": content_blocks,
        }
    ]


async def _call_ark_vision_async(image_url: str, prompt: str):
    """异步调用 VIVO 视觉理解（chat/completions）。"""
    api_key = _vision_api_key()
    if not api_key:
        raise ApiException(
            code=PARAM_ERROR,
            message="VIVO_APP_KEY 未配置，无法调用图片理解接口",
            status_code=500,
        )

    request_id = str(uuid4())
    payload = {
        "model": _vision_model(),
        "messages": _build_vivo_vision_messages([image_url], prompt),
        "temperature": 0.3,
        "max_tokens": 2048,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=float(_vision_timeout_sec()), trust_env=False) as client:
        response = await client.post(
            _build_vivo_vision_endpoint(),
            headers=_build_vivo_vision_headers(api_key),
            params={"requestId": request_id, "request_id": request_id},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


async def _call_ark_vision_multi_async(image_urls: List[str], prompt: str):
    """异步调用 VIVO 视觉理解（单次请求输入多图）。"""
    api_key = _vision_api_key()
    if not api_key:
        raise ApiException(
            code=PARAM_ERROR,
            message="VIVO_APP_KEY 未配置，无法调用图片理解接口",
            status_code=500,
        )

    request_id = str(uuid4())
    payload = {
        "model": _vision_model(),
        "messages": _build_vivo_vision_messages(image_urls, prompt),
        "temperature": 0.3,
        "max_tokens": 4096,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=float(_vision_timeout_sec()), trust_env=False) as client:
        response = await client.post(
            _build_vivo_vision_endpoint(),
            headers=_build_vivo_vision_headers(api_key),
            params={"requestId": request_id, "request_id": request_id},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def _to_image_data_url(path: Path) -> str:
    """将本地图片文件转换为 data URL，便于 VIVO 接口直接消费。"""
    resolved = path.resolve()
    ext = resolved.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    mime_type = mime_map.get(ext, "application/octet-stream")
    raw_bytes = resolved.read_bytes()
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _resolve_ark_image_input(image_url: str) -> str:
    """将图片输入转换为 VIVO 可接受的 URL（远端 URL 或 data URL）。"""
    raw = (image_url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https", "data"}:
        return raw

    upload_root = Path(settings.UPLOAD_DIR).resolve()
    normalized = raw.replace("\\", "/")

    relative_path = ""
    if normalized.startswith("/uploads/"):
        relative_path = normalized[len("/uploads/"):]
    elif normalized.startswith("uploads/"):
        relative_path = normalized[len("uploads/"):]

    if relative_path:
        candidate = (upload_root / Path(relative_path)).resolve()
        try:
            candidate.relative_to(upload_root)
        except ValueError:
            logger.warning("[vivo/vision] skip unsafe upload path image_url=%s", raw)
            return ""

        if candidate.exists():
            try:
                return _to_image_data_url(candidate)
            except Exception as exc:
                logger.warning("[vivo/vision] read local upload image failed path=%s error=%s", candidate, str(exc))
                return ""

        logger.warning("[vivo/vision] upload file not found image_url=%s path=%s", raw, candidate)
        return ""

    as_path = Path(raw)
    if as_path.is_absolute():
        if as_path.exists():
            try:
                return _to_image_data_url(as_path)
            except Exception as exc:
                logger.warning("[vivo/vision] read local image failed path=%s error=%s", as_path, str(exc))
                return ""
        logger.warning("[vivo/vision] local file not found image_url=%s path=%s", raw, as_path)
        return ""

    return raw


def _build_ark_batch_prompt(prompt: str, image_count: int) -> str:
    """构造多图输入提示词，约束模型返回可解析 JSON。"""
    base_prompt = _vision_prompt(prompt)
    return (
        f"{base_prompt}\n\n"
        "你将收到多张图片。请严格按图片输入顺序输出 JSON 数组。"
        "数组长度必须与图片数量一致。"
        "每个元素是对应图片的客观描述字符串。"
        "不要输出 Markdown 代码块，不要输出额外解释。"
        f"图片数量：{image_count}。"
    )


def _parse_ark_batch_descriptions(raw_text: str, expected_count: int) -> Optional[List[str]]:
    """解析多图识别返回内容，提取按顺序描述列表。"""
    payload = str(raw_text or "").strip()
    if not payload or expected_count <= 0:
        return None

    parsed: Any = None
    try:
        parsed = json.loads(payload)
    except Exception:
        match = re.search(r"\[[\s\S]*\]", payload)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return None

    if not isinstance(parsed, list):
        return None

    descriptions: List[str] = []
    for item in parsed:
        description = ""
        if isinstance(item, str):
            description = item
        elif isinstance(item, dict):
            for key in ("description", "text", "result", "caption", "content"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    description = value
                    break

        descriptions.append(str(description or "").strip())

    if len(descriptions) < expected_count:
        descriptions.extend([""] * (expected_count - len(descriptions)))
    return descriptions[:expected_count]


async def understand_image_text(
    image_url: str,
    prompt: str = "",
    timeout_sec: Optional[int] = None,
) -> str:
    """调用 VIVO 图片理解，返回识别文本；失败返回空字符串。"""
    image_url = (image_url or "").strip()
    if not image_url:
        return ""

    if not _vision_enabled():
        return ""

    if not _vision_api_key():
        logger.warning("[vivo/vision] VIVO_APP_KEY is empty")
        return ""

    resolved_prompt = _vision_prompt(prompt)
    resolved_image_input = _resolve_ark_image_input(image_url)
    if not resolved_image_input:
        return ""
    req_timeout = float(_vision_timeout_sec(timeout_sec))

    logger.info(
        "[vivo/vision] request model=%s timeout=%s image_url=%s image_input=%s",
        _vision_model(),
        req_timeout,
        image_url,
        resolved_image_input,
    )

    try:
        response = await asyncio.wait_for(
            _call_ark_vision_async(resolved_image_input, resolved_prompt),
            timeout=req_timeout,
        )
        description = _extract_ark_text(response)
        if not description:
            logger.warning("[vivo/vision] empty response for image_url=%s", image_url)
        return description
    except asyncio.TimeoutError:
        logger.warning("[vivo/vision] timeout for image_url=%s timeout=%s", image_url, req_timeout)
        return ""
    except ApiException:
        raise
    except Exception as exc:
        logger.exception("[vivo/vision] request failed: %s", str(exc))
        return ""


async def understand_images_batch(
    image_urls: List[str],
    prompt: str = "",
    timeout_sec: Optional[int] = None,
    max_images: Optional[int] = None,
    include_image_url: bool = False,
) -> List[Any]:
    """批量图片理解。

    默认返回按输入顺序排列的描述字符串数组。
    若 include_image_url=True，返回 [{"image_url": ..., "description": ...}, ...]。
    """
    normalized_urls: List[str] = []
    for image_url in image_urls or []:
        cleaned = str(image_url or "").strip()
        if cleaned:
            normalized_urls.append(cleaned)

    if not normalized_urls:
        return []

    resolved_prompt = _vision_prompt(prompt)
    resolved_timeout = _vision_timeout_sec(timeout_sec)

    if max_images is None:
        max_images = _vision_max_images(len(normalized_urls))
    max_images = max(int(max_images), 0)

    results: List[dict] = [
        {
            "image_url": image_url,
            "description": "",
        }
        for image_url in normalized_urls
    ]

    to_infer_indices: List[int] = []
    to_infer_urls: List[str] = []
    to_infer_inputs: List[str] = []
    model_call_count = 0

    for idx, image_url in enumerate(normalized_urls):
        hit, cached_hint = _get_cached_image_hint(image_url)
        if hit:
            results[idx]["description"] = cached_hint
            continue

        if model_call_count >= max_images:
            continue

        resolved_input = _resolve_ark_image_input(image_url)
        model_call_count += 1
        if not resolved_input:
            _set_cached_image_hint(image_url, "")
            continue

        to_infer_indices.append(idx)
        to_infer_urls.append(image_url)
        to_infer_inputs.append(resolved_input)

    descriptions: List[str] = []
    if to_infer_inputs:
        if len(to_infer_inputs) == 1:
            try:
                descriptions = [
                    await understand_image_text(
                        image_url=to_infer_urls[0],
                        prompt=resolved_prompt,
                        timeout_sec=resolved_timeout,
                    )
                ]
            except Exception:
                descriptions = [""]
        else:
            can_use_multi = bool(_vision_enabled() and _vision_api_key())
            parsed_multi: Optional[List[str]] = None
            if can_use_multi:
                batch_prompt = _build_ark_batch_prompt(resolved_prompt, len(to_infer_inputs))
                try:
                    response = await asyncio.wait_for(
                        _call_ark_vision_multi_async(to_infer_inputs, batch_prompt),
                        timeout=float(resolved_timeout),
                    )
                    parsed_multi = _parse_ark_batch_descriptions(
                        _extract_ark_text(response),
                        len(to_infer_inputs),
                    )
                except Exception:
                    parsed_multi = None

            if parsed_multi is not None:
                descriptions = parsed_multi
            else:
                descriptions = []
                for image_url in to_infer_urls:
                    try:
                        desc = await understand_image_text(
                            image_url=image_url,
                            prompt=resolved_prompt,
                            timeout_sec=resolved_timeout,
                        )
                    except Exception:
                        desc = ""
                    descriptions.append(desc)

    for offset, idx in enumerate(to_infer_indices):
        description = ""
        if offset < len(descriptions):
            description = str(descriptions[offset] or "").strip()
        results[idx]["description"] = description
        _set_cached_image_hint(normalized_urls[idx], description)

    if include_image_url:
        return results

    return [str(item.get("description") or "").strip() for item in results]

# app/ai/service.py
import asyncio
import os
import json
import re
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4
from app.config import settings
from app.ai.minimax_client import get_minimax_client
from app.response import ApiException, PARAM_ERROR


logger = logging.getLogger("uvicorn.error")


_IMAGE_UNDERSTAND_CACHE: Dict[str, Dict[str, Any]] = {}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _cleanup_image_understand_cache(now_ms: int) -> None:
    ttl_ms = max(int(settings.ARK_VISION_CACHE_TTL_SEC), 60) * 1000
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


def _extract_ark_text(response: Any) -> str:
    """从 Ark responses.create 结果中尽量提取文本。"""
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    if hasattr(response, "model_dump"):
        data = response.model_dump()
    else:
        data = response

    if isinstance(data, dict):
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


async def _call_ark_vision_async(image_url: str, prompt: str):
    """异步调用 Ark 视觉模型。"""
    try:
        from volcenginesdkarkruntime import AsyncArk
    except ImportError as exc:
        raise ApiException(
            code=PARAM_ERROR,
            message="未安装 volcengine-python-sdk[ark]，请先安装后再调用视觉理解接口",
            status_code=500,
        ) from exc

    client = AsyncArk(
        base_url=settings.ARK_BASE_URL,
        api_key=settings.ARK_API_KEY,
    )

    try:
        return await client.responses.create(
            model=settings.ARK_VISION_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": image_url,
                        },
                        {
                            "type": "input_text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )
    finally:
        close_fn = getattr(client, "close", None)
        if callable(close_fn):
            maybe_awaitable = close_fn()
            if asyncio.iscoroutine(maybe_awaitable):
                await maybe_awaitable


def _to_ark_file_uri(path: Path) -> str:
    """生成 Ark SDK 在 Windows 下可正确解析的 file URI。"""
    resolved = path.resolve()
    posix_path = resolved.as_posix()

    # Ark SDK 现版本在 Windows 下对 file:///C:/... 的解析有问题，
    # 这里使用 file://C:/... 以确保其内部拼接后得到有效本地路径。
    if len(posix_path) >= 3 and posix_path[1] == ":" and posix_path[2] == "/":
        return f"file://{posix_path}"

    return resolved.as_uri()


def _resolve_ark_image_input(image_url: str) -> str:
    """将图片输入转换为 Ark 可接受的 URL。"""
    raw = (image_url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https", "file", "data"}:
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
            logger.warning("[ark/vision] skip unsafe upload path image_url=%s", raw)
            return ""

        if candidate.exists():
            return _to_ark_file_uri(candidate)

        logger.warning("[ark/vision] upload file not found image_url=%s path=%s", raw, candidate)
        return ""

    as_path = Path(raw)
    if as_path.is_absolute():
        if as_path.exists():
            return _to_ark_file_uri(as_path)
        logger.warning("[ark/vision] local file not found image_url=%s path=%s", raw, as_path)
        return ""

    return raw


async def understand_image_text(
    image_url: str,
    prompt: str = "",
    timeout_sec: Optional[int] = None,
) -> str:
    """调用 Ark 视觉模型，返回识别文本；失败返回空字符串。"""
    image_url = (image_url or "").strip()
    if not image_url:
        return ""

    if not settings.ARK_VISION_ENABLED:
        return ""

    if not settings.ARK_API_KEY:
        logger.warning("[ark/vision] ARK_API_KEY is empty")
        return ""

    resolved_prompt = (prompt or "").strip() or settings.ARK_VISION_PROMPT
    resolved_image_input = _resolve_ark_image_input(image_url)
    if not resolved_image_input:
        return ""
    req_timeout = float(timeout_sec or settings.ARK_VISION_TIMEOUT_SEC)

    logger.info(
        "[ark/vision] request model=%s timeout=%s image_url=%s image_input=%s",
        settings.ARK_VISION_MODEL,
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
            logger.warning("[ark/vision] empty response for image_url=%s", image_url)
        return description
    except asyncio.TimeoutError:
        logger.warning("[ark/vision] timeout for image_url=%s timeout=%s", image_url, req_timeout)
        return ""
    except ApiException:
        raise
    except Exception as exc:
        logger.exception("[ark/vision] request failed: %s", str(exc))
        return ""


async def understand_images_batch(
    image_urls: List[str],
    prompt: str = "",
    timeout_sec: Optional[int] = None,
    max_images: Optional[int] = None,
) -> List[dict]:
    """批量图片理解，按输入顺序返回每张图结果。"""
    normalized_urls: List[str] = []
    for image_url in image_urls or []:
        cleaned = str(image_url or "").strip()
        if cleaned:
            normalized_urls.append(cleaned)

    if not normalized_urls:
        return []

    resolved_prompt = (prompt or "").strip() or settings.ARK_VISION_PROMPT
    resolved_timeout = int(timeout_sec or settings.ARK_VISION_TIMEOUT_SEC)

    if max_images is None:
        max_images = len(normalized_urls)
    max_images = max(int(max_images), 0)

    results: List[dict] = []
    model_call_count = 0

    for image_url in normalized_urls:
        hit, cached_hint = _get_cached_image_hint(image_url)
        if hit:
            description = cached_hint
        elif model_call_count < max_images:
            try:
                description = await understand_image_text(
                    image_url=image_url,
                    prompt=resolved_prompt,
                    timeout_sec=resolved_timeout,
                )
            except Exception:
                description = ""
            _set_cached_image_hint(image_url, description)
            model_call_count += 1
        else:
            description = ""

        results.append(
            {
                "image_url": image_url,
                "description": str(description or "").strip(),
            }
        )

    return results
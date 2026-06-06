"""用户聊天模型配置与调用解析。"""
import asyncio
import base64
import hashlib
import json
import time
from typing import AsyncGenerator, Optional
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import UserLlmModel, UserSettings
from app.response import AI_SERVICE_ERROR, NOT_FOUND, PARAM_ERROR, ApiException


BUILTIN_VIVO_ID = "builtin:vivo"
BUILTIN_MINIMAX_ID = "builtin:minimax"
BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID = "builtin:ark:deepseekv4-flash"
BUILTIN_ARK_DEEPSEEK_V4_PRO_ID = "builtin:ark:deepseekv4-pro"
PROVIDER_OPENAI = "openai_compatible"
PROVIDER_ANTHROPIC = "anthropic_compatible"
SUPPORTED_PROVIDERS = {PROVIDER_OPENAI, PROVIDER_ANTHROPIC}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _fernet() -> Fernet:
    digest = hashlib.sha256(str(settings.JWT_SECRET or "dev-secret").encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(api_key: str) -> str:
    raw = str(api_key or "").strip()
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_api_key(ciphertext: str) -> str:
    raw = str(ciphertext or "").strip()
    if not raw:
        return ""
    try:
        return _fernet().decrypt(raw.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ApiException(code=AI_SERVICE_ERROR, message="模型 API Key 解密失败", status_code=500) from exc


def _normalize_provider(provider_type: str) -> str:
    value = str(provider_type or "").strip().lower()
    if value not in SUPPORTED_PROVIDERS:
        raise ApiException(code=PARAM_ERROR, message="providerType 仅支持 openai_compatible 或 anthropic_compatible", status_code=400)
    return value


def _validate_required(data: dict, fields: list[str]) -> None:
    missing = [field for field in fields if not str(data.get(field) or "").strip()]
    if missing:
        raise ApiException(code=PARAM_ERROR, message=f"缺少必填字段: {', '.join(missing)}", status_code=400)


def builtin_models() -> list[dict]:
    return [
        {
            "id": BUILTIN_VIVO_ID,
            "name": "VIVO Doubao",
            "provider_type": "builtin_vivo",
            "base_url": settings.VIVO_API_BASE,
            "model": settings.VIVO_MODEL,
            "is_builtin": True,
            "is_enabled": True,
            "has_api_key": bool(settings.VIVO_APP_KEY),
        },
        {
            "id": BUILTIN_MINIMAX_ID,
            "name": "MiniMax",
            "provider_type": "builtin_minimax",
            "base_url": settings.MINIMAX_API_BASE,
            "model": settings.MINIMAX_MODEL,
            "is_builtin": True,
            "is_enabled": True,
            "has_api_key": bool(settings.MINIMAX_API_KEY),
        },
        {
            "id": BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID,
            "name": "DeepSeek V4 Flash",
            "provider_type": "builtin_ark",
            "base_url": settings.ARK_BASE_URL,
            "model": settings.ARK_DEEPSEEK_V4_FLASH_MODEL,
            "is_builtin": True,
            "is_enabled": True,
            "has_api_key": bool(settings.ARK_API_KEY),
        },
        {
            "id": BUILTIN_ARK_DEEPSEEK_V4_PRO_ID,
            "name": "DeepSeek V4 Pro",
            "provider_type": "builtin_ark",
            "base_url": settings.ARK_BASE_URL,
            "model": settings.ARK_DEEPSEEK_V4_PRO_MODEL,
            "is_builtin": True,
            "is_enabled": True,
            "has_api_key": bool(settings.ARK_API_KEY),
        },
    ]


def fallback_builtin_model_id() -> str:
    provider = str(settings.LLM_PROVIDER or "").strip().lower()
    if provider == "vivo":
        return BUILTIN_VIVO_ID
    if provider == "ark":
        return BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID
    return BUILTIN_MINIMAX_ID


def list_models(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(UserLlmModel)
        .filter(UserLlmModel.user_id == user_id, UserLlmModel.is_enabled.is_(True))
        .order_by(UserLlmModel.created_at.desc())
        .all()
    )
    custom = [
        {
            "id": row.id,
            "name": row.name,
            "provider_type": row.provider_type,
            "base_url": row.base_url,
            "model": row.model,
            "is_builtin": False,
            "is_enabled": bool(row.is_enabled),
            "has_api_key": bool(row.api_key_ciphertext),
        }
        for row in rows
    ]
    return builtin_models() + custom


def get_default_chat_model_id(db: Session, user_id: str) -> str:
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    value = str(getattr(user_settings, "chat_model_id", "") or "").strip() if user_settings else ""
    return value or fallback_builtin_model_id()


def _ensure_user_model(db: Session, user_id: str, model_id: str) -> UserLlmModel:
    row = (
        db.query(UserLlmModel)
        .filter(UserLlmModel.id == model_id, UserLlmModel.user_id == user_id, UserLlmModel.is_enabled.is_(True))
        .first()
    )
    if not row:
        raise ApiException(code=NOT_FOUND, message="模型配置不存在", status_code=404)
    return row


def create_model(db: Session, user_id: str, data: dict) -> dict:
    _validate_required(data, ["name", "provider_type", "base_url", "model", "api_key"])
    provider_type = _normalize_provider(data["provider_type"])
    now = _now_ms()
    row = UserLlmModel(
        id=str(uuid4()),
        user_id=user_id,
        name=str(data["name"]).strip(),
        provider_type=provider_type,
        base_url=str(data["base_url"]).strip().rstrip("/"),
        model=str(data["model"]).strip(),
        api_key_ciphertext=encrypt_api_key(str(data["api_key"]).strip()),
        is_enabled=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_model(row)


def update_model(db: Session, user_id: str, model_id: str, data: dict) -> dict:
    row = _ensure_user_model(db, user_id, model_id)
    if data.get("name") is not None:
        row.name = str(data["name"]).strip()
    if data.get("provider_type") is not None:
        row.provider_type = _normalize_provider(data["provider_type"])
    if data.get("base_url") is not None:
        row.base_url = str(data["base_url"]).strip().rstrip("/")
    if data.get("model") is not None:
        row.model = str(data["model"]).strip()
    if data.get("api_key") is not None and str(data["api_key"]).strip():
        row.api_key_ciphertext = encrypt_api_key(str(data["api_key"]).strip())

    _validate_required(
        {
            "name": row.name,
            "provider_type": row.provider_type,
            "base_url": row.base_url,
            "model": row.model,
            "api_key": row.api_key_ciphertext,
        },
        ["name", "provider_type", "base_url", "model", "api_key"],
    )
    row.updated_at = _now_ms()
    db.commit()
    db.refresh(row)
    return serialize_model(row)


def delete_model(db: Session, user_id: str, model_id: str) -> None:
    row = _ensure_user_model(db, user_id, model_id)
    row.is_enabled = False
    row.updated_at = _now_ms()
    settings_row = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings_row and settings_row.chat_model_id == model_id:
        settings_row.chat_model_id = ""
    db.commit()


def serialize_model(row: UserLlmModel) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "provider_type": row.provider_type,
        "base_url": row.base_url,
        "model": row.model,
        "is_builtin": False,
        "is_enabled": bool(row.is_enabled),
        "has_api_key": bool(row.api_key_ciphertext),
    }


def _openai_endpoint(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _anthropic_endpoint(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if base.endswith("/messages"):
        return base
    return f"{base}/messages"


def _split_system_message(messages: list, system_prompt: str) -> tuple[str, list]:
    system_parts = [system_prompt] if system_prompt else []
    next_messages = []
    for item in messages or []:
        role = (item or {}).get("role")
        content = (item or {}).get("content")
        if role == "system":
            system_parts.append(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
        else:
            next_messages.append(item)
    return "\n\n".join([part for part in system_parts if part]), next_messages


class CustomChatModelClient:
    def __init__(
        self,
        *,
        provider_type: str,
        base_url: str,
        model: str,
        api_key: str,
        timeout_sec: float = 90.0,
    ):
        self.provider_type = provider_type
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_sec = float(timeout_sec or 90.0)

    async def chat_completion(
        self,
        messages: list,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ) -> str:
        if self.provider_type == PROVIDER_ANTHROPIC:
            return await self._anthropic_completion(messages, system_prompt, temperature, max_tokens)
        return await self._openai_completion(messages, system_prompt, temperature, max_tokens)

    async def stream_chat(
        self,
        messages: list,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        if self.provider_type == PROVIDER_ANTHROPIC:
            async for chunk in self._anthropic_stream(messages, system_prompt, temperature, max_tokens):
                yield chunk
            return
        async for chunk in self._openai_stream(messages, system_prompt, temperature, max_tokens):
            yield chunk

    async def _openai_completion(self, messages: list, system_prompt: str, temperature: float, max_tokens: int) -> str:
        full_messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + (messages or [])
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        data = await self._post_json(_openai_endpoint(self.base_url), payload, {})
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not text:
            raise ApiException(code=AI_SERVICE_ERROR, message="OpenAI-compatible 返回内容为空", status_code=502)
        return text

    async def _anthropic_completion(self, messages: list, system_prompt: str, temperature: float, max_tokens: int) -> str:
        system, anthropic_messages = _split_system_message(messages, system_prompt)
        payload = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if system:
            payload["system"] = system
        data = await self._post_json(_anthropic_endpoint(self.base_url), payload, {"anthropic-version": "2023-06-01"})
        parts = data.get("content") or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        if not text:
            raise ApiException(code=AI_SERVICE_ERROR, message="Anthropic-compatible 返回内容为空", status_code=502)
        return text

    async def _openai_stream(self, messages: list, system_prompt: str, temperature: float, max_tokens: int):
        full_messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + (messages or [])
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async for event in self._stream_events(_openai_endpoint(self.base_url), payload, {}):
            if event == "[DONE]":
                return
            try:
                data = json.loads(event)
            except Exception:
                continue
            delta = ((data.get("choices") or [{}])[0].get("delta") or {}).get("content")
            if delta:
                yield str(delta)

    async def _anthropic_stream(self, messages: list, system_prompt: str, temperature: float, max_tokens: int):
        system, anthropic_messages = _split_system_message(messages, system_prompt)
        payload = {
            "model": self.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system
        async for event in self._stream_events(_anthropic_endpoint(self.base_url), payload, {"anthropic-version": "2023-06-01"}):
            try:
                data = json.loads(event)
            except Exception:
                continue
            if data.get("type") == "content_block_delta":
                text = ((data.get("delta") or {}).get("text") or "")
                if text:
                    yield str(text)

    async def _post_json(self, url: str, payload: dict, extra_headers: dict) -> dict:
        if not self.api_key:
            raise ApiException(code=AI_SERVICE_ERROR, message="模型 API Key 未配置", status_code=500)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **extra_headers,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec, trust_env=False) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise ValueError("响应不是 JSON 对象")
                return data
        except httpx.HTTPStatusError as exc:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"自定义模型请求失败: {exc.response.status_code} {exc.response.text[:200]}",
                status_code=502,
            )
        except ApiException:
            raise
        except Exception as exc:
            raise ApiException(code=AI_SERVICE_ERROR, message=f"自定义模型服务异常: {str(exc)}", status_code=502)

    async def _stream_events(self, url: str, payload: dict, extra_headers: dict):
        if not self.api_key:
            raise ApiException(code=AI_SERVICE_ERROR, message="模型 API Key 未配置", status_code=500)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **extra_headers,
        }
        try:
            async with httpx.AsyncClient(timeout=max(self.timeout_sec, 120.0), trust_env=False) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        yield line[5:].strip()
        except httpx.HTTPStatusError as exc:
            raise ApiException(
                code=AI_SERVICE_ERROR,
                message=f"自定义模型流式请求失败: {exc.response.status_code} {exc.response.text[:200]}",
                status_code=502,
            )
        except ApiException:
            raise
        except Exception as exc:
            raise ApiException(code=AI_SERVICE_ERROR, message=f"自定义模型流式服务异常: {str(exc)}", status_code=502)


def _builtin_client(model_id: str):
    from app.ai.minimax_client import MiniMaxClient, get_minimax_client

    if not model_id:
        return get_minimax_client()
    if model_id == BUILTIN_ARK_DEEPSEEK_V4_FLASH_ID:
        return CustomChatModelClient(
            provider_type=PROVIDER_OPENAI,
            base_url=settings.ARK_BASE_URL,
            model=settings.ARK_DEEPSEEK_V4_FLASH_MODEL,
            api_key=settings.ARK_API_KEY,
            timeout_sec=settings.ARK_TIMEOUT_SEC,
        )
    if model_id == BUILTIN_ARK_DEEPSEEK_V4_PRO_ID:
        return CustomChatModelClient(
            provider_type=PROVIDER_OPENAI,
            base_url=settings.ARK_BASE_URL,
            model=settings.ARK_DEEPSEEK_V4_PRO_MODEL,
            api_key=settings.ARK_API_KEY,
            timeout_sec=settings.ARK_TIMEOUT_SEC,
        )
    if model_id == BUILTIN_VIVO_ID:
        return MiniMaxClient(
            api_key=settings.MINIMAX_API_KEY,
            api_base=settings.MINIMAX_API_BASE,
            model=settings.MINIMAX_MODEL,
            mock=settings.MINIMAX_MOCK,
            provider="vivo",
            vivo_app_id=settings.VIVO_APP_ID,
            vivo_app_key=settings.VIVO_APP_KEY,
            vivo_api_base=settings.VIVO_API_BASE,
            vivo_model=settings.VIVO_MODEL,
            vivo_reasoning_effort=settings.VIVO_REASONING_EFFORT,
            vivo_enable_thinking=settings.VIVO_ENABLE_THINKING,
            vivo_timeout_sec=settings.VIVO_TIMEOUT_SEC,
            vivo_image_model=settings.VIVO_IMAGE_MODEL,
            vivo_image_timeout_sec=settings.VIVO_IMAGE_TIMEOUT_SEC,
            vivo_tts_engine_id=settings.VIVO_TTS_ENGINE_ID,
            vivo_tts_timeout_sec=settings.VIVO_TTS_TIMEOUT_SEC,
            vivo_asr_engine_id=settings.VIVO_ASR_ENGINE_ID,
            vivo_asr_timeout_sec=settings.VIVO_ASR_TIMEOUT_SEC,
            vivo_asr_end_vad_time=settings.VIVO_ASR_END_VAD_TIME,
            vivo_asr_punctuation=settings.VIVO_ASR_PUNCTUATION,
            vivo_asr_chinese2digital=settings.VIVO_ASR_CHINESE2DIGITAL,
            vivo_asr_net_type=settings.VIVO_ASR_NET_TYPE,
        )
    if model_id == BUILTIN_MINIMAX_ID:
        return MiniMaxClient(
            api_key=settings.MINIMAX_API_KEY,
            api_base=settings.MINIMAX_API_BASE,
            model=settings.MINIMAX_MODEL,
            mock=settings.MINIMAX_MOCK,
            provider="minimax",
        )
    return None


def resolve_chat_client(db: Session, user_id: str, model_id: Optional[str]):
    resolved_model_id = str(model_id or "").strip() or get_default_chat_model_id(db, user_id)
    builtin = _builtin_client(resolved_model_id)
    if builtin is not None:
        return builtin, resolved_model_id

    row = _ensure_user_model(db, user_id, resolved_model_id)
    return CustomChatModelClient(
        provider_type=row.provider_type,
        base_url=row.base_url,
        model=row.model,
        api_key=decrypt_api_key(row.api_key_ciphertext),
    ), resolved_model_id

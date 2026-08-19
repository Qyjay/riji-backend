"""短期、一次性的实时语音 WebSocket Ticket。"""
from __future__ import annotations

import re
import time
from threading import Lock
from uuid import uuid4

from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings


_AUDIENCE = "realtime_voice"
_VOICE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class VoiceTicketError(ValueError):
    pass


class VoiceTicketStore:
    """单进程 Ticket 重放保护。多 worker 部署前需替换为 Redis。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._consumed: dict[str, int] = {}

    def _cleanup(self, now: int) -> None:
        expired = [jti for jti, exp in self._consumed.items() if exp <= now]
        for jti in expired:
            self._consumed.pop(jti, None)

    def consume(self, jti: str, exp: int) -> None:
        now = int(time.time())
        with self._lock:
            self._cleanup(now)
            if jti in self._consumed:
                raise VoiceTicketError("ticket 已使用")
            self._consumed[jti] = exp

    def reset(self) -> None:
        with self._lock:
            self._consumed.clear()


ticket_store = VoiceTicketStore()


def normalize_voice(raw_voice: str) -> str:
    voice = str(raw_voice or "").strip() or settings.VOLC_REALTIME_VOICE_DEFAULT_VOICE
    if not _VOICE_RE.fullmatch(voice):
        raise VoiceTicketError("音色标识不合法")
    return voice


def issue_ticket(
    *,
    user_id: str,
    client_platform: str,
    voice: str,
    output_format: str,
) -> tuple[str, int]:
    now = int(time.time())
    ttl = max(10, int(settings.REALTIME_VOICE_TICKET_TTL_SEC))
    exp = now + ttl
    payload = {
        "sub": user_id,
        "aud": _AUDIENCE,
        "jti": str(uuid4()),
        "iat": now,
        "exp": exp,
        "platform": client_platform,
        "voice": normalize_voice(voice),
        "input_format": "pcm_16k_s16le",
        "output_format": output_format,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    return token, exp * 1000


def consume_ticket(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except ExpiredSignatureError as exc:
        raise VoiceTicketError("ticket 已过期") from exc
    except JWTError as exc:
        raise VoiceTicketError("ticket 无效") from exc

    if payload.get("aud") != _AUDIENCE:
        raise VoiceTicketError("ticket audience 无效")
    user_id = str(payload.get("sub") or "").strip()
    jti = str(payload.get("jti") or "").strip()
    exp = int(payload.get("exp") or 0)
    if not user_id or not jti or exp <= int(time.time()):
        raise VoiceTicketError("ticket 无效")
    if payload.get("input_format") != "pcm_16k_s16le":
        raise VoiceTicketError("ticket 输入格式无效")
    if payload.get("output_format") != "pcm_s16le":
        raise VoiceTicketError("ticket 输出格式无效")
    normalize_voice(str(payload.get("voice") or ""))
    ticket_store.consume(jti, exp)
    return payload


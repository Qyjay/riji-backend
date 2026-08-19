"""实时语音的进程内指标与脱敏结构化日志。"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from threading import Lock
from typing import Any


logger = logging.getLogger("uvicorn.error")
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "audio",
    "base64",
    "content",
    "jwt",
    "ticket",
    "token",
    "transcript",
}


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(str(user_id or "").encode("utf-8")).hexdigest()[:12]


def _sanitize(value: Any, *, key: str = "") -> Any:
    normalized = key.lower().replace("-", "_")
    if any(part in normalized for part in _SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value[:20]]
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:240]


def safe_log_payload(event: str, **fields: Any) -> dict[str, Any]:
    payload = {"event": str(event or "voice.event")[:80]}
    payload.update(_sanitize(fields))
    return payload


def log_voice_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(
        level,
        "[realtime_voice] %s",
        json.dumps(
            safe_log_payload(event, **fields),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )


class RealtimeVoiceMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[str] = Counter()

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[str(name)] += int(value)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()


voice_metrics = RealtimeVoiceMetrics()

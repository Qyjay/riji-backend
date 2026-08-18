"""实时语音高风险动作的一次性确认状态机。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from uuid import uuid4

from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings


_AUDIENCE = "realtime_voice_confirmation"


class ConfirmationError(ValueError):
    pass


@dataclass
class ConfirmationRecord:
    id: str
    token: str
    user_id: str
    voice_session_id: str
    action: str
    resource_id: str
    resource_hash: str
    title: str
    summary: list[str]
    expires_at: int
    created_turn: int
    status: str = "pending"
    decision: str = ""
    channel: str = ""
    result: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "riskLevel": "R2",
            "title": self.title,
            "summary": self.summary,
            "expiresAt": self.expires_at,
            "approveLabel": "确认开始",
            "rejectLabel": "再改一下",
        }


class ConfirmationManager:
    """确认对象仅存在于当前实时会话，签名 Token 用于语音确认防篡改。"""

    def __init__(self, *, user_id: str, voice_session_id: str) -> None:
        self.user_id = user_id
        self.voice_session_id = voice_session_id
        self._records: dict[str, ConfirmationRecord] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        action: str,
        resource_id: str,
        resource_hash: str,
        title: str,
        summary: list[str],
        created_turn: int,
        metadata: dict[str, Any] | None = None,
    ) -> ConfirmationRecord:
        now = int(time.time())
        expires_at = now + max(10, int(settings.REALTIME_VOICE_CONFIRM_TTL_SEC))
        confirmation_id = str(uuid4())
        payload = {
            "aud": _AUDIENCE,
            "sub": self.user_id,
            "sid": self.voice_session_id,
            "cid": confirmation_id,
            "action": action,
            "rid": resource_id,
            "rhash": resource_hash,
            "turn": int(created_turn),
            "jti": str(uuid4()),
            "iat": now,
            "exp": expires_at,
        }
        token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
        record = ConfirmationRecord(
            id=confirmation_id,
            token=token,
            user_id=self.user_id,
            voice_session_id=self.voice_session_id,
            action=action,
            resource_id=resource_id,
            resource_hash=resource_hash,
            title=title[:120],
            summary=[str(item)[:200] for item in summary[:8]],
            expires_at=expires_at * 1000,
            created_turn=int(created_turn),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._records[record.id] = record
            if len(self._records) > 20:
                oldest = next(iter(self._records))
                self._records.pop(oldest, None)
        return record

    def get(self, confirmation_id: str) -> ConfirmationRecord:
        with self._lock:
            record = self._records.get(str(confirmation_id or ""))
        if not record:
            raise ConfirmationError("确认不存在或不属于当前会话")
        if record.expires_at <= int(time.time() * 1000) and record.status == "pending":
            record.status = "expired"
            raise ConfirmationError("确认已过期，请重新整理任务")
        return record

    def _decode_token(self, token: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except ExpiredSignatureError as exc:
            raise ConfirmationError("确认已过期，请重新整理任务") from exc
        except JWTError as exc:
            raise ConfirmationError("确认 Token 无效") from exc
        if payload.get("aud") != _AUDIENCE:
            raise ConfirmationError("确认 Token 无效")
        return payload

    def resolve_screen(
        self,
        *,
        confirmation_id: str,
        decision: str,
    ) -> tuple[ConfirmationRecord, bool]:
        return self._resolve(
            record=self.get(confirmation_id),
            decision=decision,
            channel="screen",
        )

    def resolve_voice(
        self,
        *,
        token: str,
        action: str,
        resource_id: str,
        resource_hash: str,
        current_turn: int,
    ) -> tuple[ConfirmationRecord, bool]:
        payload = self._decode_token(token)
        confirmation_id = str(payload.get("cid") or "")
        record = self.get(confirmation_id)
        checks = {
            "sub": self.user_id,
            "sid": self.voice_session_id,
            "action": action,
            "rid": resource_id,
            "rhash": resource_hash,
        }
        if any(str(payload.get(key) or "") != value for key, value in checks.items()):
            raise ConfirmationError("确认 Token 与当前操作不匹配")
        if (
            record.action != action
            or record.resource_id != resource_id
            or record.resource_hash != resource_hash
        ):
            raise ConfirmationError("任务摘要已变化，请重新确认")
        if int(current_turn) <= record.created_turn:
            raise ConfirmationError("请在下一句话中明确确认后再开始")
        return self._resolve(record=record, decision="approve", channel="voice")

    @staticmethod
    def _resolve(
        *,
        record: ConfirmationRecord,
        decision: str,
        channel: str,
    ) -> tuple[ConfirmationRecord, bool]:
        if decision not in {"approve", "reject"}:
            raise ConfirmationError("确认决定不受支持")
        target_status = "approved" if decision == "approve" else "rejected"
        if record.status == target_status:
            return record, False
        if record.status != "pending":
            raise ConfirmationError("确认已经处理，不能更改决定")
        record.status = target_status
        record.decision = decision
        record.channel = channel
        return record, decision == "approve"

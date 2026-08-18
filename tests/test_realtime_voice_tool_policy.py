import asyncio
import json
import time

import pytest
from pydantic import BaseModel, ConfigDict

from app.models.realtime_voice import RealtimeToolCall, RealtimeVoiceSession
from app.realtime_voice.policy import ToolPolicyError, ToolRisk
from app.realtime_voice.provider import ProviderToolCall
from app.realtime_voice.tools import (
    ToolHandlerOutput,
    ToolRegistry,
    ToolRouter,
    ToolSpec,
)
from tests.conftest import TestingSessionLocal, create_test_user


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _session(db, user_id: str, session_id: str = "voice-tool-policy"):
    now = int(time.time() * 1000)
    db.add(
        RealtimeVoiceSession(
            id=session_id,
            user_id=user_id,
            status="active",
            started_at=now,
            last_active_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def test_registry_rejects_r3_tools():
    registry = ToolRegistry()
    with pytest.raises(ToolPolicyError, match="R3"):
        registry.register(
            ToolSpec(
                name="accept_relationship",
                description="禁止工具",
                args_model=EmptyArgs,
                risk=ToolRisk.R3,
                handler=lambda *_args: ToolHandlerOutput(data={}),
                read_only=False,
            )
        )


def test_tool_arguments_are_strict_and_unknown_tools_are_rejected(client, db):
    auth = create_test_user(client, username="voice_policy")
    user_id = auth["user"]["id"]
    _session(db, user_id)

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="safe_read",
            description="只读",
            args_model=EmptyArgs,
            risk=ToolRisk.R0,
            handler=lambda *_args: ToolHandlerOutput(data={"value": 1}),
        )
    )
    router = ToolRouter(
        voice_session_id="voice-tool-policy",
        client_session_id="voice-tool-policy",
        user_id=user_id,
        db_factory=TestingSessionLocal,
        registry=registry,
    )

    async def run():
        return await router.execute_calls(
            [
                ProviderToolCall("call-bad-args", "safe_read", '{"extra":1}'),
                ProviderToolCall("call-unknown", "delete_everything", "{}"),
            ]
        )

    results, _ = asyncio.run(run())
    first = json.loads(results[0].output)
    second = json.loads(results[1].output)
    assert first["ok"] is False
    assert second == {"ok": False, "data": None, "error": "该工具未开放"}

    rows = db.query(RealtimeToolCall).order_by(RealtimeToolCall.created_at).all()
    assert [row.status for row in rows] == ["failed", "rejected"]
    assert rows[1].risk_level == "R3"

import asyncio
import json

from app.realtime_voice.provider import (
    ProviderSessionConfig,
    ProviderToolResult,
    ToolDefinition,
)
from app.realtime_voice.volcengine import VolcengineDuplexProvider


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.response_headers = {"X-Tt-Logid": "log-123"}
        self.incoming: asyncio.Queue[str | None] = asyncio.Queue()
        self.closed = False

    async def send(self, raw: str):
        self.sent.append(json.loads(raw))

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.incoming.get()
        if item is None:
            raise StopAsyncIteration
        return item


def test_volcengine_provider_protocol_mapping(monkeypatch):
    async def run():
        ws = FakeWebSocket()

        async def fake_connect(*_args, **_kwargs):
            return ws

        monkeypatch.setattr(
            "app.realtime_voice.volcengine.websockets.connect",
            fake_connect,
        )
        provider = VolcengineDuplexProvider(
            api_key="secret-test-key",
            url="wss://example.test/realtime",
        )
        await provider.connect(
            ProviderSessionConfig(
                instructions="你是 Avalin 分身。",
                voice="zh_female_vv_jupiter_bigtts",
                tools=[
                    ToolDefinition(
                        "search_personal_memory",
                        "检索记忆",
                        {"type": "object", "properties": {}},
                    )
                ],
            )
        )
        create = ws.sent[0]
        assert create["type"] == "session.create"
        assert create["session"]["model"] == "1.2.6.1"
        assert create["session"]["audio"]["input"]["format"]["rate"] == 16000
        assert create["session"]["audio"]["output"]["format"]["rate"] == 24000
        assert create["session"]["tools"][0]["name"] == "search_personal_memory"
        assert "secret-test-key" not in json.dumps(create)
        assert provider.provider_log_id == "log-123"

        await provider.send_audio("AAE=", "audio-1")
        await provider.commit_audio("commit-1")
        await provider.cancel_response("cancel-1")
        await provider.send_tool_results(
            [ProviderToolResult(call_id="call-1", output='{"ok":true}')]
        )
        assert [item["type"] for item in ws.sent[1:]] == [
            "input_audio_buffer.append",
            "input_audio_buffer.commit",
            "response.cancel",
            "conversation.item.create",
        ]
        assert ws.sent[-1]["items"][0]["call_id"] == "call-1"

        await ws.incoming.put(
            json.dumps(
                {
                    "type": "session.created",
                    "event_id": "server-1",
                    "session": {"id": "dialog-1"},
                }
            )
        )
        await ws.incoming.put(
            json.dumps(
                {
                    "type": "response.function_call_arguments.done",
                    "items": [
                        {
                            "call_id": "call-2",
                            "name": "search_personal_memory",
                            "arguments": '{"query":"晚霞"}',
                        }
                    ],
                }
            )
        )
        await ws.incoming.put(None)
        events = [event async for event in provider.receive()]
        assert events[0].type == "session.ready"
        assert events[0].payload["providerSessionId"] == "dialog-1"
        assert events[1].type == "tool.calls"
        assert events[1].tool_calls[0].call_id == "call-2"

        provider._session_closed.set()
        sent_count = len(ws.sent)
        await provider.close()
        assert len(ws.sent) == sent_count
        assert ws.closed is True

    asyncio.run(run())

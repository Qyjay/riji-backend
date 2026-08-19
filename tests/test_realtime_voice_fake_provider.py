import asyncio

from app.realtime_voice.fake_provider import FakeRealtimeVoiceProvider
from app.realtime_voice.provider import (
    ProviderEvent,
    ProviderSessionConfig,
    ProviderToolResult,
    ToolDefinition,
)


def test_fake_provider_records_client_events_and_streams_script():
    async def run():
        scripted = [
            ProviderEvent("session.ready", payload={"providerSessionId": "fake"}),
            ProviderEvent("asr.done", payload={"text": "你好"}),
        ]
        provider = FakeRealtimeVoiceProvider(scripted)
        config = ProviderSessionConfig(
            instructions="test",
            voice="voice",
            tools=[ToolDefinition("search", "search", {"type": "object"})],
        )
        await provider.connect(config)
        await provider.send_audio("AAE=", "evt-audio")
        await provider.commit_audio("evt-commit")
        await provider.cancel_response("evt-cancel")
        await provider.send_tool_results([ProviderToolResult("call-1", '{"ok":true}')])
        await provider.finish()

        events = [event async for event in provider.receive()]
        assert [event.type for event in events] == ["session.ready", "asr.done"]
        assert provider.config is config
        assert provider.audio_events == [("evt-audio", "AAE=")]
        assert provider.commits == ["evt-commit"]
        assert provider.cancels == ["evt-cancel"]
        assert provider.tool_results[0].call_id == "call-1"

    asyncio.run(run())


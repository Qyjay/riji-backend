"""
OpenClaw Gateway HTTP 客户端

走 OpenClaw Gateway（OpenAI 兼容格式）发起 AI 对话：
- chat()        非流式，返回完整文本
- stream_chat() 流式，AsyncGenerator[str, None]

user 字段设为 "riji-{user_id}" 实现 per-user session 隔离。
"""
import json
from typing import AsyncGenerator, Optional

import httpx

from app.config import settings


class OpenClawClient:
    """OpenClaw Gateway 客户端（OpenAI 兼容格式）"""

    def __init__(self, gateway_url: str, token: str, agent_id: str):
        self.gateway_url = gateway_url.rstrip("/")
        self.token = token
        self.agent_id = agent_id
        self.model = f"openclaw:{agent_id}"

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "x-openclaw-agent-id": self.agent_id,
        }

    def _build_payload(
        self,
        messages: list,
        user_id: str,
        system_prompt: str,
        stream: bool,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "user": f"riji-{user_id}",
            "stream": stream,
        }
        if system_prompt:
            payload["messages"] = [
                {"role": "system", "content": system_prompt},
                *messages,
            ]
        return payload

    async def chat(
        self,
        messages: list,
        user_id: str,
        system_prompt: str = "",
    ) -> str:
        """
        非流式对话，返回完整回复文本

        Raises:
            httpx.HTTPError: 网络/HTTP 错误（调用方负责降级处理）
        """
        payload = self._build_payload(messages, user_id, system_prompt, stream=False)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.gateway_url}/v1/chat/completions",
                headers=self._headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return ""
            return choices[0].get("message", {}).get("content", "")

    async def stream_chat(
        self,
        messages: list,
        user_id: str,
        system_prompt: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        流式对话，逐块 yield 文本片段

        解析 OpenAI 兼容 SSE 格式：data: {"choices":[{"delta":{"content":"..."}}]}

        Raises:
            httpx.HTTPError: 网络/HTTP 错误（调用方负责降级处理）
        """
        payload = self._build_payload(messages, user_id, system_prompt, stream=True)
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.gateway_url}/v1/chat/completions",
                headers=self._headers,
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
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue


# ==================== 全局单例 ====================

_openclaw_client: Optional[OpenClawClient] = None


def get_openclaw_client() -> OpenClawClient:
    """获取 OpenClaw 客户端单例"""
    global _openclaw_client
    if _openclaw_client is None:
        _openclaw_client = OpenClawClient(
            gateway_url=settings.OPENCLAW_GATEWAY_URL,
            token=settings.OPENCLAW_GATEWAY_TOKEN,
            agent_id=settings.OPENCLAW_AGENT_ID,
        )
    return _openclaw_client

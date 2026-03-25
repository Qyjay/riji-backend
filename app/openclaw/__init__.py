"""
OpenClaw Gateway 客户端包
提供带记忆的 AI 对话能力，走 OpenClaw Gateway 而非直连 MiniMax
"""
from app.openclaw.client import OpenClawClient, get_openclaw_client

__all__ = ["OpenClawClient", "get_openclaw_client"]

"""
聊天场景下的 Exa 联网搜索服务
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger("uvicorn.error")


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str
    domain: str
    published_at: Optional[str]

    def to_attachment(self) -> Dict[str, Any]:
        return {
            "type": "web",
            "name": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "domain": self.domain,
            "published_at": self.published_at,
            "source": "exa",
        }


def _sanitize(text: Any) -> str:
    return str(text or "").strip()


def _pick_snippet(item: Dict[str, Any]) -> str:
    highlights = item.get("highlights") or []
    if isinstance(highlights, list) and highlights:
        return _sanitize(highlights[0])[:500]
    return _sanitize(item.get("summary"))[:500]


def _build_context(results: List[WebSearchResult]) -> str:
    lines: List[str] = []
    for idx, result in enumerate(results[:3], start=1):
        date_text = f"（发布时间：{result.published_at}）" if result.published_at else ""
        lines.append(
            f"{idx}. {result.title}\n"
            f"URL: {result.url}\n"
            f"摘要: {result.snippet or '无'}\n"
            f"{date_text}"
        )
    return "\n\n".join(lines).strip()


async def search_web_for_chat(query: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    返回 (可直接写入消息 attachments 的结果列表, 给 LLM 的上下文文本)
    """
    if not settings.EXA_SEARCH_ENABLED:
        return [], ""
    if not settings.EXA_API_KEY.strip():
        logger.warning("[chat] EXA_SEARCH_ENABLED=true 但未配置 EXA_API_KEY，跳过联网搜索")
        return [], ""

    payload = {
        "query": query,
        "type": "auto",
        "numResults": max(1, min(settings.EXA_SEARCH_NUM_RESULTS, 10)),
        "contents": {
            "highlights": {
                "maxCharacters": max(300, min(settings.EXA_SEARCH_HIGHLIGHTS_MAX_CHARACTERS, 4000)),
            },
            "maxAgeHours": 0,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.EXA_API_KEY,
    }
    url = f"{settings.EXA_API_BASE.rstrip('/')}/search"

    try:
        async with httpx.AsyncClient(timeout=settings.EXA_SEARCH_TIMEOUT_SEC, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("[chat] exa search failed: %s", str(exc))
        return [], ""

    raw_results = data.get("results") or []
    normalized: List[WebSearchResult] = []
    for item in raw_results:
        url_value = _sanitize(item.get("url"))
        if not url_value:
            continue
        domain = urlparse(url_value).netloc
        normalized.append(
            WebSearchResult(
                title=_sanitize(item.get("title")) or url_value,
                url=url_value,
                snippet=_pick_snippet(item),
                domain=domain,
                published_at=_sanitize(item.get("publishedDate")) or None,
            )
        )

    if not normalized:
        return [], ""

    attachments = [item.to_attachment() for item in normalized]
    context_text = _build_context(normalized)
    return attachments, context_text

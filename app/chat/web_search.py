"""
聊天场景下的联网搜索服务
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
    source: str

    def to_attachment(self) -> Dict[str, Any]:
        return {
            "type": "web",
            "name": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "domain": self.domain,
            "published_at": self.published_at,
            "source": self.source,
        }


def _sanitize(text: Any) -> str:
    return str(text or "").strip()


def _pick_snippet(item: Dict[str, Any]) -> str:
    highlights = item.get("highlights") or []
    if isinstance(highlights, list) and highlights:
        return _sanitize(highlights[0])[:500]
    return _sanitize(item.get("summary"))[:500]


def _pick_volc_snippet(item: Dict[str, Any]) -> str:
    for key in ("Summary", "Snippet", "Content"):
        snippet = _sanitize(item.get(key))
        if snippet:
            return snippet[:500]
    return ""


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


def _normalize_provider() -> str:
    provider = _sanitize(getattr(settings, "WEB_SEARCH_PROVIDER", "exa")).lower()
    if provider in {"volc", "volcengine", "bytedance"}:
        return "volcengine"
    return "exa"


async def _search_exa(query: str) -> List[WebSearchResult]:
    if not settings.EXA_SEARCH_ENABLED:
        return []
    if not settings.EXA_API_KEY.strip():
        logger.warning("[chat] EXA_SEARCH_ENABLED=true 但未配置 EXA_API_KEY，跳过联网搜索")
        return []

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
        return []

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
                source="exa",
            )
        )
    return normalized


async def _search_volcengine(query: str) -> List[WebSearchResult]:
    if not settings.VOLC_SEARCH_ENABLED:
        return []
    if not settings.VOLC_SEARCH_API_KEY.strip():
        logger.warning("[chat] VOLC_SEARCH_ENABLED=true 但未配置 VOLC_SEARCH_API_KEY，跳过联网搜索")
        return []

    payload = {
        "Query": query,
        "SearchType": "web",
        "Count": max(1, min(settings.VOLC_SEARCH_NUM_RESULTS, 10)),
        "Filter": {
            "NeedContent": False,
            "NeedUrl": True,
        },
        "NeedSummary": True,
        "TimeRange": _sanitize(settings.VOLC_SEARCH_TIME_RANGE) or "OneYear",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.VOLC_SEARCH_API_KEY}",
    }
    url = settings.VOLC_SEARCH_API_BASE.strip()

    try:
        async with httpx.AsyncClient(timeout=settings.VOLC_SEARCH_TIMEOUT_SEC, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("[chat] volcengine search failed: %s", str(exc))
        return []

    result = data.get("Result") or {}
    raw_results = result.get("WebResults") or []
    normalized: List[WebSearchResult] = []
    for item in raw_results:
        url_value = _sanitize(item.get("Url"))
        if not url_value:
            continue
        domain = urlparse(url_value).netloc or _sanitize(item.get("SiteName"))
        normalized.append(
            WebSearchResult(
                title=_sanitize(item.get("Title")) or url_value,
                url=url_value,
                snippet=_pick_volc_snippet(item),
                domain=domain,
                published_at=_sanitize(item.get("PublishTime")) or None,
                source="volcengine",
            )
        )
    return normalized


async def search_web_for_chat(query: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    返回 (可直接写入消息 attachments 的结果列表, 给 LLM 的上下文文本)
    """
    provider = _normalize_provider()
    if provider == "volcengine":
        normalized = await _search_volcengine(query)
    else:
        normalized = await _search_exa(query)

    if not normalized:
        return [], ""

    attachments = [item.to_attachment() for item in normalized]
    context_text = _build_context(normalized)
    return attachments, context_text

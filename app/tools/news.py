from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import feedparser
import httpx

from app.tools.filesystem import _error, _ok

# Google News 在当前网络下偶发 SSL EOF / 握手超时，重试一次能明显降低失败率
_FETCH_ATTEMPTS = 2
_FETCH_RETRY_DELAY = 0.8


def _default_fetch(url: str) -> bytes:
    response = httpx.get(
        url,
        headers={"User-Agent": "ai-news-agent/1.0"},
        follow_redirects=True,
        timeout=15,
    )
    response.raise_for_status()
    return response.content


def _fetch_with_retry(fetch: Callable[[str], bytes], url: str) -> bytes:
    """只对网络类异常重试，避免把程序错误也重试一遍。"""
    last_error: Exception | None = None
    for attempt in range(_FETCH_ATTEMPTS):
        try:
            return fetch(url)
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            if attempt + 1 < _FETCH_ATTEMPTS:
                time.sleep(_FETCH_RETRY_DELAY)
    raise last_error  # type: ignore[misc]


def _plain_text(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


class NewsSearchTool:
    def __init__(self, fetch: Callable[[str], bytes] | None = None) -> None:
        self.fetch = fetch or _default_fetch

    def search_news(self, query: str, limit: int = 10) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return _error("query is required")
        limit = max(1, min(limit, 20))
        url = "https://news.google.com/rss/search?" + urlencode(
            {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
        )
        try:
            feed = feedparser.parse(_fetch_with_retry(self.fetch, url))
        except Exception as exc:
            return _error(f"news search failed: {exc}")

        seen_urls: set[str] = set()
        items: list[dict[str, str]] = []
        for entry in feed.entries:
            item_url = str(entry.get("link", "")).strip()
            if not item_url or item_url in seen_urls:
                continue
            seen_urls.add(item_url)
            source_value = entry.get("source", {})
            source = source_value.get("title", "") if hasattr(source_value, "get") else ""
            items.append(
                {
                    "title": _plain_text(str(entry.get("title", ""))),
                    "url": item_url,
                    "summary": _plain_text(str(entry.get("summary", entry.get("description", "")))),
                    "source": _plain_text(str(source)),
                    "published_at": str(entry.get("published", "")),
                }
            )
            if len(items) >= limit:
                break
        return _ok({"query": query, "items": items})

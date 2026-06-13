"""Fetcher service — retrieves and extracts page content from a URL.

Tries Ollama web_fetch first, falls back to Trafilatura.
Returns the extracted plain text or empty string on failure.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any


def _web_fetch_content(ollama: Any, url: str) -> str:
    """Sync call to Ollama web_fetch — run in a thread."""
    web_fetch = getattr(ollama, "web_fetch", None)
    if web_fetch is None:
        return ""
    try:
        response = web_fetch(url)
    except Exception:
        return ""

    if hasattr(response, "model_dump"):
        payload = response.model_dump()
        return str(payload.get("content", "") or "").strip()

    content = getattr(response, "content", "")
    return str(content or "").strip()


async def _trafilatura_fetch(url: str) -> str:
    """Async trafilatura fetch using our HTTP client."""
    try:
        import trafilatura
    except Exception:
        return ""
    try:
        from src.infra.http import async_get
        html = await async_get(url)
        if not html:
            return ""
        extracted = await asyncio.to_thread(
            trafilatura.extract, html, False, False
        )
        return (extracted or "").strip()
    except Exception:
        return ""


class FetcherService:
    def __init__(self, ollama: Any) -> None:
        self.ollama = ollama

    async def fetch(self, url: str, max_chars: int = 8000) -> tuple[str, str]:
        """Fetch a URL and return (text, method_used).

        method_used is one of: "web_fetch", "trafilatura", "none"
        """
        content = await asyncio.to_thread(_web_fetch_content, self.ollama, url)
        if content:
            return content[:max_chars], "web_fetch"

        content = await _trafilatura_fetch(url)
        if content:
            return content[:max_chars], "trafilatura"

        return "", "none"

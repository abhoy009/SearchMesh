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


def _trafilatura_fetch(url: str) -> str:
    """Sync trafilatura fetch — run in a thread."""
    try:
        import trafilatura
    except Exception:
        return ""
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return ""
    extracted = trafilatura.extract(downloaded, include_links=False, include_images=False)
    return (extracted or "").strip()


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

        content = await asyncio.to_thread(_trafilatura_fetch, url)
        if content:
            return content[:max_chars], "trafilatura"

        return "", "none"

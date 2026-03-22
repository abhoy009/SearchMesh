from __future__ import annotations

from typing import Any


def _web_fetch_content(ollama: Any, url: str) -> str:
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


class FetcherService:
    def __init__(self, ollama: Any) -> None:
        self.ollama = ollama

    def fetch(self, url: str) -> str:
        content = _web_fetch_content(self.ollama, url)
        if content:
            return content

        try:
            import trafilatura
        except Exception:
            return ""

        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""

        extracted = trafilatura.extract(downloaded, include_links=False, include_images=False)
        return (extracted or "").strip()

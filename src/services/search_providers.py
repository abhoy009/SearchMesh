"""Search providers — multi-tier fallback: Ollama → Serper → DuckDuckGo.

All methods are now async. Serper and DDG use the shared httpx.AsyncClient.
Ollama web_search is wrapped with asyncio.to_thread (sync SDK).
"""
from __future__ import annotations

import asyncio
import json
import urllib.parse
from typing import Any

from bs4 import BeautifulSoup

from src.app.config import settings
from src.app.models import SearchResult
from src.infra.http import async_get, async_post


def _parse_ollama_results(response: Any) -> list[SearchResult]:
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    elif isinstance(response, dict):
        payload = response
    else:
        payload = {"results": response}

    results = payload.get("results", []) if isinstance(payload, dict) else []
    clean: list[SearchResult] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        url = str(item.get("url", "") or "").strip()
        content = str(item.get("content", "") or "").strip()
        if url:
            clean.append(SearchResult(title=title, url=url, content=content, source="ollama"))
    return clean


def _normalize_ddg_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = urllib.parse.parse_qs(parsed.query)
        return urllib.parse.unquote(query.get("uddg", [""])[0])
    return url


async def _serper_search(query: str, max_results: int = 8) -> list[SearchResult]:
    api_key = settings.serper_api_key.strip()
    if not api_key:
        return []
    data = await async_post(
        "https://google.serper.dev/search",
        json={"q": query, "num": max_results},
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        timeout=float(settings.timeout_search_seconds),
    )
    results: list[SearchResult] = []
    for item in data.get("organic", []):
        title = str(item.get("title", "") or "").strip()
        url = str(item.get("link", "") or "").strip()
        snippet = str(item.get("snippet", "") or "").strip()
        if title and url.startswith("http"):
            results.append(SearchResult(title=title, url=url, content=snippet, source="serper"))
        if len(results) >= max_results:
            break
    return results


async def _duckduckgo_search(query: str, max_results: int = 8) -> list[SearchResult]:
    encoded = urllib.parse.quote_plus(query)
    html = await async_get(
        f"https://duckduckgo.com/html/?q={encoded}",
        timeout=float(settings.timeout_search_seconds),
    )
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    for node in soup.select(".result"):
        anchor = node.select_one("a.result__a")
        if anchor is None:
            continue
        url = _normalize_ddg_url(anchor.get("href", "").strip())
        title = anchor.get_text(" ", strip=True)
        snippet_node = node.select_one(".result__snippet")
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
        if title and url.startswith("http"):
            results.append(SearchResult(title=title, url=url, content=snippet, source="duckduckgo"))
        if len(results) >= max_results:
            break

    return results


class FallbackSearchProvider:
    def __init__(self, ollama: Any) -> None:
        self.ollama = ollama

    async def search(self, query: str, max_results: int) -> tuple[list[SearchResult], str]:
        """Search using fallback chain. Returns (results, provider_used)."""
        # Tier 1: Ollama web_search
        try:
            web_search = getattr(self.ollama, "web_search", None)
            if web_search:
                results = await asyncio.to_thread(
                    lambda: _parse_ollama_results(web_search(query=query, max_results=max_results))
                )
                if results:
                    return results, "ollama"
        except Exception:
            pass

        # Tier 2: Serper
        try:
            results = await _serper_search(query, max_results=max_results)
            if results:
                return results, "serper"
        except Exception:
            pass

        # Tier 3: DuckDuckGo
        try:
            results = await _duckduckgo_search(query, max_results=max_results)
            return results, "duckduckgo"
        except Exception:
            pass

        return [], "none"

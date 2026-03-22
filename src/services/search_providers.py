from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from bs4 import BeautifulSoup

from src.app.models import SearchResult
from src.infra.http_client import http_get


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
            clean.append(SearchResult(title=title, url=url, content=content, source="ollama_web_search"))
    return clean


def _normalize_ddg_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = urllib.parse.parse_qs(parsed.query)
        return urllib.parse.unquote(query.get("uddg", [""])[0])
    return url


def _serper_search(query: str, max_results: int = 8) -> list[SearchResult]:
    serper_api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not serper_api_key:
        return []

    payload = json.dumps({"q": query, "num": max_results}).encode("utf-8")
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=payload,
        method="POST",
        headers={
            "X-API-KEY": serper_api_key,
            "Content-Type": "application/json",
            "User-Agent": "agent-search/1.0",
        },
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read().decode("utf-8", errors="ignore")

    data = json.loads(raw)
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


def _duckduckgo_search(query: str, max_results: int = 8) -> list[SearchResult]:
    encoded = urllib.parse.quote_plus(query)
    html = http_get(f"https://duckduckgo.com/html/?q={encoded}")
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

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            web_search = getattr(self.ollama, "web_search", None)
            if web_search:
                results = _parse_ollama_results(web_search(query=query, max_results=max_results))
                if results:
                    return results
        except Exception:
            pass

        try:
            results = _serper_search(query, max_results=max_results)
            if results:
                return results
        except Exception:
            pass

        return _duckduckgo_search(query, max_results=max_results)

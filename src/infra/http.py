"""Shared async HTTP client.

A single httpx.AsyncClient instance is created at server startup (in api.py's
lifespan) and stored here. All services that need to make outbound HTTP calls
import `get_http_client()` rather than creating their own clients.

This prevents connection pool exhaustion and enables proper cleanup on shutdown.
"""
from __future__ import annotations

import httpx

# Module-level client reference — set during app startup via set_http_client()
_client: httpx.AsyncClient | None = None

# User-Agent sent on all outbound requests
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def set_http_client(client: httpx.AsyncClient) -> None:
    """Called once during app startup lifespan."""
    global _client
    _client = client


def get_http_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("HTTP client not initialised — call set_http_client() at startup")
    return _client


async def async_get(url: str, timeout: float = 10.0, headers: dict | None = None) -> str:
    """Perform an async GET request and return the response body as text."""
    client = get_http_client()
    merged_headers = {"User-Agent": _USER_AGENT}
    if headers:
        merged_headers.update(headers)
    response = await client.get(url, headers=merged_headers, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.text


async def async_post(
    url: str,
    json: dict | None = None,
    headers: dict | None = None,
    timeout: float = 10.0,
) -> dict:
    """Perform an async POST request and return the parsed JSON response."""
    client = get_http_client()
    merged_headers = {"User-Agent": _USER_AGENT, "Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    response = await client.post(url, json=json, headers=merged_headers, timeout=timeout)
    response.raise_for_status()
    return response.json()

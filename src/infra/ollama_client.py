"""Ollama client builder and readiness helpers."""
from __future__ import annotations

import asyncio
from typing import Any

from src.app.config import settings


def import_ollama() -> Any:
    try:
        import ollama
    except Exception as exc:
        raise RuntimeError("Install/update ollama python package: pip install -U 'ollama>=0.6.0'") from exc
    return ollama


def build_client(ollama: Any) -> Any:
    host = settings.ollama_host.strip()
    api_key = settings.ollama_api_key.strip()

    if host and api_key:
        return ollama.Client(host=host, headers={"Authorization": f"Bearer {api_key}"})
    if host:
        return ollama.Client(host=host)
    if api_key:
        return ollama.Client(headers={"Authorization": f"Bearer {api_key}"})
    return ollama.Client()


def is_ready(client: Any) -> bool:
    try:
        client.ps()
        return True
    except Exception:
        return False


async def is_ready_async(client: Any) -> bool:
    """Non-blocking readiness check — wraps the sync SDK call in a thread."""
    return await asyncio.to_thread(is_ready, client)

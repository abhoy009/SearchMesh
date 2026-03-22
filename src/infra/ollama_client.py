from __future__ import annotations

import os
from typing import Any


def import_ollama() -> Any:
    try:
        import ollama
    except Exception as exc:
        raise RuntimeError("Install/update ollama python package: pip install -U 'ollama>=0.6.0'") from exc
    return ollama


def build_client(ollama: Any) -> Any:
    host = os.getenv("OLLAMA_HOST", "").strip()
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()

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

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class RuntimeConfig:
    model: str
    max_results: int
    debug: bool
    ollama_host: str
    ollama_api_key: str
    serper_api_key: str


def _env_bool(name: str, default: str = "1") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value not in {"0", "false", "no", "off"}


def load_runtime_config(max_results: int = 5) -> RuntimeConfig:
    load_dotenv()
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b").strip() or "qwen2.5:0.5b"
    return RuntimeConfig(
        model=model,
        max_results=max_results,
        debug=_env_bool("AGENT_DEBUG", "1"),
        ollama_host=os.getenv("OLLAMA_HOST", "").strip(),
        ollama_api_key=os.getenv("OLLAMA_API_KEY", "").strip(),
        serper_api_key=os.getenv("SERPER_API_KEY", "").strip(),
    )


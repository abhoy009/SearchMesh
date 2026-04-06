"""Runtime configuration via pydantic-settings.

Single source of truth for all environment variables.
Access via: from src.app.config import settings

Required env vars (no defaults — server will not start if missing):
  DECISION_MODEL  e.g. qwen2.5:0.5b   (fast: decision, query gen, validate)
  RESPONSE_MODEL  e.g. llama3.2:1b    (quality: final answer)
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Ollama — base
    ollama_host: str = "http://localhost:11434"
    ollama_api_key: str = ""

    # Split-model config — NO defaults, must be set via env vars:
    #   DECISION_MODEL  → fast tiny model for decision + query generation
    #   RESPONSE_MODEL  → quality model for the final answer
    decision_model: str
    response_model: str

    # Optional legacy override — if set, forces both services to use this model.
    ollama_model: str = ""

    # Search
    serper_api_key: str = ""
    max_results: int = 5

    # Context
    max_context_chars: int = 4000

    # Debug
    agent_debug: bool = False

    # Session (used in M3, defined here for /v1/config)
    session_ttl_seconds: int = 3600
    session_max_turns: int = 20

    # Cache TTL (used in M2, defined here for /v1/config)
    cache_search_ttl_seconds: int = 600
    cache_fetch_ttl_seconds: int = 1800

    # Timeouts (seconds)
    timeout_search_seconds: int = 5
    timeout_fetch_seconds: int = 8
    timeout_ollama_seconds: int = 30
    timeout_global_seconds: int = 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Module-level singleton — import this everywhere
settings: Settings = get_settings()

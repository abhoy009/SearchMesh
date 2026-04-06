"""Pydantic request/response schemas for all M1 API endpoints.

Every endpoint has typed inputs and typed outputs — no bare dicts in route handlers.
Schema definitions match the API contract in plan.md exactly.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Shared / sub-models
# ---------------------------------------------------------------------------

class SourceResult(BaseModel):
    url: str
    title: str
    snippet: str
    score: float
    source: str  # "ollama" | "serper" | "duckduckgo"


class LatencyBreakdown(BaseModel):
    decision: float = 0.0
    search: float = 0.0
    fetch: float = 0.0
    validate_ms: float = 0.0
    respond: float = 0.0
    total: float = 0.0


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str


# ---------------------------------------------------------------------------
# POST /v1/chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's input text")
    session_id: str | None = Field(default=None, description="Resume an existing session")
    use_web: bool = Field(default=True, description="If false, skip decision step and answer from model knowledge")
    model: str | None = Field(default=None, description="Override Ollama model for this request")
    max_context_chars: int | None = Field(default=None, ge=100, le=32000, description="Max chars of fetched context")


class ChatResponse(BaseModel):
    response: str
    session_id: str
    used_web: bool
    sources: list[SourceResult] = Field(default_factory=list)
    latency_ms: LatencyBreakdown
    cache_hit: bool = False
    request_id: str


# ---------------------------------------------------------------------------
# POST /v1/search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int | None = Field(default=5, ge=1, le=10)
    sources: list[str] | None = Field(
        default=None,
        description="Restrict which providers are tried: ollama, serper, duckduckgo",
    )


class SearchResultItem(BaseModel):
    url: str
    title: str
    snippet: str
    score: float
    source: str
    rank: int


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    provider_used: str
    query_used: str
    cache_hit: bool = False
    latency_ms: float
    request_id: str


# ---------------------------------------------------------------------------
# POST /v1/fetch
# ---------------------------------------------------------------------------

class FetchRequest(BaseModel):
    url: str = Field(..., description="Must be a valid https:// URL")
    max_chars: int | None = Field(default=8000, ge=100, le=64000)

    @field_validator("url")
    @classmethod
    def must_be_https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("url must start with https://")
        return v


class FetchResponse(BaseModel):
    url: str
    text: str
    char_count: int
    method: str  # "web_fetch" | "trafilatura" | "none"
    cache_hit: bool = False
    success: bool
    latency_ms: float
    request_id: str


# ---------------------------------------------------------------------------
# GET /v1/health
# ---------------------------------------------------------------------------

class OllamaHealth(BaseModel):
    status: str  # "ok" | "unreachable"
    host: str
    model: str


class RedisHealth(BaseModel):
    status: str  # "ok" | "unreachable" | "not_configured"
    host: str


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    ollama: OllamaHealth
    redis: RedisHealth
    uptime_seconds: float
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# GET /v1/config
# ---------------------------------------------------------------------------

class CacheTTL(BaseModel):
    search_seconds: int
    fetch_seconds: int


class TimeoutConfig(BaseModel):
    search_seconds: int
    fetch_seconds: int
    ollama_seconds: int
    global_seconds: int


class ConfigResponse(BaseModel):
    model: str
    ollama_host: str
    search_providers: list[str]
    serper_api_key: str  # "configured" | "not_configured"
    agent_debug: bool
    session_ttl_seconds: int
    session_max_turns: int
    cache_ttl: CacheTTL
    timeouts: TimeoutConfig

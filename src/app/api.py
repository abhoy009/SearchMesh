"""FastAPI application entry point.

- Creates and configures the FastAPI app
- Registers lifespan (startup/shutdown) — owns the shared httpx client
- Request-ID middleware — UUID per request, attached to response header + log context
- Global exception handler — structured JSON errors, never raw stack traces
- All M1 routes: POST /v1/chat, POST /v1/search, POST /v1/fetch, GET /v1/health, GET /v1/config
"""
from __future__ import annotations

import time
import traceback
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from src.app.config import settings
from src.app.models import SearchResult
from src.app.orchestrator import DefaultTurnOrchestrator
from src.app.schemas import (
    CacheTTL,
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    ErrorResponse,
    FetchRequest,
    FetchResponse,
    HealthResponse,
    LatencyBreakdown,
    OllamaHealth,
    RedisHealth,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SourceResult,
    TimeoutConfig,
)
from src.infra import http as http_module
from src.infra.logging import get_logger, request_id_ctx
from src.infra.ollama_client import build_client, import_ollama, is_ready_async
from src.services.decision_engine import DecisionEngineService
from src.services.fetcher import FetcherService
from src.services.query_generator import QueryGeneratorService
from src.services.ranking import RankingService, rank_results
from src.services.responder import ResponderService
from src.services.search_providers import FallbackSearchProvider
from src.services.validator import ValidatorService

from redis.asyncio import Redis
from src.infra.cache import SearchMeshCache

logger = get_logger(__name__)

# Module-level references set during lifespan startup
_orchestrator: DefaultTurnOrchestrator | None = None
_search_provider: FallbackSearchProvider | None = None
_fetcher: FetcherService | None = None
_ollama_client: Any = None
_redis_client: Redis | None = None
_cache: SearchMeshCache | None = None

_server_start_time = time.monotonic()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator, _search_provider, _fetcher, _ollama_client, _redis_client, _cache

    # Shared async HTTP client
    client = httpx.AsyncClient(timeout=30.0)
    http_module.set_http_client(client)

    # Redis Cache initialization
    if settings.redis_url:
        try:
            _redis_client = Redis.from_url(settings.redis_url)
            _cache = SearchMeshCache(_redis_client)
        except Exception as exc:
            logger.warning("Failed to initialize Redis client: %s", exc)
            _cache = SearchMeshCache(None)
    else:
        _cache = SearchMeshCache(None)

    # Ollama
    ollama_lib = import_ollama()
    _ollama_client = build_client(ollama_lib)

    model = settings.ollama_model

    # Split-model wiring:
    # pipeline steps (fast, tiny) → decision_model
    # final answer (quality)       → response_model
    # If the legacy OLLAMA_MODEL env var is set, it takes precedence for both.
    decision_model = model or settings.decision_model
    response_model = model or settings.response_model

    # Build services
    decision_engine = DecisionEngineService(_ollama_client, decision_model)
    query_generator = QueryGeneratorService(_ollama_client, decision_model)
    _search_provider = FallbackSearchProvider(_ollama_client)
    ranker = RankingService()
    _fetcher = FetcherService(_ollama_client)
    validator = ValidatorService(_ollama_client, decision_model)
    responder = ResponderService(_ollama_client, response_model)

    _orchestrator = DefaultTurnOrchestrator(
        decision_engine=decision_engine,
        query_generator=query_generator,
        search_provider=_search_provider,
        ranker=ranker,
        fetcher=_fetcher,
        validator=validator,
        responder=responder,
        max_results=settings.max_results,
        cache=_cache,
    )

    ready = await is_ready_async(_ollama_client)
    logger.info(
        "SearchMesh server started",
        extra={
            "ollama_ready": ready,
            "decision_model": decision_model,
            "response_model": response_model,
            "ollama_host": settings.ollama_host,
        },
    )

    yield  # app runs here

    await client.aclose()
    if _redis_client:
        await _redis_client.aclose()
    logger.info("SearchMesh server shut down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SearchMesh",
    description="Local-first RAG search API with multi-provider fallback, semantic ranking, and observability.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Middleware — request ID
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    token = request_id_ctx.set(request_id)
    try:
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_ctx.reset(token)

@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    if settings.api_key:
        exempt_paths = {"/v1/health", "/docs", "/redoc", "/openapi.json", "/"}
        if request.url.path not in exempt_paths and not request.url.path.startswith("/static"):
            key = request.headers.get("x-api-key")
            if not key or key != settings.api_key:
                request_id = request_id_ctx.get("")
                return JSONResponse(
                    status_code=401,
                    content=ErrorResponse(
                        error="unauthorized",
                        detail="Invalid or missing X-API-Key header",
                        request_id=request_id,
                    ).model_dump(),
                )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = request_id_ctx.get("")
    logger.error(
        "Unhandled exception",
        extra={
            "path": str(request.url.path),
            "exception_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        },
    )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            detail=f"An unexpected error occurred: {type(exc).__name__}",
            request_id=request_id,
        ).model_dump(),
    )


# Helper: build SourceResult list from domain SearchResult list
# ---------------------------------------------------------------------------

def _to_source_results(results: list[SearchResult]) -> list[SourceResult]:
    return [
        SourceResult(
            url=r.url,
            title=r.title,
            snippet=r.content,
            score=r.score,
            source=r.source,
        )
        for r in results
    ]


# ---------------------------------------------------------------------------
# POST /v1/chat
# ---------------------------------------------------------------------------

from fastapi.responses import JSONResponse, StreamingResponse

@app.post("/v1/chat", tags=["pipeline"])
async def chat(request: ChatRequest):
    """Run the full pipeline: decision → query gen → search → fetch → validate → respond."""
    request_id = request_id_ctx.get("")

    if _orchestrator is None:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error="service_unavailable",
                detail="Server is not fully initialised yet",
                request_id=request_id,
            ).model_dump(),
        )

    # Synthetic session_id for M1 — real persistence comes in M3
    session_id = request.session_id or str(uuid.uuid4())
    history: list[dict] = []

    if request.stream:
        async def event_generator():
            try:
                async for chunk in _orchestrator.stream_turn(
                    user_input=request.message,
                    history=history,
                    use_web=request.use_web,
                    model=request.model,
                    max_context_chars=request.max_context_chars or settings.max_context_chars,
                ):
                    yield f"data: {chunk}\n\n"
            except Exception as exc:
                logger.error("Pipeline error during streaming", extra={"error": str(exc), "traceback": traceback.format_exc()})
                error_msg = ErrorResponse(
                    error="llm_unavailable",
                    detail="Ollama is unreachable or returned an error",
                    request_id=request_id,
                ).model_dump_json()
                yield f"data: {{\"type\": \"error\", \"data\": {error_msg}}}\n\n"
        
        return StreamingResponse(event_generator(), media_type="text/event-stream")

    try:
        result = await _orchestrator.run_turn(
            user_input=request.message,
            history=history,
            use_web=request.use_web,
            model=request.model,
            max_context_chars=request.max_context_chars or settings.max_context_chars,
        )
    except Exception as exc:
        logger.error("Pipeline error", extra={"error": str(exc), "traceback": traceback.format_exc()})
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error="llm_unavailable",
                detail="Ollama is unreachable or returned an error",
                request_id=request_id,
            ).model_dump(),
        )

    lat = result.latency
    return ChatResponse(
        response=result.assistant_text,
        session_id=session_id,
        used_web=result.context_used,
        sources=_to_source_results(result.results),
        latency_ms=LatencyBreakdown(
            decision=lat.get("decision", 0.0),
            search=lat.get("search", 0.0),
            fetch=lat.get("fetch", 0.0),
            validate_ms=lat.get("validate", 0.0),
            respond=lat.get("respond", 0.0),
            total=lat.get("total", 0.0),
        ),
        cache_hit=result.cache_hit,
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# POST /v1/search
# ---------------------------------------------------------------------------

@app.post("/v1/search", response_model=SearchResponse, tags=["pipeline"])
async def search(request: SearchRequest):
    """Run only the search step — no fetch, no LLM call, no session."""
    request_id = request_id_ctx.get("")

    if _search_provider is None:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error="service_unavailable",
                detail="Server is not fully initialised yet",
                request_id=request_id,
            ).model_dump(),
        )

    t0 = time.monotonic()
    max_results = request.max_results or 5
    cache_hit = False
    provider_used = "none"
    results = []

    # Check Cache
    if _cache:
        cache_key = _cache._search_key(request.query)
        cached_data = await _cache.get(cache_key)
        if cached_data:
            try:
                import json
                parsed = json.loads(cached_data)
                results = [
                    SearchResult(
                        title=r["title"],
                        url=r["url"],
                        content=r.get("content", r.get("snippet", "")),
                        source=r["source"],
                        score=r.get("score", 0.0),
                        snippet=r.get("snippet", "")
                    )
                    for r in parsed.get("results", [])
                ]
                provider_used = parsed.get("provider_used", "unknown")
                cache_hit = True
            except Exception as e:
                logger.warning("Failed to parse cached search results: %s", e)

    if not cache_hit:
        try:
            results, provider_used = await _search_provider.search(
                query=request.query,
                max_results=max_results,
            )
            if _cache and results:
                import json
                from dataclasses import asdict
                cache_key = _cache._search_key(request.query)
                payload = {
                    "results": [asdict(r) for r in results],
                    "provider_used": provider_used
                }
                await _cache.set(
                    cache_key,
                    json.dumps(payload),
                    settings.cache_search_ttl_seconds
                )
        except Exception as exc:
            logger.error("Search error", extra={"error": str(exc)})
            return JSONResponse(
                status_code=502,
                content=ErrorResponse(
                    error="all_providers_failed",
                    detail="All search providers failed or returned empty results",
                    request_id=request_id,
                ).model_dump(),
            )

    latency_ms = round((time.monotonic() - t0) * 1000, 2)

    if not results:
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error="all_providers_failed",
                detail="All search providers returned empty results",
                request_id=request_id,
            ).model_dump(),
        )

    # Apply deterministic ranking before returning
    ranked = rank_results(results, request.query)

    items = [
        SearchResultItem(
            url=r.url,
            title=r.title,
            snippet=r.content,
            score=r.score,
            source=r.source,
            rank=i + 1,
        )
        for i, r in enumerate(ranked[:max_results])
    ]

    return SearchResponse(
        results=items,
        provider_used=provider_used,
        query_used=request.query,
        cache_hit=cache_hit,
        latency_ms=latency_ms,
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# POST /v1/fetch
# ---------------------------------------------------------------------------

@app.post("/v1/fetch", response_model=FetchResponse, tags=["pipeline"])
async def fetch(request: FetchRequest):
    """Fetch and extract a single URL. Tries web_fetch first, falls back to Trafilatura."""
    request_id = request_id_ctx.get("")

    if _fetcher is None:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                error="service_unavailable",
                detail="Server is not fully initialised yet",
                request_id=request_id,
            ).model_dump(),
        )

    max_chars = request.max_chars or 8000
    t0 = time.monotonic()
    cache_hit = False
    text = ""
    method = "none"

    if _cache:
        cache_key = _cache._fetch_key(request.url)
        cached_data = await _cache.get(cache_key)
        if cached_data:
            try:
                import json
                parsed = json.loads(cached_data)
                text = parsed.get("text", "")
                method = parsed.get("method", "none")
                cache_hit = True
            except Exception as e:
                logger.warning("Failed to parse cached fetch response: %s", e)

    if not cache_hit:
        try:
            text, method = await _fetcher.fetch(request.url, max_chars=max_chars)
            if _cache:
                import json
                cache_key = _cache._fetch_key(request.url)
                payload = {"text": text, "method": method}
                await _cache.set(
                    cache_key,
                    json.dumps(payload),
                    settings.cache_fetch_ttl_seconds
                )
        except Exception as exc:
            logger.error("Fetch error", extra={"url": request.url, "error": str(exc)})
            return JSONResponse(
                status_code=504,
                content=ErrorResponse(
                    error="fetch_timeout",
                    detail=f"Fetch failed: {type(exc).__name__}",
                    request_id=request_id,
                ).model_dump(),
            )

    latency_ms = round((time.monotonic() - t0) * 1000, 2)

    return FetchResponse(
        url=request.url,
        text=text,
        char_count=len(text),
        method=method,
        cache_hit=cache_hit,
        success=bool(text),
        latency_ms=latency_ms,
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# GET /v1/health
# ---------------------------------------------------------------------------

@app.get("/v1/health", response_model=HealthResponse, tags=["ops"])
async def health():
    """Check readiness of all dependencies. Always returns 200 (degraded is not 5xx)."""
    ollama_ok = False
    if _ollama_client is not None:
        try:
            ollama_ok = await is_ready_async(_ollama_client)
        except Exception:
            ollama_ok = False

    redis_status = "not_configured"
    if _redis_client is not None:
        try:
            await _redis_client.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "unreachable"

    overall = "ok" if (ollama_ok and redis_status in ("ok", "not_configured")) else "degraded"
    uptime = round(time.monotonic() - _server_start_time, 1)

    return HealthResponse(
        status=overall,
        ollama=OllamaHealth(
            status="ok" if ollama_ok else "unreachable",
            host=settings.ollama_host,
            model=settings.ollama_model,
        ),
        redis=RedisHealth(
            status=redis_status,
            host=settings.redis_url or "redis://localhost:6379",
        ),
        uptime_seconds=uptime,
        version="0.1.0",
    )


# ---------------------------------------------------------------------------
# GET /v1/config
# ---------------------------------------------------------------------------

@app.get("/v1/config", response_model=ConfigResponse, tags=["ops"])
async def config():
    """Return active runtime configuration. API keys are masked."""
    return ConfigResponse(
        model=settings.ollama_model,
        ollama_host=settings.ollama_host,
        search_providers=["ollama", "serper", "duckduckgo"],
        serper_api_key="configured" if settings.serper_api_key else "not_configured",
        agent_debug=settings.agent_debug,
        session_ttl_seconds=settings.session_ttl_seconds,
        session_max_turns=settings.session_max_turns,
        cache_ttl=CacheTTL(
            search_seconds=settings.cache_search_ttl_seconds,
            fetch_seconds=settings.cache_fetch_ttl_seconds,
        ),
        timeouts=TimeoutConfig(
            search_seconds=settings.timeout_search_seconds,
            fetch_seconds=settings.timeout_fetch_seconds,
            ollama_seconds=settings.timeout_ollama_seconds,
            global_seconds=settings.timeout_global_seconds,
        ),
    )


# ---------------------------------------------------------------------------
# DELETE /v1/cache
# ---------------------------------------------------------------------------

@app.delete("/v1/cache", tags=["ops"])
async def delete_cache():
    """Clear all Redis cache entries (search and fetch keys)."""
    request_id = request_id_ctx.get("")
    deleted_count = 0
    if _cache:
        deleted_count += await _cache.delete_pattern("search:*")
        deleted_count += await _cache.delete_pattern("fetch:*")
    return {"status": "ok", "deleted_keys": deleted_count, "request_id": request_id}

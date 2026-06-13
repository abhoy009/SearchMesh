# SearchMesh — Revised Production Plan

> Status: FastAPI server with async pipeline, deterministic ranking, and 10 passing unit tests. Not yet interview-ready. This document defines what it must become and in what order.

---

## Honest Project Framing

**What this actually is:** A self-hosted, privacy-first web-augmented generation tool. It takes a user query, decides if a web search would help, searches, fetches and validates the top result, then calls a local LLM to synthesize an answer.

**What to call it in interviews:** "A multi-stage retrieval pipeline with caching, fallback handling, and observability." Not "RAG" — real RAG involves chunking, embedding, and vector similarity search. Not "semantic search" — the ranking is keyword overlap and URL heuristics, not embeddings. Honest language at SDE1 level is actually stronger than inflated labels.

**Who it's for:** Developers who want Perplexity-like functionality without sending queries to a third-party API. Privacy-conscious setups, air-gapped environments, cost-sensitive teams. That differentiation — fully local, fully private — is the story. Lead with it.

**Why build it at SDE1:** Not because it beats Perplexity. Because building it forced you to make real engineering decisions: async design, multi-tier fallback, caching strategy, session state, observability. The project is a vehicle for demonstrating those decisions. That is what you are selling.

---

## Known Architectural Limitations (Know These Cold)

| Issue | Honest Answer When Asked |
|---|---|
| Ollama as a "search provider" | Ollama generates plausible URLs from training data — it's a hallucination-prone last resort, not a real search engine. It exists as a third-tier fallback when both Serper and DuckDuckGo fail. In production I'd replace it with a second scraping source. |
| Ranking is keyword overlap, not semantic | Deterministic, testable, and fast. Semantic ranking with embeddings would be more accurate but adds a local embedding model as a dependency. Keyword overlap is the right tradeoff for a self-hosted SDE1 project. |
| Redis sessions reset on server restart | Sessions are in-memory Redis without AOF persistence configured. They fall back to stateless gracefully — the API keeps working, the user starts fresh. For a local dev tool this is acceptable; for production I'd enable Redis AOF or swap to SQLite. |
| No streaming | Current `/v1/chat` waits for the full Ollama response. Streaming is M2 in this revised plan and changes the demo dramatically. |

---

## Current State

| Done | Status |
|---|---|
| FastAPI server with async pipeline | ✅ M1 complete |
| `POST /v1/chat`, `/v1/search`, `/v1/fetch`, `/v1/health`, `/v1/config` | ✅ All five endpoints live |
| Deterministic source ranking with domain deduplication | ✅ M4 complete |
| Request-ID middleware, structured JSON error handler | ✅ |
| 10 passing unit tests (ranking + models) | ✅ |
| Shared `httpx.AsyncClient` with per-call timeouts | ✅ |
| Validator: LLM-based JSON structured output via Ollama | ✅ (was a black box in old plan — now explicit) |
| Redis cache | ❌ |
| Session memory | ❌ |
| Streaming tokens | ❌ |
| Chat UI | ❌ |
| API key auth | ❌ |
| Metrics endpoint | ❌ |
| Docker + CI | ❌ |

---

## Target Folder Structure

```
SearchMesh/
├── src/
│   ├── app/
│   │   ├── api.py              # FastAPI app + routes (exists)
│   │   ├── cli.py              # CLI shim (exists)
│   │   ├── config.py           # pydantic-settings (exists)
│   │   ├── schemas.py          # Pydantic request/response models (exists)
│   │   ├── orchestrator.py     # DefaultTurnOrchestrator (exists)
│   │   └── interfaces.py       # Protocol definitions (exists)
│   ├── services/
│   │   ├── decision_engine.py  # should_search() (exists)
│   │   ├── query_generator.py  # generate_query() (exists)
│   │   ├── search_providers.py # FallbackSearchProvider (exists)
│   │   ├── ranking.py          # score_and_rank() (exists)
│   │   ├── fetcher.py          # fetch() with fallback (exists)
│   │   ├── validator.py        # is_relevant() via Ollama JSON (exists)
│   │   ├── responder.py        # respond() (exists)
│   │   └── session.py          # NEW: SessionStore (M3)
│   ├── infra/
│   │   ├── ollama_client.py    # Ollama HTTP wrapper (exists)
│   │   ├── http.py             # Shared async HTTP client (exists)
│   │   ├── cache.py            # NEW: Redis cache layer (M2)
│   │   ├── metrics.py          # NEW: in-process counters (M5)
│   │   └── logging.py          # Structured JSON logger (exists)
├── static/
│   └── index.html              # NEW: Chat UI (M2)
├── tests/
│   ├── unit/
│   │   ├── test_ranking.py     # 8 tests, all passing (exists)
│   │   ├── test_models.py      # 2 tests, passing (exists)
│   │   ├── test_validator.py   # NEW (M4)
│   │   └── test_cache.py       # NEW (M2)
│   ├── integration/
│   │   └── test_chat_endpoint.py  # NEW (M4)
├── docs/
│   ├── architecture.md
│   └── failure_modes.md
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── .github/workflows/ci.yml
├── ollama_web_search.py        # Compatibility shim (keep)
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

---

## API Contract

All routes versioned under `/v1`. Every response returns `Content-Type: application/json`. Consistent error shape:

```json
{"error": "short_code", "detail": "Human explanation", "request_id": "uuid"}
```

### Endpoint Overview

| Method | Path | Purpose | Milestone |
|---|---|---|---|
| `POST` | `/v1/chat` | Full pipeline turn + optional streaming | M1 ✅ / stream M2 |
| `POST` | `/v1/search` | Search step only, ranked results | M1 ✅ |
| `POST` | `/v1/fetch` | Fetch and extract a single URL | M1 ✅ |
| `GET` | `/v1/health` | Dependency readiness (Ollama + Redis) | M1 ✅ / Redis M2 |
| `GET` | `/v1/config` | Active runtime config, keys masked | M1 ✅ |
| `GET` | `/v1/sessions/{id}` | Retrieve turn history | M3 |
| `DELETE` | `/v1/sessions/{id}` | Delete session from Redis | M3 |
| `GET` | `/v1/metrics` | Live pipeline counters and latency averages | M5 |
| `DELETE` | `/v1/cache` | Clear all Redis cache entries | M2 |

> **Removed:** `POST /v1/metrics/reset` — adds complexity, solved by server restart.

### Chat Request Schema (updated for streaming)

```json
{
  "message": "string",
  "session_id": "string | null",
  "use_web": true,
  "stream": false,
  "model": "string | null",
  "max_context_chars": 4000
}
```

When `stream: true`, the response is `text/event-stream` (SSE), not JSON. Each event is a token chunk. The final event is `data: [DONE]`.

---

## Validator — Explicit Specification

The validator was a black box in the old plan. Here is exactly what it does (already implemented in `src/services/validator.py`):

1. Takes `user_input` (the question) and `context` (up to 4000 chars of fetched page text).
2. Calls Ollama with a structured JSON format constraint: `{"is_relevant": boolean}`.
3. Parses the JSON response. Returns `True` only if `is_relevant` is true.
4. On any parse failure or exception, defaults to `False` (safe: skip context injection rather than inject garbage).

**In an interview:** "The validator calls the local LLM with a binary yes/no prompt. I use Ollama's structured output mode to force valid JSON, so I never have to parse free-form text. Defaults to false on failure — if relevance can't be confirmed, we skip web context injection rather than risk hallucination compounding."

This is testable by mocking the Ollama client.

---

## Milestones

Work in order. Each milestone is a prerequisite for the one after it.

---

### ✅ M1 — FastAPI Server + Async Pipeline
**DONE.** Five endpoints, shared httpx client, request-ID middleware, structured error handler, async pipeline, pydantic-settings config.

---

### ✅ M4 — Deterministic Source Ranking
**DONE.** `ranking.py` with keyword overlap + source trust + snippet length scoring. Domain deduplication. 8 unit tests passing.

---

### M2 — Streaming + Redis Cache + Chat UI + Auth
**Timeline: 3–4 days**
**This is the highest-ROI milestone for SDE1.** Four changes, all tightly related because they all touch `api.py`.

#### Why
- **Streaming** makes the demo feel like a real product. Waiting 10 seconds for a response feels broken. Token streaming makes the same wait feel fast.
- **Cache** means repeated queries skip the network entirely. Demonstrable: ask the same question twice and the second response is instant.
- **Chat UI** means you can demo to anyone, not just people willing to curl your API.
- **Auth** signals security awareness. Without it, any interviewer can reasonably ask "so anyone on your network can hit this?"

#### What to Build

**Streaming (`src/app/api.py`, `src/services/responder.py`)**

Add `stream: bool = False` to `ChatRequest`. When `True`, return a `StreamingResponse` with `media_type="text/event-stream"`:

```python
from fastapi.responses import StreamingResponse

async def _stream_pipeline(request, orchestrator):
    # Run pipeline stages up to respond
    # Then stream tokens from Ollama
    async for chunk in orchestrator.stream_turn(...):
        yield f"data: {chunk}\n\n"
    yield "data: [DONE]\n\n"

if request.stream:
    return StreamingResponse(_stream_pipeline(request, _orchestrator), media_type="text/event-stream")
```

The orchestrator needs a `stream_turn()` method that mirrors `run_turn()` but yields tokens instead of returning a string. The Ollama Python client supports `stream=True` — it returns a generator of chunks.

**Redis Cache (`src/infra/cache.py`)**

```python
class SearchMeshCache:
    def __init__(self, redis: Redis):
        self.redis = redis

    def _search_key(self, query: str) -> str:
        return f"search:{hashlib.sha256(query.encode()).hexdigest()}"

    def _fetch_key(self, url: str) -> str:
        return f"fetch:{hashlib.sha256(url.encode()).hexdigest()}"

    async def get(self, key: str) -> str | None:
        return await self.redis.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self.redis.setex(key, ttl, value)

    async def delete_pattern(self, pattern: str) -> int:
        keys = await self.redis.keys(pattern)
        if keys:
            return await self.redis.delete(*keys)
        return 0
```

- Search cache: TTL = 600s (10 min). Key = `search:{sha256(query)}`.
- Fetch cache: TTL = 1800s (30 min). Key = `fetch:{sha256(url)}`.
- Initialize a connection pool at startup, not per-request. Use `redis.asyncio`.
- Add `cache_hit: bool` to `ChatResponse` and `SearchResponse` schemas. Already in the schemas — wire it up.
- On Redis unavailable: log the error, continue without cache. Never fail a request because cache is down.

**Update `/v1/health`** to include Redis ping. Return `"unreachable"` if Redis is down — don't 500.

**Add `DELETE /v1/cache`**: calls `delete_pattern("search:*")` and `delete_pattern("fetch:*")`, returns count of deleted keys.

**HTTP Retry Logic (`src/infra/http.py`)**

Wrap outbound calls with retry + exponential backoff. Max 3 attempts, base delay 0.5s, retry only on connection errors and 5xx:

```python
async def async_get_with_retry(url: str, timeout: float, max_attempts: int = 3) -> str:
    for attempt in range(max_attempts):
        try:
            return await async_get(url, timeout=timeout)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if attempt == max_attempts - 1:
                raise
            await asyncio.sleep(0.5 * (2 ** attempt))
```

**Chat UI (`static/index.html`)**

A single HTML file served via FastAPI's `StaticFiles`. No framework. Requirements:
- Text input + send button
- Message history displayed in a chat bubble layout
- Connects to `POST /v1/chat` with `stream: true`
- Reads the SSE stream and appends tokens as they arrive (EventSource or fetch + ReadableStream)
- Shows a spinner during the pipeline stages, tokens appear as they stream
- Displays the source URLs from the final response
- Works without any build step — open the file and it runs

Mount in `api.py`:
```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

**API Key Auth (middleware in `api.py`)**

```python
EXEMPT_PATHS = {"/v1/health", "/docs", "/redoc", "/openapi.json", "/"}

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if settings.api_key and request.url.path not in EXEMPT_PATHS:
        if request.headers.get("X-API-Key") != settings.api_key:
            return JSONResponse({"error": "unauthorized", "detail": "Invalid or missing X-API-Key header"}, status_code=401)
    return await call_next(request)
```

Add `API_KEY` to `Settings` in `config.py` and `.env.example`. If not set, auth is disabled (dev default). `/v1/health` is always exempt so Docker health checks work.

**Unit Tests (`tests/unit/test_cache.py`)**

Test with a mocked Redis client:
- Cache hit: `get()` returns a value → verify the result is returned without calling the provider.
- Cache miss: `get()` returns None → verify the provider is called and result is written to cache.
- Key generation: same query always produces the same SHA256 key.
- TTL: `setex` is called with correct TTL values for search vs fetch.
- Redis down: cache failure does not propagate as an exception to the caller.

#### Exit Check
- `POST /v1/chat` with `stream: true` returns tokens one by one as an SSE stream.
- Ask the same question twice — second response has `cache_hit: true` and noticeably lower latency.
- `GET /v1/health` returns both `ollama` and `redis` status fields.
- Request without `X-API-Key` header returns 401. Request with correct key succeeds.
- Open `http://localhost:8000` in a browser — chat UI loads, streaming works.

---

### M3 — Session Memory
**Timeline: 2 days**

#### Why
Every turn is stateless. The model has no memory of what you said two messages ago. Fixing this requires Redis (already running from M2) and a session store.

#### What to Build

**`src/services/session.py`**

```python
class SessionStore:
    def __init__(self, redis: Redis, ttl: int = 3600, max_turns: int = 20):
        self.redis = redis
        self.ttl = ttl
        self.max_turns = max_turns

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def get_history(self, session_id: str) -> list[dict]:
        raw = await self.redis.get(self._key(session_id))
        return json.loads(raw) if raw else []

    async def append_turn(self, session_id: str, user: str, assistant: str, sources: list) -> None:
        history = await self.get_history(session_id)
        history.append({"role": "user", "content": user})
        history.append({"role": "assistant", "content": assistant})
        # Cap to last N messages to bound context size
        history = history[-(self.max_turns * 2):]
        await self.redis.setex(self._key(session_id), self.ttl, json.dumps(history))

    async def delete(self, session_id: str) -> bool:
        return bool(await self.redis.delete(self._key(session_id)))

    async def get_full_session(self, session_id: str) -> dict | None:
        raw = await self.redis.get(self._key(session_id))
        if not raw:
            return None
        ttl = await self.redis.ttl(self._key(session_id))
        history = json.loads(raw)
        return {"session_id": session_id, "turn_count": len(history) // 2, "ttl_seconds": ttl, "turns": history}
```

**Orchestrator changes:**
- Before calling Ollama, load history from `SessionStore`.
- Build messages: `[system_prompt] + history + [current_user_message_with_context]`.
- After getting the response, call `append_turn()`.

**Redis-down graceful degradation:**
- If `get_history()` fails: log the error, continue with empty history (stateless fallback).
- If `append_turn()` fails: log the error, return the response anyway. Memory loss is better than a failed request.

**New Endpoints:**
- `GET /v1/sessions/{session_id}` — returns turn history from `get_full_session()`. 404 if not found.
- `DELETE /v1/sessions/{session_id}` — calls `store.delete()`. 404 if session doesn't exist.

**Session ID:** Generate UUID4 server-side if `session_id` is not provided. Return it in the `ChatResponse` so the client includes it on the next turn.

**Config:** Add `SESSION_MAX_TURNS` and `SESSION_TTL_SECONDS` to settings. Already present — just wire to `SessionStore`.

#### Exit Check
1. Send `"My name is Abhoy"` with no `session_id` — note the returned `session_id`.
2. Send `"What is my name?"` with that `session_id` — model answers correctly.
3. `GET /v1/sessions/{id}` returns both turns.
4. Restart the server — session is still retrievable (Redis persisted it, app memory did not).

---

### M5 — Metrics + Observability
**Timeline: 2 days**

#### Why
You cannot defend a project in an interview with "it felt fast." You need numbers. Metrics also change how you develop — when you can see that validation is failing 40% of the time, you know what to fix.

#### What to Build

**`src/infra/metrics.py`**

In-process singleton. Thread-safe using `asyncio.Lock`. Resets on server restart (intentional — in-process is fine for a solo project).

Track:
- `requests_total`
- `search_provider_counts`: `{ollama: N, serper: N, duckduckgo: N, all_failed: N}`
- `cache_hits` / `cache_misses` for both search and fetch caches
- `fetch_method_counts`: `{web_fetch: N, trafilatura: N, search_snippets: N, failed: N}`
- `validation_pass` / `validation_fail`
- `latency_samples`: list of per-stage dicts — used to compute averages

Computed properties: `cache_hit_rate`, `validation_pass_rate`, `avg_latency_ms_per_stage`.

**Instrument the Orchestrator**

Use a context manager to track stage timing cleanly:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def track_stage(metrics: MetricsCollector, stage: str):
    t0 = time.monotonic()
    try:
        yield
    finally:
        ms = round((time.monotonic() - t0) * 1000, 2)
        await metrics.record_latency(stage, ms)
```

**`GET /v1/metrics` endpoint**

Returns the current snapshot. See response schema below.

```json
{
  "requests_total": 142,
  "cache": {
    "search_hit_rate": 0.38,
    "fetch_hit_rate": 0.52
  },
  "search_providers": {
    "serper": {"count": 80, "rate": 0.56},
    "duckduckgo": {"count": 50, "rate": 0.35},
    "ollama": {"count": 8, "rate": 0.06},
    "all_failed": {"count": 4, "rate": 0.03}
  },
  "validation": {
    "pass_rate": 0.87,
    "pass": 85,
    "fail": 13
  },
  "avg_latency_ms": {
    "decision": 112,
    "search": 724,
    "fetch": 478,
    "validate": 41,
    "respond": 1338,
    "total": 2693
  },
  "uptime_seconds": 3612,
  "sample_count": 142
}
```

**README Metrics Table**

Run 50+ queries (mix of new and repeated, with and without web search). Capture `GET /v1/metrics`. Paste the real numbers into the README. Do not estimate. The specific numbers matter less than the fact that they are real.

#### Exit Check
`GET /v1/metrics` returns valid JSON with all fields populated after 10+ requests. You can answer from memory: average end-to-end latency, cache hit rate, which provider is primary. Both questions should have actual numbers.

---

### M6 — Docker + CI
**Timeline: 2 days**

#### Why
A project that only runs on your machine is not production software. `docker-compose up` in under a minute is the SDE1 equivalent of "it's deployed."

#### What to Build

**`docker/Dockerfile`** — multi-stage build:

```dockerfile
# Stage 1: install deps
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# Stage 2: runtime only
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/ src/
COPY static/ static/
COPY ollama_web_search.py .
EXPOSE 8000
CMD ["uvicorn", "src.app.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`docker/docker-compose.yml`:**

```yaml
services:
  searchmesh:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports: ["8000:8000"]
    env_file: ../.env
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/v1/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
```

Note: Ollama runs on the host, not in Compose. Use `OLLAMA_HOST=http://host.docker.internal:11434` in `.env` for Mac/Windows. Linux: `http://host-gateway:11434`.

**`requirements-dev.txt`:**
```
pytest
pytest-asyncio
httpx
ruff
mypy
```

**Tests to add for M6:**

`tests/unit/test_validator.py`:
- Mock Ollama client returning `{"is_relevant": true}` → `is_relevant()` returns `True`.
- Mock Ollama returning `{"is_relevant": false}` → returns `False`.
- Mock Ollama returning malformed JSON → returns `False` (safe default).
- Empty context string → returns `False` without calling Ollama.

`tests/integration/test_chat_endpoint.py` — use `httpx.AsyncClient` with `app` as the transport (no real network calls). Mock Ollama client and search providers:
- Valid request with `use_web: false` → 200 with correct schema.
- Missing `message` field → 422 validation error.
- Ollama client raises exception → 503 with `llm_unavailable` error code.
- Request without API key when `API_KEY` is set → 401.

**`.github/workflows/ci.yml`:**

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: ruff check src/ tests/
      - run: pytest tests/unit/ tests/integration/ -v
```

> mypy is omitted from CI for now — run it locally but don't block CI on it until the codebase is more settled.

#### Exit Check
`docker-compose up` starts both services without errors. `curl http://localhost:8000/v1/health` returns `{"redis": "ok", "ollama": "..."}` from inside Docker. Push to GitHub — CI runs and goes green. README shows the CI badge.

---

### M7 — Load Testing (Lower Priority)
**Timeline: Do last, only if M2–M6 are solid**

Locust load test with 10 and 20 concurrent users. The bottleneck will almost certainly be Ollama inference speed — document this honestly. "The bottleneck is local model inference, which is a hardware constraint. At 20 concurrent users the pipeline queues behind Ollama. The fix at scale would be a model serving layer like vLLM."

Add a `docs/failure_modes.md` regardless of whether load testing is done. It covers: Ollama unreachable, Redis unreachable, all search providers fail, rate limit hit, fetch fails for the chosen URL. The failure modes are already mostly handled in code — the doc is just making that explicit.

---

## Ranking Algorithm Reference

```python
def score_result(result: SearchResult, query: str) -> float:
    score = 0.0

    # Keyword overlap (weight: 0.4)
    query_tokens = set(query.lower().split())
    result_tokens = set((result.title + " " + result.content).lower().split())
    overlap = len(query_tokens & result_tokens) / max(len(query_tokens), 1)
    score += overlap * 0.4

    # Source trust (weight: 0.3)
    trust = {"serper": 1.0, "ollama": 0.8, "duckduckgo": 0.6}
    score += trust.get(result.source, 0.5) * 0.3

    # Penalize social/forum domains
    penalize = ["reddit.com", "quora.com", "twitter.com", "facebook.com", "x.com"]
    if any(d in result.url for d in penalize):
        score -= 0.2

    # Snippet length signal (weight: 0.3)
    score += min(len(result.content) / 500, 1.0) * 0.3

    return round(max(score, 0.0), 4)
```

Implemented and tested. Do not change the weights until M5 gives you data showing they need adjustment.

---

## README Must-Haves (After M5)

1. Architecture diagram (Mermaid) matching the actual code
2. Honest project description: "self-hosted web-augmented generation, not RAG"
3. Metrics table with real numbers from real runs
4. One-command setup: `docker-compose up`
5. Environment variables table (with `.env.example` as reference)
6. CI badge
7. Demo GIF of the chat UI with streaming — record this with a screen capture tool

---

## SDE1 Interview Signal

| What They're Testing | Where This Project Shows It |
|---|---|
| Async/await design | Entire async pipeline, shared httpx client |
| API design | Versioned REST, typed schemas, consistent error shape |
| Caching strategy | Redis search + fetch cache with SHA256 keys and TTL |
| Fallback handling | 3-tier search fallback, validator skip on failure, stateless session fallback |
| Observability | Per-stage latency tracking, metrics endpoint |
| Security awareness | API key middleware, keys masked in `/v1/config` |
| Testing discipline | Unit tests (ranking, validator, cache), integration tests with mocked deps |
| Deployment | Docker Compose + CI |
| Communication | Can explain every decision clearly and honestly, including limitations |

---

## What NOT to Claim

- Do not say **"RAG"** — you're doing web-augmented generation
- Do not say **"semantic search"** — the ranking is keyword overlap
- Do not say **"distributed"** — it's a single server
- Do not say **"real-time"** — you have no latency SLAs
- Do not say **"production-ready"** before M6 is done

Honest language is: "I built a multi-stage retrieval pipeline with Redis caching, graceful fallback handling, streaming token output, and per-stage latency observability." That is accurate and strong at SDE1.
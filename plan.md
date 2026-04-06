# SearchMesh — Production Plan

> Status: CLI script with good internal structure. Not yet a backend service. Not yet resume-worthy.
> This document defines what it must become, why, and exactly how.

---

## Current State (honest assessment)

| What exists | What it means |
|---|---|
| CLI-only entrypoint | Cannot be called from anything except a terminal |
| 3-tier search fallback | Good idea, no metrics to prove it works |
| Trafilatura fetch fallback | Correct instinct, zero observability |
| Context validation before injection | Right pattern, untestable black box |
| `src/` layer separation | Structural skeleton, not a real service boundary |
| No FastAPI | Cannot be deployed, integrated, or load-tested |
| No Redis | Every request does full work even for repeated queries |
| No session memory | Each turn is stateless, context resets every time |
| No metrics | Cannot be defended in an interview with numbers |
| No Docker | Cannot run anywhere except your machine |
| No CI | No automated test signal on PRs |

The code architecture is clean. The system is not production software.

---

## Target state

**SearchMesh: A local-first RAG search API with multi-provider fallback, semantic ranking, session memory, and operational observability.**

That sentence is the north star. Every milestone below serves it.

---

## Folder structure (target)

```
SearchMesh/
├── src/
│   ├── app/
│   │   ├── api.py              # FastAPI app + route registration
│   │   ├── cli.py              # CLI shim (keep for local dev)
│   │   ├── config.py           # Settings via pydantic-settings
│   │   ├── schemas.py          # Request/response Pydantic models
│   │   └── orchestrator.py     # DefaultTurnOrchestrator (exists, refactor)
│   ├── services/
│   │   ├── decision.py         # should_search()
│   │   ├── query_gen.py        # generate_query()
│   │   ├── search.py           # FallbackSearchProvider
│   │   ├── ranking.py          # score_and_rank() — deterministic
│   │   ├── fetcher.py          # fetch() with fallback
│   │   ├── validator.py        # is_relevant()
│   │   ├── responder.py        # stream()
│   │   └── session.py          # NEW: session read/write
│   ├── infra/
│   │   ├── ollama_client.py    # Ollama HTTP wrapper
│   │   ├── http.py             # Shared async HTTP client + retry logic
│   │   ├── cache.py            # NEW: Redis cache layer
│   │   ├── metrics.py          # NEW: in-process counters + timers
│   │   └── logging.py          # Structured JSON logger
├── tests/
│   ├── unit/
│   │   ├── test_ranking.py
│   │   ├── test_validator.py
│   │   └── test_cache.py
│   ├── integration/
│   │   ├── test_chat_endpoint.py
│   │   └── test_search_endpoint.py
│   └── load/
│       └── locustfile.py       # Load test script
├── docs/
│   ├── architecture.md
│   ├── api_reference.md
│   └── metrics_reference.md
├── .github/
│   └── workflows/
│       └── ci.yml              # Lint + test on every push
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml      # App + Redis
├── ollama_web_search.py        # Compatibility shim (keep)
├── requirements.txt
├── requirements-dev.txt        # pytest, locust, ruff, mypy
├── .env.example
└── README.md                   # Must have architecture diagram + numbers
```

---

## Endpoints

All routes are versioned under `/v1`. Every response — including errors — returns `Content-Type: application/json`. Every request that mutates state or triggers a pipeline call (`POST`, `DELETE`) requires `Content-Type: application/json` in the request headers.

Error shape is consistent across all endpoints:
```json
{
  "error": "short_error_code",
  "detail": "Human-readable explanation",
  "request_id": "uuid"
}
```

---

### Overview

| Method | Path | Purpose | Added in |
|---|---|---|---|
| `POST` | `/v1/chat` | Run a full pipeline turn — decide, search, fetch, answer | M1 |
| `POST` | `/v1/search` | Run only the search step and return ranked results | M1 |
| `POST` | `/v1/fetch` | Fetch and extract a single URL | M1 |
| `GET` | `/v1/health` | Check readiness of all dependencies | M1 |
| `GET` | `/v1/sessions/{session_id}` | Retrieve turn history for a session | M3 |
| `DELETE` | `/v1/sessions/{session_id}` | Delete a session and its history from Redis | M3 |
| `GET` | `/v1/metrics` | Live snapshot of pipeline counters and latency averages | M5 |
| `POST` | `/v1/metrics/reset` | Reset all in-process counters (dev only) | M5 |
| `DELETE` | `/v1/cache` | Clear all cached search and fetch entries from Redis | M2 |
| `GET` | `/v1/config` | Return active runtime configuration | M1 |

---

### POST /v1/chat

The main entrypoint. Runs the full pipeline: decision → query generation → search → fetch → validate → respond. Returns the assistant's response along with metadata about what happened inside the pipeline.

**When to use:** Any time you want the assistant to answer a question, with or without web augmentation.

**Request**
```json
{
  "message": "string",
  "session_id": "string | null",
  "use_web": "bool",
  "model": "string | null",
  "max_context_chars": "int | null"
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `message` | yes | — | The user's input text |
| `session_id` | no | null | If provided, history is loaded and the turn is appended. If null, a new session is created and returned. |
| `use_web` | no | `true` | If false, skips the decision step and answers from model knowledge only |
| `model` | no | `OLLAMA_MODEL` env value | Override the model for this request |
| `max_context_chars` | no | `4000` | Max characters of fetched web content to inject into the prompt |

**Response — 200 OK**
```json
{
  "response": "string",
  "session_id": "string",
  "used_web": "bool",
  "sources": [
    {
      "url": "string",
      "title": "string",
      "snippet": "string",
      "score": "float",
      "source": "ollama | serper | duckduckgo"
    }
  ],
  "latency_ms": {
    "decision": 112,
    "search": 843,
    "fetch": 421,
    "validate": 38,
    "respond": 1204,
    "total": 2618
  },
  "cache_hit": "bool",
  "request_id": "string"
}
```

**Error responses**

| Status | `error` code | Cause |
|---|---|---|
| 422 | `validation_error` | Missing or malformed request fields |
| 503 | `llm_unavailable` | Ollama is unreachable or returned a non-200 |
| 504 | `request_timeout` | Pipeline did not complete within 60s global timeout |
| 500 | `internal_error` | Unexpected error — logged server-side with `request_id` |

**Example**
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the CAP theorem?",
    "use_web": false
  }'
```

---

### POST /v1/search

Runs only the search step — no fetch, no LLM call, no session involvement. Returns ranked results from whichever provider(s) were used, with scores attached.

**When to use:** Debugging search quality, testing the ranking algorithm independently, building a search-only frontend, or verifying fallback behavior.

**Request**
```json
{
  "query": "string",
  "max_results": "int | null",
  "sources": ["ollama", "serper", "duckduckgo"] 
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `query` | yes | — | The search query string |
| `max_results` | no | `5` | Maximum number of results to return (capped at 10) |
| `sources` | no | all three | Restrict which providers are tried. Useful for testing a specific provider. |

**Response — 200 OK**
```json
{
  "results": [
    {
      "url": "string",
      "title": "string",
      "snippet": "string",
      "score": "float",
      "source": "ollama | serper | duckduckgo",
      "rank": "int"
    }
  ],
  "provider_used": "string",
  "query_used": "string",
  "cache_hit": "bool",
  "latency_ms": 342,
  "request_id": "string"
}
```

`query_used` is the query as actually sent to the provider — useful for debugging query rewriting.
`provider_used` is the provider that returned results (the first one that succeeded in the fallback chain).
`score` is the deterministic ranking score from `ranking.py`. Higher is better. Range: 0.0–1.0.

**Error responses**

| Status | `error` code | Cause |
|---|---|---|
| 422 | `validation_error` | Missing query or invalid field type |
| 502 | `all_providers_failed` | All three search providers failed or returned empty results |
| 504 | `search_timeout` | Search exceeded 5s timeout across all providers |

**Example**
```bash
curl -X POST http://localhost:8000/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "redis vs postgres for session storage",
    "max_results": 5
  }'
```

---

### POST /v1/fetch

Fetches a single URL and returns extracted plain text. Tries `web_fetch` first, falls back to Trafilatura if that fails or returns empty content.

**When to use:** Debugging fetch quality for a specific URL, verifying that the extraction pipeline works on a particular domain, testing content before feeding it to the validator.

**Request**
```json
{
  "url": "string",
  "max_chars": "int | null"
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `url` | yes | — | The URL to fetch. Must be a valid `https://` URL. |
| `max_chars` | no | `8000` | Truncate extracted text to this many characters |

**Response — 200 OK**
```json
{
  "url": "string",
  "text": "string",
  "char_count": 4218,
  "method": "web_fetch | trafilatura",
  "cache_hit": "bool",
  "success": "bool",
  "latency_ms": 521,
  "request_id": "string"
}
```

`success: false` with `text: ""` means both fetch methods failed but did not error — the URL was unreachable or returned no extractable content. This is a 200, not a 4xx/5xx, because the fetch pipeline ran correctly; it just got nothing back.

**Error responses**

| Status | `error` code | Cause |
|---|---|---|
| 422 | `validation_error` | Invalid URL format |
| 504 | `fetch_timeout` | Fetch exceeded 8s timeout |

**Example**
```bash
curl -X POST http://localhost:8000/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://redis.io/docs/manual/persistence/",
    "max_chars": 5000
  }'
```

---

### GET /v1/health

Returns the current readiness state of every external dependency the service depends on. Intended for Docker health checks, uptime monitoring, and pre-flight verification.

**When to use:** Before running load tests, in Docker Compose `healthcheck`, in any startup script.

**Request:** No body, no query params.

**Response — 200 OK** (even if some dependencies are down — health checks should not throw 5xx)
```json
{
  "status": "ok | degraded",
  "ollama": {
    "status": "ok | unreachable",
    "host": "http://localhost:11434",
    "model": "qwen2.5:0.5b"
  },
  "redis": {
    "status": "ok | unreachable",
    "host": "redis://localhost:6379"
  },
  "serper": {
    "status": "configured | not_configured"
  },
  "uptime_seconds": 3612,
  "version": "0.1.0"
}
```

`status` at the top level is `"ok"` only if all required dependencies (Ollama, Redis) are reachable. `"degraded"` if any required dependency is down. Serper being unconfigured does not affect `status` — it is optional.

**Example**
```bash
curl http://localhost:8000/v1/health
```

---

### GET /v1/sessions/{session_id}

Returns the full turn history stored for a given session. Useful for debugging, for verifying that memory is working correctly, and for building session-aware frontends.

**Path parameter:** `session_id` — the UUID returned by a prior `/v1/chat` call.

**Response — 200 OK**
```json
{
  "session_id": "string",
  "turn_count": 4,
  "ttl_seconds": 2847,
  "turns": [
    {
      "turn": 1,
      "timestamp": "2026-04-01T10:23:11Z",
      "user": "string",
      "assistant": "string",
      "used_web": "bool",
      "sources": [
        {
          "url": "string",
          "title": "string",
          "score": "float"
        }
      ]
    }
  ]
}
```

`ttl_seconds` is the time remaining before Redis expires this session. Resets on every new turn (TTL is refreshed on each `append_turn` write).

**Error responses**

| Status | `error` code | Cause |
|---|---|---|
| 404 | `session_not_found` | No session exists for this ID (expired or never created) |
| 503 | `redis_unavailable` | Redis is unreachable |

**Example**
```bash
curl http://localhost:8000/v1/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

---

### DELETE /v1/sessions/{session_id}

Deletes a session and all its stored history from Redis immediately, without waiting for TTL expiry.

**When to use:** Explicitly ending a conversation, privacy-motivated clearing, or resetting state during testing.

**Response — 200 OK**
```json
{
  "deleted": true,
  "session_id": "string"
}
```

**Error responses**

| Status | `error` code | Cause |
|---|---|---|
| 404 | `session_not_found` | Session does not exist or already expired |
| 503 | `redis_unavailable` | Redis is unreachable |

**Example**
```bash
curl -X DELETE http://localhost:8000/v1/sessions/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

---

### GET /v1/metrics

Returns a live snapshot of all in-process pipeline counters and computed rates. Resets to zero on server restart (in-process storage, not persisted).

**When to use:** After running a batch of queries to evaluate system behavior, in load test post-analysis, or for README documentation.

**Response — 200 OK**
```json
{
  "requests_total": 142,
  "web_augmented_total": 98,
  "cache": {
    "search_hit_rate": 0.38,
    "fetch_hit_rate": 0.52,
    "search_hits": 54,
    "search_misses": 88,
    "fetch_hits": 71,
    "fetch_misses": 65
  },
  "search_providers": {
    "ollama": { "count": 78, "rate": 0.80 },
    "serper": { "count": 12, "rate": 0.12 },
    "duckduckgo": { "count": 8, "rate": 0.08 },
    "all_failed": { "count": 0, "rate": 0.00 }
  },
  "fetch_methods": {
    "web_fetch": { "count": 81, "rate": 0.83 },
    "trafilatura": { "count": 9, "rate": 0.09 },
    "failed": { "count": 8, "rate": 0.08 }
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
  "p95_latency_ms": {
    "total": 5820
  },
  "uptime_seconds": 3612,
  "sample_count": 142
}
```

**Example**
```bash
curl http://localhost:8000/v1/metrics
```

---

### POST /v1/metrics/reset

Resets all in-process counters to zero. Intended for development and benchmarking only — run this before a controlled test batch to get a clean baseline.

**⚠ Do not expose this in a production deployment without authentication.**

**Request:** No body required.

**Response — 200 OK**
```json
{
  "reset": true,
  "timestamp": "2026-04-01T10:23:11Z"
}
```

**Example**
```bash
curl -X POST http://localhost:8000/v1/metrics/reset
```

---

### DELETE /v1/cache

Clears all cached entries from Redis — both search result cache and fetch content cache. Does not affect sessions.

**When to use:** Force-refreshing stale cached data during development, or before a controlled benchmark run where you want to measure cold-path latency.

**Response — 200 OK**
```json
{
  "deleted_keys": 47,
  "cleared": true
}
```

**Error responses**

| Status | `error` code | Cause |
|---|---|---|
| 503 | `redis_unavailable` | Redis is unreachable |

**Example**
```bash
curl -X DELETE http://localhost:8000/v1/cache
```

---

### GET /v1/config

Returns the active runtime configuration — which model is loaded, which search providers are enabled, what the fallback order is, and what feature flags are set. Read-only. Does not expose secrets (API keys are shown as `"configured"` or `"not_configured"`, never their values).

**When to use:** Verifying your `.env` was loaded correctly, debugging model selection, confirming provider configuration before running tests.

**Response — 200 OK**
```json
{
  "model": "qwen2.5:0.5b",
  "ollama_host": "http://localhost:11434",
  "search_providers": ["ollama", "serper", "duckduckgo"],
  "serper_api_key": "configured | not_configured",
  "agent_debug": false,
  "session_ttl_seconds": 3600,
  "session_max_turns": 20,
  "cache_ttl": {
    "search_seconds": 600,
    "fetch_seconds": 1800
  },
  "timeouts": {
    "search_seconds": 5,
    "fetch_seconds": 8,
    "ollama_seconds": 30,
    "global_seconds": 60
  }
}
```

**Example**
```bash
curl http://localhost:8000/v1/config
```

---

## Ranking algorithm (stop using "best result agent" as a placeholder)

`ranking.py` must implement a deterministic score. No LLM calls here.

```python
def score_result(result: SearchResult, query: str) -> float:
    score = 0.0

    # Keyword overlap between query tokens and title/snippet
    query_tokens = set(query.lower().split())
    result_tokens = set((result.title + " " + result.snippet).lower().split())
    overlap = len(query_tokens & result_tokens) / max(len(query_tokens), 1)
    score += overlap * 0.4

    # Source trust weight
    trust = {"serper": 1.0, "ollama": 0.8, "duckduckgo": 0.6}
    score += trust.get(result.source, 0.5) * 0.3

    # URL heuristics: prefer non-social, non-forum domains
    penalize = ["reddit.com", "quora.com", "twitter.com", "facebook.com"]
    if any(d in result.url for d in penalize):
        score -= 0.2

    # Prefer results with longer snippets (more content signal)
    score += min(len(result.snippet) / 500, 1.0) * 0.3

    return round(score, 4)
```

This is explainable in an interview. "We scored results on query overlap, source trust, and content signal" is a real answer.

---

## Session memory design

Problem: every turn resets. The LLM has no history.

Solution: Redis-backed session store with TTL.

```python
# infra/cache.py
class SessionStore:
    def __init__(self, redis: Redis, ttl: int = 3600):
        self.redis = redis
        self.ttl = ttl

    async def get_history(self, session_id: str) -> list[dict]:
        raw = await self.redis.get(f"session:{session_id}")
        return json.loads(raw) if raw else []

    async def append_turn(self, session_id: str, user: str, assistant: str):
        history = await self.get_history(session_id)
        history.append({"role": "user", "content": user})
        history.append({"role": "assistant", "content": assistant})
        # Keep last 20 turns to bound context size
        history = history[-20:]
        await self.redis.setex(f"session:{session_id}", self.ttl, json.dumps(history))
```

The orchestrator injects `history` into the Ollama prompt. That is persistent context. That is the thing you keep saying you want to solve.

---

## Milestones

Each milestone has four subsections: **Why** (the problem it solves), **What to build** (the concrete work), **Key decisions** (choices you'll face and how to make them), and **Exit check** (how you know it's actually done).

Work in order. Do not start M3 until M2 is solid. Each milestone is a prerequisite for the one after it.

---

### ✅ [DONE] M1 — FastAPI server + async pipeline
**Timeline: Week 1**

#### Why
Right now the entire system can only be invoked from a terminal. That means it cannot be called by another service, cannot be tested with HTTP clients, cannot be deployed to any environment, and cannot be load-tested. Until there is an HTTP interface, this project is a script — not a service. Everything else in this roadmap depends on M1 being done first, because all subsequent milestones (caching, sessions, metrics, CI) are built on top of the API layer.

The secondary problem is that the current pipeline uses synchronous calls. When a search request takes 2 seconds and a fetch takes another 2 seconds, everything blocks. Moving to `async def` + `await` throughout the service layer means the server can handle multiple requests without waiting on one slow network call before starting the next.

#### What to build

**API layer (`src/app/`)**
- `api.py` — Create the FastAPI application instance. Register all routes. Add startup/shutdown event handlers that check Ollama readiness and log server boot.
- `schemas.py` — Define all Pydantic request and response models. Every endpoint must have typed inputs and typed outputs. No bare dicts in route handlers. Use the schemas defined in the API contract section above as the source of truth.
- `config.py` — Move all env var reads into a single `Settings` class using `pydantic-settings`. No scattered `os.getenv()` calls across files. One config object, injected where needed.

**Async conversion (`src/services/` and `src/infra/`)**
- Convert every service method to `async def`. Anywhere the code calls Ollama, makes an HTTP request, or reads/writes to storage, it must `await`.
- The existing `DefaultTurnOrchestrator.run_turn()` becomes an `async` method that the `/chat` route calls with `await`.
- Use `httpx.AsyncClient` as the shared HTTP client in `infra/http.py`. Replace any `requests` library usage.

**Endpoints to ship**
- `POST /v1/chat` — main entrypoint. Accepts a message, runs the full pipeline, returns response + metadata.
- `POST /v1/search` — exposes the search step independently. Useful for debugging and for future consumers.
- `POST /v1/fetch` — exposes the fetch step independently. Same reasoning.
- `GET /v1/health` — pings Ollama and (eventually) Redis, returns status of each dependency. This is the first thing ops tooling and Docker health checks will call.

**Error handling**
All unhandled exceptions must be caught at the route level and returned as structured JSON with a consistent shape: `{"error": "...", "detail": "...", "request_id": "..."}`. Stack traces must never reach the client. Log the full traceback server-side.

#### Key decisions

**FastAPI vs Flask:** FastAPI is the right call here because it has native async support, automatic OpenAPI docs at `/docs`, and Pydantic integration baked in. Flask with async bolted on is messier and less idiomatic for this stack.

**Where to put the orchestrator call:** The route handler in `api.py` should be thin — validate input, call orchestrator, return output. No business logic in route handlers. The orchestrator owns the pipeline.

**Request IDs:** Add a middleware that generates a UUID per request and attaches it to the response headers and all log lines for that request. This is a one-time addition that pays dividends forever when debugging.

#### Exit check
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what is redis"}'
```
Returns a JSON response with `response`, `session_id`, `used_web`, `latency_ms`, and `cache_hit` fields. No stack traces. `GET /v1/health` returns `{"ollama": "ok"}`.

---

### M2 — Redis cache + reliability hardening
**Timeline: Week 1–2**

#### Why
The current system does full work on every request. If you ask the same question twice, it re-runs the search, re-fetches the page, re-validates context, and re-calls Ollama. This is wasteful and slow. For a retrieval assistant, a significant fraction of queries will be semantically identical or use the same source URLs — caching directly reduces latency and provider API calls.

The second problem is brittleness. The current HTTP calls have no timeouts and no retries. A single slow response from DuckDuckGo or a transient Ollama hiccup causes the entire request to hang or fail hard. In a real backend service, the assumption is that external calls will fail intermittently — the code must handle that by default, not as an afterthought.

#### What to build

**Cache layer (`src/infra/cache.py`)**
- Use `aioredis` (async Redis client). Initialize a connection pool at server startup, not per-request.
- **Search cache:** key = `search:{sha256(query)}`, value = serialized result list, TTL = 10 minutes. Before calling any search provider, check this key. On miss, run the search and write the result.
- **Fetch cache:** key = `fetch:{sha256(url)}`, value = extracted page text, TTL = 30 minutes. Before fetching a URL, check this key. On miss, fetch and write.
- Expose `async def get(key)`, `async def set(key, value, ttl)`, and `async def delete(key)` — nothing more. The cache layer should be ignorant of what is being cached.
- Add `cache_hit: bool` to the chat response schema so callers can see when they hit cache.

**Retry and timeout logic (`src/infra/http.py`)**
- Wrap all outbound HTTP calls in a retry decorator: max 3 attempts, exponential backoff starting at 0.5s, retry only on connection errors and 5xx responses, not on 4xx.
- Per-call timeouts: search calls timeout at 5 seconds, fetch calls at 8 seconds, Ollama calls at 30 seconds. These are not optional — every outbound call must have a timeout ceiling.
- When a call exhausts retries, raise a typed exception (`SearchProviderError`, `FetchError`) that the orchestrator can catch and route to the fallback. Do not swallow errors silently.

**Structured logging**
- Every cache hit and miss should produce a log line with: `event`, `key_type` (search|fetch), `hit` (bool), `request_id`, `latency_ms`.
- This is what makes the cache observable before you have a full metrics system.

**Update `/v1/health`**
- Add a Redis ping to the health check. Return `{"ollama": "ok", "redis": "ok"}` or `"unreachable"` for each.

#### Key decisions

**aioredis vs redis-py with asyncio:** Use `redis.asyncio` (the async interface from the `redis` package, which replaces the old `aioredis` package). It is maintained by the Redis core team and better supported.

**Cache key design:** Use SHA256 of the query/URL string as the key suffix. Do not use the raw query as a Redis key — it can contain spaces, special characters, and would make key inspection messy. SHA256 is deterministic and collision-resistant enough for this use case.

**What not to cache:** Do not cache Ollama responses. The answer depends on session history and context, which changes per user. Only cache the search results and fetched content, which are stateless and URL-deterministic.

**TTL values:** 10 minutes for search results is aggressive but appropriate — web search results go stale quickly. 30 minutes for fetched page content is reasonable since page content changes less frequently than search rankings. Adjust based on your actual query patterns once M5 gives you data.

#### Exit check
Send the same query twice within the TTL window. Second response `latency_ms.search` should drop by >60% compared to the first. Response includes `"cache_hit": true`. `GET /v1/health` returns both `ollama` and `redis` statuses. Kill the search provider mid-request — the system should retry, fall back to the next provider, and still return an answer.

---

### M3 — Session memory
**Timeline: Week 2**

#### Why
This is the problem you've identified as the most painful part of working with the current system: every conversation turn is stateless. The model has no memory of what you said two messages ago. This makes multi-turn conversations useless because you have to re-state context on every message.

The fix is not complicated in concept — you store conversation history per session and inject it into every Ollama prompt as the `messages` array. The implementation lives in Redis (already running from M2), so there is no new infrastructure to add.

#### What to build

**SessionStore (`src/infra/cache.py` or `src/services/session.py`)**

Implement a `SessionStore` class as described in the session memory design section above. The key behaviors are:
- Auto-generate a `session_id` (UUID4) if the request does not include one. Return it in the response so the client can include it on the next turn.
- Store history as a JSON list of `{"role": "user"|"assistant", "content": "..."}` dicts — the exact format Ollama's chat API expects.
- Cap history at the last 20 messages (10 turns) before writing. This is important: without truncation, the prompt grows unbounded and will eventually exceed the model's context window or cause slow responses.
- Set a TTL of 1 hour on every write so inactive sessions expire automatically. Refresh the TTL on every append — the clock resets on each new message.
- Include retrieved sources in the stored turn so `GET /sessions/{id}` is useful for debugging.

**Orchestrator changes**
- Before calling Ollama, load session history from `SessionStore`.
- Build the Ollama `messages` array: `[system_prompt] + history + [current_user_message_with_context]`.
- After getting the response, append the user message and assistant response to the session store.

**Expose `GET /v1/sessions/{session_id}`**
- Returns the full turn history for a session in the format defined in the API contract.
- Useful for: debugging why the model said something, verifying memory is working, and showing in demos.

#### Key decisions

**Where to inject sources into the prompt:** Retrieved web context should be injected as part of the current user message, not as a separate system message. Format: append `\n\n[Context from web]\n{context_text}` to the user message before storing and sending. This keeps the history clean while making the context available to the model.

**What happens when Redis is down:** The orchestrator must handle `SessionStore` failures gracefully. If reading history fails, continue with no history (stateless fallback). If writing fails, log the error but do not fail the request. Memory loss is better than a broken response.

**Session ID generation:** Generate on the server, not the client. The client can optionally supply a `session_id` to resume a session. If not supplied, generate and return one. This makes the API predictable.

**Context window management:** The 20-message cap is a starting point. If you are using a model with a small context window (e.g., `qwen2.5:0.5b`), you may need to drop to 10 messages. Add a configurable `SESSION_MAX_TURNS` env variable so this can be tuned without code changes.

#### Exit check
Start a conversation with two turns:
1. Turn 1: `"My name is Abhoy"`
2. Turn 2: `"What is my name?"` — model should answer correctly.

Verify via `GET /v1/sessions/{session_id}` that both turns are stored with timestamps and sources. Restart the server — session should still be retrievable (Redis persists, app memory does not).

---

### ✅ [DONE] M4 — Deterministic source ranking
**Timeline: Week 2–3**

#### Why
The current system uses an LLM call or vague heuristic to pick the "best" search result. This is a problem for two reasons. First, it is non-deterministic and untestable — you cannot write a unit test for "the model thinks this URL is best." Second, it is slow — an extra LLM call just to pick a URL adds latency to every web-augmented turn.

Source ranking must be a deterministic function: given a list of results and a query, it returns a scored, sorted list. The scoring logic is explainable, testable, and fast. See the ranking algorithm section above for the exact implementation.

#### What to build

**`src/services/ranking.py`**
- Implement `score_result(result: SearchResult, query: str) -> float` as specified in the ranking algorithm section.
- Implement `rank_results(results: list[SearchResult], query: str) -> list[SearchResult]` — applies `score_result` to each result, sorts descending by score, strips duplicates (same domain within the same result set, keep the highest-scored one).
- Add `score: float` to the `SearchResult` schema in `schemas.py`.
- The orchestrator calls `rank_results()` after search, takes the top-1 result for fetching. The rest of the ranked list is returned in the `/chat` and `/search` response `sources` field.

**Remove the "best result" LLM call**
- Whatever prompt or LLM call currently picks the best URL gets deleted. `rank_results()` replaces it entirely.
- This shaves one Ollama call per web-augmented turn. That is significant latency reduction.

**Duplicate suppression**
- Within a single result set, if two results point to the same domain (e.g., two `stackoverflow.com` links), keep only the one with the higher score.
- This avoids injecting redundant content from the same source.

**Unit tests (`tests/unit/test_ranking.py`)**
- Test that a result with higher keyword overlap scores higher than one with less.
- Test that a Serper result scores higher than a DuckDuckGo result for equal content.
- Test that a Reddit URL gets penalized correctly.
- Test that duplicate domains are suppressed.
- Test that an empty result list returns an empty ranked list without errors.
- Test that the ranking is stable (same input always produces same output).
- Minimum 8 test cases. These should run without any network calls — use mocked `SearchResult` objects.

#### Key decisions

**Why not use embeddings for ranking:** Embeddings-based semantic similarity would be more accurate but requires either a local embedding model (extra setup, extra latency) or an API call. The keyword overlap + source trust + snippet length heuristic is good enough for this use case, is explainable, and has zero external dependencies. Do not over-engineer ranking at this stage.

**Scoring weights:** The weights in the algorithm (0.4 / 0.3 / 0.3) are starting values. Once M5 gives you data on validation pass/fail rates, you can adjust these to improve context quality. For now, hardcode them — do not make them configurable until you have evidence they need tuning.

**What to do when all results score below a threshold:** If the top-ranked result scores below 0.2, log a warning and proceed anyway. Do not skip context injection based on score alone — the validator already handles that. Ranking and validation are two separate concerns.

#### Exit check
`POST /v1/search?query=redis+vs+postgres` returns results sorted by `score` descending, all scores visible in the response. Running the same query produces the same ordering every time. Unit tests for `ranking.py` pass with `pytest tests/unit/test_ranking.py`. The chat pipeline no longer makes an extra LLM call to pick a URL — visible in debug logs.

---

### M5 — Metrics + observability
**Timeline: Week 3**

#### Why
Without metrics, you cannot answer basic questions about your own system: How fast is it? Where does time go? How often does search fail? How effective is the cache? These are questions every interviewer at an SDE2 level will ask if you list this project on your resume. "I don't know, it felt fast" is not an answer.

Observability also changes how you develop — when you can see that validation is failing 30% of the time, you know to fix the validator. When you can see that fetch is taking 3x longer than search, you know where to optimize. Without metrics, you are flying blind.

#### What to build

**`src/infra/metrics.py`**
- Implement a `MetricsCollector` as an in-process singleton using Python's `threading.Lock` or `asyncio.Lock` to safely update counters from concurrent requests.
- Track at minimum:
  - `requests_total` — total chat requests processed
  - `search_provider_counts` — dict of `{provider: count}` for which provider was actually used
  - `cache_hits` and `cache_misses` — for both search and fetch caches
  - `fetch_method_counts` — `{web_fetch: N, trafilatura: N}`
  - `validation_pass` and `validation_fail` — how often the validator rejects fetched context
  - `latency_samples` — list of per-stage latency dicts, used to compute averages
- Expose computed properties: `cache_hit_rate`, `validation_pass_rate`, `avg_latency_ms_per_stage`, `search_fallback_rate`.

**Pipeline instrumentation**
- Wrap each stage in the orchestrator with `time.monotonic()` start/end timestamps. Add the delta to `latency_samples` for that stage.
- This should be done with a context manager or decorator to avoid cluttering orchestrator code with timing boilerplate:

```python
async with track_stage(metrics, "search"):
    results = await search_provider.search(query)
```

**`GET /v1/metrics` endpoint**
- Returns the current snapshot of all counters and computed rates as JSON.
- See the API contract section for the exact response schema.

**Optional: Prometheus endpoint**
- Install `prometheus-fastapi-instrumentator` and expose `/metrics` in Prometheus text format.
- This is a one-line addition once `MetricsCollector` exists and lets you plug in Grafana later if you want to make a dashboard for the README.

**README metrics table**
- Run 100 queries (mix of new and repeated, mix of simple and web-augmented).
- Capture the `GET /v1/metrics` output.
- Paste the numbers into the README as a table.
- These are real numbers from real runs. Do not estimate.

#### Key decisions

**In-process vs external metrics store:** For a solo project, in-process counters that reset on server restart are fine. The alternative (writing metrics to Redis or a time-series DB) is overkill here and adds infrastructure complexity. If you want persistence, you can add it later. The `/metrics` endpoint is what matters for the resume.

**Latency granularity:** Track per-stage latency (decision, search, fetch, validate, respond) not just end-to-end. End-to-end latency tells you there is a problem. Per-stage latency tells you where the problem is. The extra instrumentation is minimal.

**When to reset counters:** Add a `POST /v1/metrics/reset` endpoint for development convenience. Do not expose this in production without auth. For the README, take a clean snapshot after 100 queries — note the query count in the README for context.

#### Exit check
`GET /v1/metrics` returns a valid JSON response with all fields populated after at least 50 requests. The README contains a metrics table with real numbers. You can answer these questions from memory in an interview: average end-to-end latency, cache hit rate, and which search provider is the primary fallback.

---

### M6 — Docker + CI
**Timeline: Week 3–4**

#### Why
A project that only runs on your laptop is not production software. Docker solves the "works on my machine" problem — it defines the exact environment the service runs in, including Python version, dependencies, and the Redis connection. Anyone who clones the repo and runs `docker-compose up` gets a working service in under a minute.

CI solves the "I thought it still worked" problem. Without automated tests running on every push, it is easy to break something without noticing. A passing CI badge on the README also signals to any recruiter or interviewer who looks at the repo that you treat quality as a non-negotiable, not an afterthought.

#### What to build

**Docker (`docker/`)**

`Dockerfile` — use a multi-stage build:
- Stage 1 (`builder`): install all dependencies into a virtual environment.
- Stage 2 (`runtime`): copy only the venv and application code, no dev tools. This keeps the image small.
- Base image: `python:3.11-slim`. Avoid `python:3.11` (full Debian image, much larger).
- Expose port 8000. Set `CMD ["uvicorn", "src.app.api:app", "--host", "0.0.0.0", "--port", "8000"]`.

`docker-compose.yml` — define two services:
- `searchmesh`: builds from `docker/Dockerfile`, mounts `.env`, maps port 8000, depends on `redis`.
- `redis`: uses `redis:7-alpine`. No custom config needed.
- Add a `healthcheck` for both services so Docker knows when they are ready.

Note: Ollama is not in the Compose file because it runs on the host machine. Use `OLLAMA_HOST=http://host-gateway:11434` (Linux) or `http://host.docker.internal:11434` (Mac/Windows) in the env file.

**Dev dependencies (`requirements-dev.txt`)**
```
pytest
pytest-asyncio
httpx          # for async test client
ruff           # linter + formatter
mypy           # type checker
locust         # load testing (M7)
```

**Tests**

`tests/unit/test_ranking.py` — minimum 8 test cases as defined in M4.

`tests/unit/test_validator.py` — test that the validator correctly accepts relevant context and rejects off-topic text. Use mocked inputs.

`tests/unit/test_cache.py` — test cache key generation, TTL logic, hit/miss behavior. Mock the Redis client.

`tests/integration/test_chat_endpoint.py` — use `httpx.AsyncClient` with `app` as the transport (no real network calls). Mock the Ollama client and search providers. Test: valid request returns 200 with correct schema, missing required field returns 422, Ollama unreachable returns 503.

**GitHub Actions (`.github/workflows/ci.yml`)**
```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: ruff check src/ tests/
      - run: mypy src/
      - run: pytest tests/unit/ tests/integration/ -v
```

#### Key decisions

**Multi-stage Docker build:** The single biggest mistake in Python Docker setups is installing dev dependencies in the production image. Multi-stage builds prevent this. The final image should only contain what the service needs to run.

**Don't add Redis to the Compose file with a password yet:** Auth adds complexity. For a local dev environment, passwordless Redis on the internal Docker network is fine. If you ever expose this service externally, add `requirepass` in the Redis config. Not now.

**mypy strictness:** Start with `--ignore-missing-imports` and `--no-strict-optional` in `pyrightconfig.json`/`mypy.ini`. Do not start with strict mode — you will spend more time fighting the type checker than building features. Add stricter settings incrementally.

**Test isolation:** Integration tests must not depend on a running Ollama or Redis. Mock both. If a test requires real infrastructure, it is a load test, not an integration test.

#### Exit check
`docker-compose up` starts both services without errors. `curl http://localhost:8000/v1/health` returns `{"ollama": "...", "redis": "ok"}` from inside Docker. `git push` triggers CI on GitHub Actions. CI runs linting, type checking, and all unit + integration tests. The CI badge is green. README includes the badge.

---

### M7 — Load testing + hardening
**Timeline: Week 4**

#### Why
Everything before this milestone proves the system works correctly. This milestone proves it works under pressure. Correctness without resilience is not production software. An SDE2 is expected to know the limits of their system — not discover them when things break in production.

Load testing also exposes bugs that unit tests cannot: race conditions in the async pipeline, connection pool exhaustion, memory leaks under sustained load, and failure modes that only appear when multiple requests hit simultaneously.

#### What to build

**Load test script (`tests/load/locustfile.py`)**
- Use Locust to simulate concurrent users.
- Define three task types: chat with no web search (35% of traffic), chat with web search (50%), direct search endpoint (15%).
- Use a mix of unique and repeated queries to exercise both cache hits and misses.
- Run three scenarios: 10 users, 20 users, 50 users. Record for each: requests per second, median latency, 95th percentile latency, error rate.
- Target: 20 concurrent users with <5% error rate. If you hit that, the project is load-tested. If you don't, fix the bottleneck and document what you changed.

**Rate limiting**
- Install `slowapi`. Add a rate limit of 10 requests per minute per IP to `POST /v1/chat`.
- This is not about preventing abuse — it is about demonstrating that you thought about it. Rate limiting is a standard backend concern.
- Return `429 Too Many Requests` with a `Retry-After` header.

**Global timeout middleware**
- Add a FastAPI middleware that cancels any request still running after 60 seconds and returns `{"error": "request_timeout"}`.
- This prevents one slow Ollama call from holding a connection open indefinitely under load.

**Graceful degradation documentation**
Write `docs/failure_modes.md` that covers:
- Ollama is unreachable: system returns `503` on health check, `/chat` returns `{"error": "llm_unavailable"}`.
- Redis is unreachable: search and fetch still run (no cache), session history falls back to stateless (no memory). System degrades gracefully, does not crash.
- All search providers fail: system answers from Ollama's training knowledge with no web context. The response includes `"used_web": false`.
- Rate limit hit: `429` with retry header.
- Fetch fails for chosen URL: validator rejects empty content, orchestrator falls back to raw user prompt (no context injection).

**README load test results**
Add a table like:

| Concurrent users | RPS | Median latency | P95 latency | Error rate |
|---|---|---|---|---|
| 10 | 2.8 | 1.9s | 4.2s | 0.3% |
| 20 | 3.2 | 2.4s | 6.1s | 1.8% |
| 50 | 2.1 | 8.3s | 18s | 9.4% |

Run these against real infrastructure. The numbers above are placeholders — replace with actuals.

#### Key decisions

**Locust vs k6 vs wrk:** Use Locust. It is Python-native, easy to write realistic task distributions in, and produces clean reports. k6 is more powerful but requires JavaScript and a separate install. wrk is great for raw throughput benchmarks but cannot simulate realistic user behavior. Locust is the right tradeoff for this project.

**Where the bottleneck will be:** Almost certainly Ollama. The local model inference is the slowest part of the pipeline by a large margin. You will likely see P95 latency climb steeply at 20+ concurrent users because requests queue for the single Ollama instance. Document this honestly — it is a hardware constraint, not a code deficiency. The fix at scale would be a model serving layer (vLLM, Ollama with multiple GPU workers), which is out of scope here.

**What "hardening" means practically:** After the load test, look at the error log for the 50-user run. Fix anything that is a code error (not a resource constraint). Add retry on connection pool exhaustion. Ensure all async context managers properly release resources on error. Run the 20-user scenario again and verify the error rate is below 5%.

#### Exit check
Load test script runs successfully with 20 concurrent users and produces a report. README contains the load test table with real numbers from actual runs. `POST /v1/chat` enforces rate limiting — 429 is returned after 10 requests per minute from the same IP. Server handles Redis going down mid-run without crashing. Failure modes document exists in `docs/`.

---

## README must-haves after M7

The README is part of the deliverable. It needs:

1. Architecture diagram (Mermaid or image) that matches the actual code
2. Metrics table:

| Metric | Value |
|---|---|
| Avg end-to-end latency | ~2.1s |
| Cache hit rate (repeated queries) | ~38% |
| Search fallback rate (Serper) | ~12% |
| Search fallback rate (DDG) | ~4% |
| Fetch fallback rate (Trafilatura) | ~9% |
| Validation pass rate | ~87% |
| Sustained RPS (20 users) | ~3.2 |

3. One-command local setup: `docker-compose up`
4. Environment variables table
5. API reference or link to `docs/api_reference.md`

Numbers must come from actual runs. Do not fake them.

---

## Resume bullets (only valid after M5+)

Replace anything vague with these. Only use what you've actually built.

**Primary:**
> Designed and built SearchMesh, a FastAPI-based local retrieval API backed by Ollama with multi-tier search fallback across three providers, Redis-cached results, session-persistent conversation memory, and a deterministic source ranking algorithm.

**Supporting bullets:**
> Implemented per-stage latency tracking and fallback counters; reduced redundant fetch work by ~38% via Redis query and content caching.

> Built a scored source ranking pipeline combining keyword overlap, source trust weights, and content heuristics to replace heuristic-free "best result" selection.

> Added retry logic with exponential backoff, per-stage timeouts, and graceful degradation — system returns answers even when all search providers fail.

> Containerized the service with Docker Compose (app + Redis), configured GitHub Actions CI with ruff, mypy, and pytest; load-tested to 20 concurrent users at ~3 RPS with <5% error rate.

---

## What NOT to claim

Regardless of what you've seen in other repos or want to sound impressive:

- Do not say "distributed" unless you have multiple nodes
- Do not say "agent" unless there is stateful decision-making with tool calls and memory (you'll have memory after M3, but it's still a pipeline, not an agent)
- Do not say "real-time" unless you have latency SLAs
- Do not say "semantic search" unless you have embeddings
- Do not say "LLM orchestration framework" — you built a pipeline, call it that

Honest language at SDE2 level is: "I designed a multi-stage retrieval pipeline with caching, fallback handling, and observability." That is accurate and strong.

---

## SDE2 signal this project demonstrates

An SDE2 is expected to own an entire feature end-to-end: design, reliability, observability, testing, deployment. This project can demonstrate all of it if the milestones are completed:

| SDE2 signal | Where in this project |
|---|---|
| System design thinking | Multi-tier fallback, caching strategy, session memory |
| Reliability engineering | Retries, timeouts, graceful degradation |
| Observability | Per-stage metrics, structured logging, `/metrics` endpoint |
| API design | Clean REST contract, versioned, schema-validated |
| Testing discipline | Unit + integration + load tests, CI enforcement |
| Deployment ownership | Docker + Compose, one-command setup |
| Data modeling | Session history schema, search result schema with scores |
| Performance awareness | Cache hit rate, latency benchmarks, concurrency testing |

Do not treat this as a portfolio piece until at least M5 is done. Before that it is a script.
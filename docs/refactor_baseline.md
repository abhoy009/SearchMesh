# Refactor Baseline (Phase 0)

## Purpose
- Capture current runtime behavior before modular refactor.
- Define parity checks so refactor does not silently change behavior.

## Current Entrypoint
- File: `ollama_web_search.py`
- Mode support:
  - Interactive mode: `python ollama_web_search.py`
  - One-shot mode: `python ollama_web_search.py "query"`

## CLI Contract (Current)
- `--model` (default: `OLLAMA_MODEL` env or `qwen2.5:0.5b`)
- `--max-results` (default: `5`)
- `--debug` (default follows `AGENT_DEBUG`, enabled unless env is off-like value)
- Positional `query` for one-shot execution

## Runtime Pipeline (Observed)
1. Check Ollama readiness (`client.ps()`).
2. Decide search needed (`search_or_not_agent`).
3. If search is needed:
   - Generate query.
   - Get search results via fallback:
     - Ollama `web_search`
     - Serper API
     - DuckDuckGo HTML scrape
   - Pick best URL.
   - Fetch page via fallback:
     - Ollama `web_fetch`
     - Trafilatura extraction
   - Validate context relevance.
4. Inject validated context only.
5. Stream final assistant response.

## Error/Degradation Behavior (Current)
- Most search/fetch stages catch exceptions and continue fallback path.
- If Ollama is unreachable, turn exits early with guidance to run `ollama serve`.
- If no validated context is found, assistant answers from original user prompt only.

## Smoke Parity Checklist
- [ ] Greeting prompt (for example `hello`) should usually skip search.
- [ ] Time-sensitive prompt should usually trigger search path.
- [ ] Missing `SERPER_API_KEY` still allows DuckDuckGo fallback.
- [ ] Failed fetch should not inject empty context.
- [ ] One-shot mode exits after one response.
- [ ] Interactive mode maintains in-memory turn history.

## Constraints For Refactor
- Preserve CLI flags and defaults.
- Preserve fallback order until intentionally changed by ADR.
- Preserve validation gate before context injection.

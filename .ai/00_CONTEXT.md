# Current Context

## Project Purpose
- Local Python assistant using Ollama with optional web augmentation.
- Main goal in current code: choose when to search web, fetch context, validate relevance, answer.

## Current Branch/Task
- Branch: `main`
- Task: execute Phase 0/1 of refactor-first plan before feature reuse; plan tracked in `neststep.md`.

## Current State
- Runtime pipeline extracted into `src/app`, `src/services`, and `src/infra`.
- `ollama_web_search.py` is now a compatibility launcher to `src.app.cli`.
- Debug visibility restored in orchestrator (`--debug` now prints search/query/results/context-stage logs).
- Supports interactive chat and one-shot query mode.
- Search fallback chain implemented: Ollama `web_search` -> Serper -> DuckDuckGo HTML.
- Content fetch fallback implemented: Ollama `web_fetch` -> Trafilatura extraction.
- Validation gate implemented before injecting web context into final prompt.
- No FastAPI server in repo.
- Automated test scaffold exists (`unittest`; minimal coverage).
- Refactor-first roadmap with module split and TODOs is documented in `neststep.md`.

## Main Modules
- `ollama_web_search.py`: compatibility launcher.
- `src/app/cli.py`: active CLI entrypoint and orchestration wiring.
- `src/app/orchestrator.py`: turn orchestration with context gating.
- `src/services/*`: extracted decision/query/search/rank/fetch/validate/respond services.
- `src/infra/*`: extracted Ollama client and HTTP helper utilities.
- `README.md`: setup, usage, pipeline description.
- `plan.md`: future roadmap notes (not implementation).
- `docs/refactor_baseline.md`: parity baseline and migration constraints.

## Critical Risks
- Core behavior is now split, but service integration tests are still shallow.
- Automated coverage is minimal; regression risk remains moderate-high.
- DuckDuckGo HTML scraping may break if markup changes.
- Network/provider failures are still mostly swallowed in fallback logic.
- Search relevance depends on LLM prompt decisions without deterministic ranking.

## Next Actions
- Add stronger unit/integration tests for extracted services and orchestrator parity.
- Move toward Phase 4/5 tasks in `neststep.md` (test depth and regression gates).
- Add measurable validation (latency, fallback hit rate, fetch success rate).
- Confirm whether `plan.md` roadmap should be treated as official product direction.

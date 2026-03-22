# Next Step Plan: Refactor Before Reuse

## Objective
- Refactor the current single-file pipeline into modular services before adding new product features.
- Preserve existing behavior while improving testability, maintainability, and observability readiness.

## Scope Rules
- No major feature expansion until refactor baseline is complete.
- Keep CLI behavior working during transition.
- Add interfaces first, then move logic behind those interfaces.

## Target Structure
```text
src/
  app/
    config.py
    models.py
    interfaces.py
    orchestrator.py
    cli.py
  services/
    decision_engine.py
    query_generator.py
    search_providers.py
    ranking.py
    fetcher.py
    validator.py
    responder.py
  infra/
    ollama_client.py
    http_client.py
    logging.py
tests/
  unit/
  integration/
```

## Interface Contracts (First-Class)
- `DecisionEngine.should_search(user_input: str) -> bool`
- `QueryGenerator.generate(user_input: str) -> str`
- `SearchProvider.search(query: str, max_results: int) -> list[SearchResult]`
- `Ranker.pick_best(user_input: str, results: list[SearchResult]) -> str | None`
- `Fetcher.fetch(url: str) -> str`
- `Validator.is_relevant(user_input: str, context: str) -> bool`
- `Responder.stream(messages: list[dict[str, str]]) -> str`
- `TurnOrchestrator.run_turn(...) -> TurnResult`

## Execution Plan

### Phase 0: Baseline Capture
- Document current behavior and critical paths from `ollama_web_search.py`.
- Add smoke validation checklist for non-web and web-required prompts.
- Lock current CLI arguments and defaults as migration constraints.

### Phase 1: Create Skeleton + Models
- Create `src/` package and typed data models (`SearchResult`, `TurnResult`, config model).
- Add interfaces (`Protocol` or abstract classes) for each service boundary.
- Keep old script untouched; no behavior change yet.

### Phase 2: Extract Infrastructure
- Move Ollama client initialization/readiness to `infra/ollama_client.py`.
- Move generic HTTP helpers and retry-ready wrapper to `infra/http_client.py`.
- Centralize configuration loading in `app/config.py`.

### Phase 3: Extract Services
- Move decision/query/ranking/validation into separate service modules.
- Move search fallback chain into `services/search_providers.py`.
- Move fetch fallback chain into `services/fetcher.py`.
- Keep method signatures aligned to interfaces.

### Phase 4: Orchestrator + CLI Adapter
- Implement `TurnOrchestrator` to coordinate service calls.
- Rebuild CLI entrypoint in `app/cli.py`.
- Replace root script with thin bootstrap wrapper (or keep compatibility shim).

### Phase 5: Tests + Regression Gate
- Add unit tests for each service using mocks.
- Add integration tests for:
  - search-needed path
  - no-search path
  - fallback behavior when provider fails
  - context validation gate
- Ensure behavior parity with old script before adding new features.

## TODOs (Actionable)
- [x] Create `src/app`, `src/services`, `src/infra`, and `tests` directories.
- [x] Define typed models (`SearchResult`, `TurnResult`, config structures).
- [x] Define all service interfaces in `src/app/interfaces.py`.
- [x] Move env + defaults into `src/app/config.py`.
- [x] Extract Ollama client builder/readiness into `src/infra/ollama_client.py`.
- [x] Extract HTTP GET + request helpers into `src/infra/http_client.py`.
- [x] Extract decision logic into `src/services/decision_engine.py`.
- [x] Extract query generation into `src/services/query_generator.py`.
- [x] Extract search fallback chain into `src/services/search_providers.py`.
- [x] Extract ranking/URL selection into `src/services/ranking.py`.
- [x] Extract fetch logic into `src/services/fetcher.py`.
- [x] Extract validation logic into `src/services/validator.py`.
- [x] Extract streaming response into `src/services/responder.py`.
- [x] Implement `TurnOrchestrator` in `src/app/orchestrator.py`.
- [x] Create new CLI entrypoint `src/app/cli.py`.
- [x] Keep compatibility launcher at repo root.
- [x] Add unit test scaffolding and first smoke integration tests.
- [x] Update README and `.ai/` docs after each completed phase.

## Definition of Done (Refactor Stage)
- Pipeline logic no longer concentrated in a single monolithic file.
- Clear interfaces exist between orchestration, services, and infra.
- CLI behavior is preserved for existing commands.
- Core paths have at least baseline automated coverage.
- Team can add FastAPI/Redis/metrics without reworking core boundaries again.

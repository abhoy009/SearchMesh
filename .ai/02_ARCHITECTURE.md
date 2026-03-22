# Architecture

## System Shape
- Modular Python CLI application with orchestrated service layers.
- Primary execution path is a sequential turn pipeline in `DefaultTurnOrchestrator.run_turn()`.

## Folder Map
- `ollama_web_search.py`: compatibility launcher to `src.app.cli`.
- `src/app/`: active config/models/interfaces/orchestration/CLI modules.
- `src/services/`: active decision/query/search/rank/fetch/validate/respond services.
- `src/infra/`: active Ollama client and HTTP helper modules.
- `tests/`: unit/integration scaffolding (minimal current coverage).
- `docs/refactor_baseline.md`: baseline behavior and parity checks for migration.
- `requirements.txt`: dependencies.
- `pyrightconfig.json`: static type-checker scope.
- `.env.example`: environment template.
- `README.md`: user/developer docs.
- `plan.md`: roadmap notes.

## Major Components
- CLI/bootstrap:
  - `src/app/cli.py::main()`
- Client/bootstrap:
  - `src/infra/ollama_client.py::import_ollama(), build_client(), is_ready()`
- Decision + query:
  - `src/services/decision_engine.py::DecisionEngineService`
  - `src/services/query_generator.py::QueryGeneratorService`
- Search providers:
  - `src/services/search_providers.py::FallbackSearchProvider`
- Result selection:
  - `src/services/ranking.py::RankingService`
- Fetch + extraction:
  - `src/services/fetcher.py::FetcherService`
- Validation:
  - `src/services/validator.py::ValidatorService`
- Response output:
  - `src/services/responder.py::ResponderService`
- Orchestration:
  - `src/app/orchestrator.py::DefaultTurnOrchestrator`

## Data Flow
1. User input enters CLI (`main`).
2. CLI checks Ollama readiness.
3. Search need is decided.
4. If search needed: generate query -> fetch search results -> pick best URL -> fetch text -> validate context.
5. Valid context is appended to user payload.
6. Final assistant response is streamed.
7. Turn is appended to in-memory history list.

## External Services/APIs/Libraries
- Ollama local/remote endpoint via Python SDK (`ollama>=0.6.0`).
- Serper API (optional, needs `SERPER_API_KEY`).
- DuckDuckGo HTML endpoint (fallback scraping).
- `trafilatura` for extraction fallback.
- `beautifulsoup4` for HTML parsing.
- `python-dotenv` for env loading.

## Key Abstractions
- Fallback chains (search, then fetch).
- LLM-based gates (search-needed, best URL, context-valid).
- In-memory conversation history only (no persistence).
- Interface-first service boundary (`src/app/interfaces.py`) now wired in active orchestration.

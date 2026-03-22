# Decisions (ADR Style)

## 2026-03-21 - Single-file pipeline implementation
- Decision: implement end-to-end flow in one file (`ollama_web_search.py`).
- Reason: fast iteration and simple local execution.
- Alternatives considered: modular package layout with separate services/modules.
- Consequences: low setup complexity, but high coupling and harder testing.

## 2026-03-21 - Multi-tier web search fallback
- Decision: fallback order is Ollama `web_search` -> Serper -> DuckDuckGo HTML.
- Reason: prefer native integration first, quality API second, free fallback third.
- Alternatives considered: single provider only.
- Consequences: better resilience, but inconsistent ranking/format across providers.

## 2026-03-21 - Multi-tier content fetch fallback
- Decision: use Ollama `web_fetch` first, then Trafilatura extraction.
- Reason: native API convenience plus robust extraction backup.
- Alternatives considered: direct extraction only.
- Consequences: improved retrieval success, but external fetch behavior depends on provider/runtime.

## 2026-03-21 - LLM relevance validation gate before context injection
- Decision: inject web context only when validator agent returns `True`.
- Reason: reduce irrelevant context contamination.
- Alternatives considered: always inject first fetched content.
- Consequences: better precision potential, but may drop useful context on false negatives.

## 2026-03-22 - Introduce `.ai/` persistent project memory
- Decision: add vendor-neutral `.ai/` folder as the single handoff source.
- Reason: future agents should start from concise repo-local context rather than chat history.
- Alternatives considered: no memory layer, or vendor-specific folders.
- Consequences: lower onboarding time; requires regular maintenance to avoid stale docs.

## 2026-03-22 - Refactor before reusing/extending pipeline
- Decision: require module/interface refactor before adding major new capabilities.
- Reason: single-file implementation is too coupled for reliable scaling, testing, and observability.
- Alternatives considered: continue direct feature additions in monolithic script.
- Consequences: short-term delivery slows, but reduces future rework and unlocks cleaner FastAPI/Redis/metrics integration.

## 2026-03-22 - Interface-first migration scaffold
- Decision: introduce `src/` packages with typed models/interfaces and placeholder services before moving runtime logic.
- Reason: lock contracts early and reduce risk of accidental behavior regressions during extraction.
- Alternatives considered: direct function-by-function moves without shared contracts.
- Consequences: early stubs exist temporarily, but future extractions become more predictable and testable.

## 2026-03-22 - Make `src/` the active runtime path
- Decision: run the CLI pipeline from `src/app/cli.py` + orchestrator/services, with root file kept as compatibility launcher.
- Reason: complete practical extraction while preserving existing user command (`python ollama_web_search.py`).
- Alternatives considered: keep monolith as active runtime and only maintain scaffolding.
- Consequences: architecture is cleaner now; integration test depth must increase to protect parity.

# Changelog

## 2026-03-22
- Added vendor-neutral `.ai/` project memory system (README, context, project, architecture, decisions, workflow, commands, testing, open questions, changelog) to support persistent agent/human handoff.
- Added `neststep.md` with a refactor-first execution plan, target module boundaries, and actionable TODO checklist.
- Started refactor Phase 0/1: added `docs/refactor_baseline.md`, `src/` scaffold (app/services/infra), typed models/interfaces/config, CLI shim, and initial unittest scaffolding.
- Completed major extraction pass: moved core runtime pipeline from monolith into `src/infra`, `src/services`, and `src/app/orchestrator`; converted `ollama_web_search.py` into compatibility launcher.
- Fixed refactor regression: wired `--debug`/`AGENT_DEBUG` into orchestrator and restored stage-level diagnostic logs.
- Cleanup pass: removed unused `build_stub_result()` helper and deleted unused legacy file `sys_msg.py`; updated docs to remove stale references.

## 2026-03-21
- Implemented local assistant pipeline with optional web augmentation and multi-tier fallback flow in `ollama_web_search.py`.
- Added/updated setup and usage documentation in `README.md`.

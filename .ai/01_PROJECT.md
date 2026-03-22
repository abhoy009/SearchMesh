# Project

## What It Does
- Runs a local assistant through Ollama.
- Optionally enriches answers with web context from a multi-tier search/fetch pipeline.

## Target Users
- Primary: developer/operator running local Ollama from terminal.
- Secondary: UNKNOWN.

## Core Features
- Interactive and one-shot CLI query modes.
- Search decision step (`True`/`False`) per user turn.
- Query generation for web search.
- Multi-provider search fallback.
- Best URL selection from candidates.
- Multi-step content retrieval and relevance validation.
- Streamed assistant output.

## Non-Goals (Current Repo)
- Hosted multi-user service.
- Web UI.
- Persistent session/database layer.
- Production observability stack.

## Success Criteria
- Assistant responds reliably when Ollama is reachable.
- Web context is used only when validation passes.
- Fallbacks return usable results when top-tier provider fails.

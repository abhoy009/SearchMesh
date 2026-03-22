# Open Questions

## Unresolved Product/Direction
- Is `plan.md` the official roadmap or exploratory notes?
- Should this remain a CLI tool or be converted to API service (FastAPI)?
- Target user persona beyond local developer usage: `UNKNOWN`.

## Technical Unknowns
- Intended Python version pinning policy: `UNKNOWN`.
- Preferred lint/format tools: `UNKNOWN`.
- Expected reliability/latency targets: `UNKNOWN`.
- Required citation behavior in final answers: partially implied, not enforced.

## Risks
- Single-file architecture will slow future feature growth.
- No automated tests increases chance of silent regressions.
- External scraping/API dependencies may change unexpectedly.

## Assumptions
- Ollama SDK web APIs (`web_search`, `web_fetch`) remain available in runtime environment.
- Current fallback order is intentional and should be preserved unless explicitly changed.

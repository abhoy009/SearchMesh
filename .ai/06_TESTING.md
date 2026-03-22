# Testing

## Test Strategy (Current)
- Manual runtime validation through CLI interactions.
- Debug logs used to verify decision points and fallback path behavior.

## Covered
- Basic end-to-end turn execution when Ollama is reachable.
- Search fallback behavior across available providers (manual).
- Content fetch fallback behavior (manual).
- Unit tests for new refactor data models (`SearchResult`, `TurnResult` defaults).

## Not Covered
- Automated unit tests for helper functions.
- Automated integration tests for full extracted pipeline behavior.
- Deterministic regression tests for prompt-driven routing/validation.
- Contract tests for Serper and DuckDuckGo parsing.

## How To Run Tests
- Automated scaffold tests:
```bash
python -m unittest discover -s tests -t . -v
```
- Manual smoke test:
```bash
python ollama_web_search.py --debug "today weather in Delhi"
```
- Validate logs for:
  - search decision
  - query generation
  - results count
  - validated context source

## Known Flaky Areas
- DuckDuckGo HTML selectors may break due to markup changes.
- LLM-based `True/False` responses can vary by model.
- External network/provider availability affects reproducibility.
- Integration parity tests are currently placeholders and not yet enforcing extracted runtime parity.

## Key Validation Paths
1. Non-web prompt should often skip search and still answer.
2. Time-sensitive prompt should trigger search path.
3. Missing `SERPER_API_KEY` should still allow DuckDuckGo fallback.
4. Invalid/empty fetch should not inject context.

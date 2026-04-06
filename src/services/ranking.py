"""Deterministic source ranking — no LLM calls.

Implements the scoring algorithm from plan.md exactly:
  - Keyword overlap between query and title+snippet (weight: 0.4)
  - Source trust weight: serper=1.0, ollama=0.8, duckduckgo=0.6 (weight: 0.3)
  - URL heuristics: penalize social/forum domains (−0.2)
  - Snippet length as content signal (weight: 0.3)

Result: deterministic, testable, fast. Zero LLM calls.
This replaces the old LLM-based pick_best() which was taking 5+ minutes.
"""
from __future__ import annotations

from src.app.models import SearchResult

_PENALIZED_DOMAINS = ["reddit.com", "quora.com", "twitter.com", "facebook.com", "x.com"]
_SOURCE_TRUST = {"serper": 1.0, "ollama": 0.8, "duckduckgo": 0.6}


def score_result(result: SearchResult, query: str) -> float:
    score = 0.0

    # Keyword overlap between query tokens and title+snippet
    query_tokens = set(query.lower().split())
    text = (result.title + " " + result.content).lower()
    result_tokens = set(text.split())
    overlap = len(query_tokens & result_tokens) / max(len(query_tokens), 1)
    score += overlap * 0.4

    # Source trust weight
    trust = _SOURCE_TRUST.get(result.source, 0.5)
    score += trust * 0.3

    # URL heuristics: penalize social/forum domains
    if any(d in result.url for d in _PENALIZED_DOMAINS):
        score -= 0.2

    # Prefer results with longer snippets (more content signal)
    score += min(len(result.content) / 500, 1.0) * 0.3

    return round(max(score, 0.0), 4)


def rank_results(results: list[SearchResult], query: str) -> list[SearchResult]:
    """Score, deduplicate by domain, and sort descending by score."""
    if not results:
        return []

    # Score each result
    scored = [(r, score_result(r, query)) for r in results]

    # Deduplicate: keep only highest-scored result per domain
    seen_domains: dict[str, tuple[SearchResult, float]] = {}
    for result, score in scored:
        try:
            from urllib.parse import urlparse
            domain = urlparse(result.url).netloc
        except Exception:
            domain = result.url

        existing = seen_domains.get(domain)
        if existing is None or score > existing[1]:
            seen_domains[domain] = (result, score)

    deduped = list(seen_domains.values())
    deduped.sort(key=lambda x: x[1], reverse=True)

    # Return SearchResult objects with score field populated
    ranked: list[SearchResult] = []
    for result, score in deduped:
        result.score = score
        ranked.append(result)

    return ranked


class RankingService:
    """Deterministic ranker — no LLM, no network calls, instant."""

    def pick_best(self, user_input: str, results: list[SearchResult]) -> str | None:
        if not results:
            return None
        ranked = rank_results(results, user_input)
        return ranked[0].url if ranked else results[0].url

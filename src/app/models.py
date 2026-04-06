"""Core domain models shared across app, services, and infra layers."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    content: str = ""
    source: str = "unknown"
    score: float = 0.0
    snippet: str = ""  # alias — populated from content for API responses


@dataclass(slots=True)
class TurnMetrics:
    search_used: bool = False
    results_count: int = 0
    context_validated: bool = False


@dataclass(slots=True)
class TurnResult:
    assistant_text: str
    user_input: str
    query: str = ""
    chosen_url: str | None = None
    context_used: bool = False
    results: list[SearchResult] = field(default_factory=list)
    provider_used: str = "none"
    fetch_method: str = "none"
    latency: dict[str, float] = field(default_factory=dict)
    metrics: TurnMetrics = field(default_factory=TurnMetrics)

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    content: str = ""
    source: str = "unknown"


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
    metrics: TurnMetrics = field(default_factory=TurnMetrics)


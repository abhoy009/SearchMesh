from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from .models import SearchResult, TurnResult


Message = Mapping[str, str]


class DecisionEngine(Protocol):
    def should_search(self, user_input: str) -> bool:
        ...


class QueryGenerator(Protocol):
    def generate(self, user_input: str) -> str:
        ...


class SearchProvider(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]:
        ...


class Ranker(Protocol):
    def pick_best(self, user_input: str, results: list[SearchResult]) -> str | None:
        ...


class Fetcher(Protocol):
    def fetch(self, url: str) -> str:
        ...


class Validator(Protocol):
    def is_relevant(self, user_input: str, context: str) -> bool:
        ...


class Responder(Protocol):
    def stream(self, messages: Sequence[Message]) -> str:
        ...


class TurnOrchestrator(Protocol):
    def run_turn(self, user_input: str, history: list[dict[str, str]]) -> TurnResult:
        ...


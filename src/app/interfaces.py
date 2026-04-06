"""Protocol definitions for all pipeline service components.

Using typing.Protocol so services can be swapped with any compatible implementation
without inheritance. All methods are now async to match the service layer.
"""
from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from .models import SearchResult, TurnResult


Message = Mapping[str, str]


class DecisionEngine(Protocol):
    async def should_search(self, user_input: str) -> bool:
        ...


class QueryGenerator(Protocol):
    async def generate(self, user_input: str) -> str:
        ...


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> tuple[list[SearchResult], str]:
        ...


class Ranker(Protocol):
    def pick_best(self, user_input: str, results: list[SearchResult]) -> str | None:
        ...


class Fetcher(Protocol):
    async def fetch(self, url: str, max_chars: int) -> tuple[str, str]:
        ...


class Validator(Protocol):
    async def is_relevant(self, user_input: str, context: str) -> bool:
        ...


class Responder(Protocol):
    async def respond(self, messages: Sequence[Message]) -> str:
        ...


class TurnOrchestrator(Protocol):
    async def run_turn(
        self,
        user_input: str,
        history: list[dict[str, str]],
        use_web: bool,
        model: str | None,
        max_context_chars: int,
    ) -> TurnResult:
        ...

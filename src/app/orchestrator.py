from __future__ import annotations

from dataclasses import dataclass

from .interfaces import DecisionEngine, Fetcher, QueryGenerator, Ranker, Responder, SearchProvider, Validator
from .models import SearchResult, TurnMetrics, TurnResult

MAX_CONTEXT_CHARS = 6000


def add_context_to_user_prompt(user_prompt: str, source_url: str, context: str) -> str:
    return (
        f"{user_prompt}\n\n"
        "Use this web context only if relevant:\n"
        f"SOURCE_URL: {source_url}\n"
        f"WEB_CONTEXT:\n{context[:MAX_CONTEXT_CHARS]}"
    )


@dataclass(slots=True)
class DefaultTurnOrchestrator:
    decision_engine: DecisionEngine
    query_generator: QueryGenerator
    search_provider: SearchProvider
    ranker: Ranker
    fetcher: Fetcher
    validator: Validator
    responder: Responder
    max_results: int = 5
    debug: bool = False

    def run_turn(self, user_input: str, history: list[dict[str, str]]) -> TurnResult:
        use_search = False
        query = ""
        chosen_url: str | None = None
        context = ""
        results: list[SearchResult] = []

        try:
            use_search = self.decision_engine.should_search(user_input)
            if self.debug:
                print(f"[agent] search_or_not={use_search}")
        except Exception:
            use_search = False
            if self.debug:
                print("[agent] search_or_not failed")

        if use_search:
            try:
                query = self.query_generator.generate(user_input)
                if self.debug:
                    print(f"[agent] query={query}")
                results = self.search_provider.search(query, max_results=self.max_results)
                if self.debug:
                    print(f"[agent] results={len(results)}")

                if results:
                    best_url = self.ranker.pick_best(user_input, results)
                    ordered_urls: list[str] = []
                    if best_url:
                        ordered_urls.append(best_url)
                    for item in results:
                        if item.url not in ordered_urls:
                            ordered_urls.append(item.url)

                    for url in ordered_urls[:3]:
                        candidate_context = self.fetcher.fetch(url)
                        if not candidate_context:
                            continue

                        if self.validator.is_relevant(user_input, candidate_context):
                            chosen_url = url
                            context = candidate_context
                            if self.debug:
                                print(f"[agent] context validated from: {url}")
                            break
                if self.debug and not context:
                    print("[agent] no validated context found")
            except Exception:
                if self.debug:
                    print("[agent] web pipeline failed")

        user_payload = add_context_to_user_prompt(user_input, chosen_url, context) if (chosen_url and context) else user_input
        messages = history + [{"role": "user", "content": user_payload}]

        assistant_text = self.responder.stream(messages)
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": assistant_text})

        return TurnResult(
            assistant_text=assistant_text,
            user_input=user_input,
            query=query,
            chosen_url=chosen_url,
            context_used=bool(chosen_url and context),
            metrics=TurnMetrics(
                search_used=use_search,
                results_count=len(results),
                context_validated=bool(chosen_url and context),
            ),
        )

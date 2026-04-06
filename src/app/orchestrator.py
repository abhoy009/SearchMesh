"""Async pipeline orchestrator.

Owns the full turn pipeline: decision → query_gen → search → fetch → validate → respond.
Per-stage latency is tracked via time.monotonic() and returned in every TurnResult.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .interfaces import DecisionEngine, Fetcher, QueryGenerator, Ranker, Responder, SearchProvider, Validator
from .models import SearchResult, TurnMetrics, TurnResult
from src.app.config import settings
from src.services.ranking import rank_results

MAX_CONTEXT_CHARS_DEFAULT = 4000

def build_rag_system_prompt(source_url: str, context: str, max_chars: int) -> str:
    return (
        "You are an AI assistant answering questions precisely using the provided web context. "
        "Strictly follow these rules:\n"
        "1. Answer the question concisely based ONLY on the context.\n"
        "2. Do NOT hallucinate or perform complex math, calculations, or unit conversions unless explicitly asked.\n"
        "3. If the context contains a direct number/price, just output it directly and clearly.\n"
        f"SOURCE_URL: {source_url}\n"
        f"WEB_CONTEXT:\n<context>{context[:max_chars]}</context>"
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

    async def run_turn(
        self,
        user_input: str,
        history: list[dict[str, str]],
        use_web: bool = True,
        model: str | None = None,
        max_context_chars: int = MAX_CONTEXT_CHARS_DEFAULT,
    ) -> TurnResult:
        latency: dict[str, float] = {
            "decision": 0.0,
            "search": 0.0,
            "fetch": 0.0,
            "validate": 0.0,
            "respond": 0.0,
            "total": 0.0,
        }
        total_start = time.monotonic()

        use_search = False
        query = ""
        chosen_url: str | None = None
        context = ""
        results: list[SearchResult] = []
        provider_used = "none"
        fetch_method = "none"

        # --- Stage: Decision ---
        if use_web:
            t0 = time.monotonic()
            try:
                use_search = await self.decision_engine.should_search(user_input)
            except Exception:
                use_search = False
            latency["decision"] = round((time.monotonic() - t0) * 1000, 2)

        # --- Stage: Search ---
        if use_search:
            t0 = time.monotonic()
            try:
                query = await self.query_generator.generate(user_input)
                results, provider_used = await self.search_provider.search(
                    query, max_results=self.max_results
                )
            except Exception:
                results = []
                provider_used = "none"
            latency["search"] = round((time.monotonic() - t0) * 1000, 2)

        # --- Stage: Fetch (ranked) ---
        if results:
            # Deterministic ranking — instant, no LLM call
            ranked_results = rank_results(results, query or user_input)
            results = ranked_results  # store ranked results in TurnResult

            ordered_urls = [r.url for r in ranked_results]

            t0 = time.monotonic()
            for url in ordered_urls[:3]:
                try:
                    candidate_text, method = await self.fetcher.fetch(url, max_chars=max_context_chars)
                except Exception:
                    continue
                if not candidate_text:
                    continue

                # --- Stage: Validate ---
                t_val = time.monotonic()
                try:
                    relevant = await self.validator.is_relevant(user_input, candidate_text)
                except Exception:
                    relevant = False
                latency["validate"] += round((time.monotonic() - t_val) * 1000, 2)

                if relevant:
                    chosen_url = url
                    context = candidate_text
                    fetch_method = method
                    break
            latency["fetch"] = round((time.monotonic() - t0) * 1000, 2)

        # Build messages for Ollama
        messages = list(history)
        if chosen_url and context:
            sys_prompt = build_rag_system_prompt(chosen_url, context, max_context_chars)
            # Inject context natively as a system message so the model doesn't get confused
            messages.insert(0, {"role": "system", "content": sys_prompt})

        messages.append({"role": "user", "content": user_input})

        # --- Stage: Respond ---
        t0 = time.monotonic()
        assistant_text = await self.responder.respond(messages)
        latency["respond"] = round((time.monotonic() - t0) * 1000, 2)

        latency["total"] = round((time.monotonic() - total_start) * 1000, 2)

        return TurnResult(
            assistant_text=assistant_text,
            user_input=user_input,
            query=query,
            chosen_url=chosen_url,
            context_used=bool(chosen_url and context),
            results=results,
            provider_used=provider_used,
            fetch_method=fetch_method,
            latency=latency,
            metrics=TurnMetrics(
                search_used=use_search,
                results_count=len(results),
                context_validated=bool(chosen_url and context),
            ),
        )

"""Async pipeline orchestrator.

Owns the full turn pipeline: decision → query_gen → search → fetch → validate → respond.
Per-stage latency is tracked via time.monotonic() and returned in every TurnResult.
"""
import logging
import json
import time
from typing import Any
from dataclasses import asdict, dataclass
from .interfaces import DecisionEngine, Fetcher, QueryGenerator, Ranker, Responder, SearchProvider, Validator
from .models import SearchResult, TurnMetrics, TurnResult
from src.app.config import settings
from src.services.ranking import rank_results

MAX_CONTEXT_CHARS_DEFAULT = 4000

logger = logging.getLogger(__name__)

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
    cache: Any = None

    async def _prepare_turn(
        self,
        user_input: str,
        history: list[dict[str, str]],
        use_web: bool = True,
        max_context_chars: int = MAX_CONTEXT_CHARS_DEFAULT,
    ) -> dict:
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
        cache_hit = False

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
                cache_hit_search = False

                if self.cache:
                    cache_key = self.cache._search_key(query)
                    cached_data = await self.cache.get(cache_key)
                    if cached_data:
                        try:
                            parsed = json.loads(cached_data)
                            results = [
                                SearchResult(
                                    title=r["title"],
                                    url=r["url"],
                                    content=r.get("content", r.get("snippet", "")),
                                    source=r["source"],
                                    score=r.get("score", 0.0),
                                    snippet=r.get("snippet", "")
                                )
                                for r in parsed.get("results", [])
                            ]
                            provider_used = parsed.get("provider_used", "unknown")
                            cache_hit_search = True
                            cache_hit = True
                        except Exception as e:
                            logger.warning("Failed to parse cached search results: %s", e)

                if not cache_hit_search:
                    results, provider_used = await self.search_provider.search(
                        query, max_results=self.max_results
                    )
                    if self.cache and results:
                        cache_key = self.cache._search_key(query)
                        payload = {
                            "results": [asdict(r) for r in results],
                            "provider_used": provider_used
                        }
                        await self.cache.set(
                            cache_key,
                            json.dumps(payload),
                            settings.cache_search_ttl_seconds
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
                candidate_text = ""
                method = "none"
                cache_hit_fetch = False

                if self.cache:
                    cache_key = self.cache._fetch_key(url)
                    cached_data = await self.cache.get(cache_key)
                    if cached_data:
                        try:
                            parsed = json.loads(cached_data)
                            candidate_text = parsed.get("text", "")
                            method = parsed.get("method", "none")
                            cache_hit_fetch = True
                            cache_hit = True
                        except Exception as e:
                            logger.warning("Failed to parse cached fetch response: %s", e)

                if not cache_hit_fetch:
                    try:
                        candidate_text, method = await self.fetcher.fetch(url, max_chars=max_context_chars)
                    except Exception:
                        continue
                    if not candidate_text:
                        continue
                    if self.cache:
                        cache_key = self.cache._fetch_key(url)
                        payload = {"text": candidate_text, "method": method}
                        await self.cache.set(
                            cache_key,
                            json.dumps(payload),
                            settings.cache_fetch_ttl_seconds
                        )

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

            if not context and results:
                # Fallback to search snippets if no full page was successfully fetched and validated
                snippets = []
                for r in results[:5]:
                    snippets.append(f"Source: {r.url}\nTitle: {r.title}\nSnippet: {r.content}")
                context = "\n\n".join(snippets)
                chosen_url = results[0].url
                fetch_method = "search_snippets"

        # Build messages for Ollama
        messages = list(history)
        if chosen_url and context:
            sys_prompt = build_rag_system_prompt(chosen_url, context, max_context_chars)
            # Inject context natively as a system message so the model doesn't get confused
            messages.insert(0, {"role": "system", "content": sys_prompt})

        messages.append({"role": "user", "content": user_input})

        return {
            "messages": messages,
            "latency": latency,
            "total_start": total_start,
            "use_search": use_search,
            "query": query,
            "chosen_url": chosen_url,
            "context": context,
            "results": results,
            "provider_used": provider_used,
            "fetch_method": fetch_method,
            "cache_hit": cache_hit,
        }

    async def run_turn(
        self,
        user_input: str,
        history: list[dict[str, str]],
        use_web: bool = True,
        model: str | None = None,
        max_context_chars: int = MAX_CONTEXT_CHARS_DEFAULT,
    ) -> TurnResult:
        prep = await self._prepare_turn(user_input, history, use_web, max_context_chars)
        messages = prep["messages"]
        latency = prep["latency"]


        # --- Stage: Respond ---
        t0 = time.monotonic()
        assistant_text = await self.responder.respond(messages)
        latency["respond"] = round((time.monotonic() - t0) * 1000, 2)

        latency["total"] = round((time.monotonic() - prep["total_start"]) * 1000, 2)

        return TurnResult(
            assistant_text=assistant_text,
            user_input=user_input,
            query=prep["query"],
            chosen_url=prep["chosen_url"],
            context_used=bool(prep["chosen_url"] and prep["context"]),
            results=prep["results"],
            provider_used=prep["provider_used"],
            fetch_method=prep["fetch_method"],
            latency=latency,
            metrics=TurnMetrics(
                search_used=prep["use_search"],
                results_count=len(prep["results"]),
                context_validated=bool(prep["chosen_url"] and prep["context"]),
            ),
            cache_hit=prep["cache_hit"],
        )

    async def stream_turn(
        self,
        user_input: str,
        history: list[dict[str, str]],
        use_web: bool = True,
        model: str | None = None,
        max_context_chars: int = MAX_CONTEXT_CHARS_DEFAULT,
    ):
        """Yields JSON chunks with SSE-style events: type='token'|'metadata'."""
        import time
        prep = await self._prepare_turn(user_input, history, use_web, max_context_chars)
        messages = prep["messages"]
        latency = prep["latency"]
        
        # --- Stage: Respond (Stream) ---
        t0 = time.monotonic()
        
        # We can yield an initial metadata chunk with the sources, so the UI can show them immediately!
        # This is great for UX.
        initial_metadata = {
            "type": "metadata",
            "data": {
                "query": prep["query"],
                "results": [asdict(r) for r in prep["results"]],
                "chosen_url": prep["chosen_url"],
            }
        }
        yield json.dumps(initial_metadata)
        
        assistant_text = ""
        async for token in self.responder.stream_respond(messages):
            assistant_text += token
            yield json.dumps({"type": "token", "content": token})
            
        latency["respond"] = round((time.monotonic() - t0) * 1000, 2)
        latency["total"] = round((time.monotonic() - prep["total_start"]) * 1000, 2)
        
        final_metadata = {
            "type": "final",
            "data": {
                "assistant_text": assistant_text,
                "latency": latency,
                "metrics": {
                    "search_used": prep["use_search"],
                    "results_count": len(prep["results"]),
                    "context_validated": bool(prep["chosen_url"] and prep["context"])
                },
                "cache_hit": prep["cache_hit"]
            }
        }
        yield json.dumps(final_metadata)

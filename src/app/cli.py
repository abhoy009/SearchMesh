from __future__ import annotations

import argparse
import asyncio

from .config import settings
from .orchestrator import DefaultTurnOrchestrator
from src.infra.ollama_client import build_client, import_ollama, is_ready
from src.services.decision_engine import DecisionEngineService
from src.services.fetcher import FetcherService
from src.services.query_generator import QueryGeneratorService
from src.services.ranking import RankingService
from src.services.responder import ResponderService
from src.services.search_providers import FallbackSearchProvider
from src.services.validator import ValidatorService

ASSISTANT_SYSTEM_PROMPT = (
    "You are a helpful assistant with optional web context. "
    "If web context is provided, use it carefully and do not invent facts."
)


def _build_parser(default_model: str, default_debug: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local agentic web search flow with Ollama")
    parser.add_argument("query", nargs="*", help="Optional one-shot user prompt")
    parser.add_argument("--model", default=default_model, help="Model for all agent steps")
    parser.add_argument("--max-results", type=int, default=5, help="Max web search results")
    parser.add_argument("--debug", action="store_true", default=default_debug, help="Show agent step logs")
    return parser


def _build_orchestrator(ollama: object, client: object, model: str, max_results: int, debug: bool) -> DefaultTurnOrchestrator:
    return DefaultTurnOrchestrator(
        decision_engine=DecisionEngineService(client=client, model=model),
        query_generator=QueryGeneratorService(client=client, model=model),
        search_provider=FallbackSearchProvider(ollama=ollama),
        ranker=RankingService(),
        fetcher=FetcherService(ollama=ollama),
        validator=ValidatorService(client=client, model=model),
        responder=ResponderService(client=client, model=model),
        max_results=max_results,
    )


async def async_main() -> int:
    default_model = settings.ollama_model or settings.response_model
    parser = _build_parser(default_model=default_model, default_debug=settings.agent_debug)
    args = parser.parse_args()

    ollama = import_ollama()
    client = build_client(ollama)
    if not is_ready(client):
        print("[agent] Ollama is not running or unreachable.")
        print("[agent] Start it with: ollama serve")
        return 0

    import httpx
    from src.infra import http as http_module

    async_client = httpx.AsyncClient(timeout=30.0)
    http_module.set_http_client(async_client)

    try:
        orchestrator = _build_orchestrator(
            ollama=ollama,
            client=client,
            model=args.model,
            max_results=args.max_results,
            debug=args.debug,
        )
        history: list[dict[str, str]] = [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT}]

        first_query = " ".join(args.query).strip()
        if first_query:
            result = await orchestrator.run_turn(first_query, history)
            print(result.assistant_text)
            return 0

        print("Chat started. Type 'exit' or 'quit' to stop.")
        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting chat.")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                print("Exiting chat.")
                break

            result = await orchestrator.run_turn(user_input, history)
            print(f"\nAssistant: {result.assistant_text}\n")
            # Update history
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": result.assistant_text})

        return 0
    finally:
        await async_client.aclose()


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nExiting chat.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

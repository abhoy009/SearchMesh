import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

import trafilatura
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ASSISTANT_SYSTEM_PROMPT = (
    "You are a helpful assistant with optional web context. "
    "If web context is provided, use it carefully and do not invent facts."
)

SEARCH_OR_NOT_PROMPT = (
    "You decide whether web search is needed for the user message. "
    "Reply with exactly one token: True or False. "
    "Return True for current events, prices, weather, schedules, releases, or any fact likely to change. "
    "Return False for reasoning, coding, writing, math, and stable knowledge."
)

QUERY_GENERATION_PROMPT = (
    "Generate one concise search query for the user message. "
    "Return only the query text."
)

BEST_RESULT_PROMPT = (
    "Pick the single best URL from candidate web search results for answering the user message. "
    "Return exactly one URL and nothing else."
)

DATA_VALIDATION_PROMPT = (
    "You are a strict validator. Decide if the provided web context is relevant and useful "
    "for answering the user message. Reply exactly True or False."
)

MAX_CONTEXT_CHARS = 6000
MAX_VALIDATION_CHARS = 4000


def _import_ollama() -> Any:
    try:
        import ollama

        return ollama
    except Exception as exc:
        raise RuntimeError("Install/update ollama python package: pip install -U 'ollama>=0.6.0'") from exc


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def _bool_from_text(text: str) -> bool:
    return text.strip().lower().startswith("true")


def _http_get(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def _normalize_ddg_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = urllib.parse.parse_qs(parsed.query)
        return urllib.parse.unquote(query.get("uddg", [""])[0])
    return url


def _build_chat_client(ollama: Any) -> Any:
    host = os.getenv("OLLAMA_HOST", "").strip()
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()

    if host and api_key:
        return ollama.Client(host=host, headers={"Authorization": f"Bearer {api_key}"})
    if host:
        return ollama.Client(host=host)
    if api_key:
        return ollama.Client(headers={"Authorization": f"Bearer {api_key}"})
    return ollama.Client()


def ollama_ready(client: Any) -> bool:
    try:
        client.ps()
        return True
    except Exception:
        return False


def search_or_not_agent(client: Any, model: str, user_prompt: str) -> bool:
    prompt = user_prompt.strip().lower()
    # Fast path: avoid needless web search for obvious non-web prompts.
    if prompt in {"hi", "hello", "hey"}:
        return False
    if re.fullmatch(r"[0-9\\s\\+\\-\\*\\/\\(\\)\\.\\=]+", prompt):
        return False

    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": SEARCH_OR_NOT_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _bool_from_text(_message_content(response.message))


def query_generator_agent(client: Any, model: str, user_prompt: str) -> str:
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": QUERY_GENERATION_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    query = _message_content(response.message).strip().strip('"')
    return query or user_prompt


def _parse_ollama_results(response: Any) -> list[dict[str, str]]:
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    elif isinstance(response, dict):
        payload = response
    else:
        payload = {"results": response}

    results = payload.get("results", []) if isinstance(payload, dict) else []
    clean: list[dict[str, str]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip()
        url = str(item.get("url", "") or "").strip()
        content = str(item.get("content", "") or "").strip()
        if url:
            clean.append({"title": title, "url": url, "content": content})

    return clean


def _serper_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    serper_api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not serper_api_key:
        return []

    payload = json.dumps({"q": query, "num": max_results}).encode("utf-8")
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=payload,
        method="POST",
        headers={
            "X-API-KEY": serper_api_key,
            "Content-Type": "application/json",
            "User-Agent": "agent-search/1.0",
        },
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read().decode("utf-8", errors="ignore")

    data = json.loads(raw)
    results: list[dict[str, str]] = []
    for item in data.get("organic", []):
        title = str(item.get("title", "") or "").strip()
        url = str(item.get("link", "") or "").strip()
        snippet = str(item.get("snippet", "") or "").strip()
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "content": snippet})
        if len(results) >= max_results:
            break

    return results


def _duckduckgo_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    encoded = urllib.parse.quote_plus(query)
    html = _http_get(f"https://duckduckgo.com/html/?q={encoded}")
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []

    for node in soup.select(".result"):
        anchor = node.select_one("a.result__a")
        if anchor is None:
            continue

        url = _normalize_ddg_url(anchor.get("href", "").strip())
        title = anchor.get_text(" ", strip=True)
        snippet_node = node.select_one(".result__snippet")
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""

        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "content": snippet})
        if len(results) >= max_results:
            break

    return results


def search_engine_results_scraper(ollama: Any, query: str, max_results: int) -> list[dict[str, str]]:
    # Tier 1: Ollama native web_search (newest)
    try:
        web_search = getattr(ollama, "web_search", None)
        if web_search:
            results = _parse_ollama_results(web_search(query=query, max_results=max_results))
            if results:
                return results
    except Exception:
        pass

    # Tier 2: Serper (best quality, needs API key)
    try:
        results = _serper_search(query, max_results=max_results)
        if results:
            return results
    except Exception:
        pass

    # Tier 3: DuckDuckGo (free fallback)
    return _duckduckgo_search(query, max_results=max_results)


def best_search_result_agent(client: Any, model: str, user_prompt: str, results: list[dict[str, str]]) -> str | None:
    if not results:
        return None

    formatted = json.dumps(results, ensure_ascii=True, indent=2)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": BEST_RESULT_PROMPT},
            {
                "role": "user",
                "content": f"User prompt: {user_prompt}\n\nCandidate results:\n{formatted}",
            },
        ],
    )

    raw = _message_content(response.message).strip()
    if not raw:
        return results[0]["url"]

    token = raw.split()[0]
    for item in results:
        if item["url"] == token:
            return token

    for item in results:
        if item["url"] in raw:
            return item["url"]

    return results[0]["url"]


def _web_fetch_content(ollama: Any, url: str) -> str:
    web_fetch = getattr(ollama, "web_fetch", None)
    if web_fetch is None:
        return ""

    try:
        response = web_fetch(url)
    except Exception:
        return ""

    if hasattr(response, "model_dump"):
        payload = response.model_dump()
        return str(payload.get("content", "") or "").strip()

    content = getattr(response, "content", "")
    return str(content or "").strip()


def best_result_scraper(ollama: Any, url: str) -> str:
    content = _web_fetch_content(ollama, url)
    if content:
        return content

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return ""

    extracted = trafilatura.extract(downloaded, include_links=False, include_images=False)
    return (extracted or "").strip()


def data_validation_agent(client: Any, model: str, user_prompt: str, context: str) -> bool:
    if not context:
        return False

    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": DATA_VALIDATION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"User prompt: {user_prompt}\n\n"
                    f"Web context:\n{context[:MAX_VALIDATION_CHARS]}"
                ),
            },
        ],
    )
    return _bool_from_text(_message_content(response.message))


def add_context_to_user_prompt(user_prompt: str, source_url: str, context: str) -> str:
    return (
        f"{user_prompt}\n\n"
        "Use this web context only if relevant:\n"
        f"SOURCE_URL: {source_url}\n"
        f"WEB_CONTEXT:\n{context[:MAX_CONTEXT_CHARS]}"
    )


def stream_assistant_response(client: Any, model: str, messages: list[dict[str, str]]) -> str:
    stream = client.chat(model=model, messages=messages, stream=True)

    collected: list[str] = []
    print("Assistant: ", end="", flush=True)
    for chunk in stream:
        text = _message_content(chunk.message)
        if text:
            print(text, end="", flush=True)
            collected.append(text)
    print()

    return "".join(collected)


def run_turn(
    ollama: Any,
    client: Any,
    model: str,
    user_input: str,
    history: list[dict[str, str]],
    max_results: int,
    debug: bool,
) -> None:
    if not ollama_ready(client):
        print("[agent] Ollama is not running or unreachable.")
        print("[agent] Start it with: ollama serve")
        return

    use_search = False
    query = ""
    chosen_url: str | None = None
    context = ""

    try:
        use_search = search_or_not_agent(client, model, user_input)
        if debug:
            print(f"[agent] search_or_not={use_search}")
    except Exception as exc:
        if debug:
            print(f"[agent] search_or_not failed: {exc}")

    if use_search:
        try:
            query = query_generator_agent(client, model, user_input)
            if debug:
                print(f"[agent] query={query}")

            results = search_engine_results_scraper(ollama, query, max_results=max_results)
            if debug:
                print(f"[agent] results={len(results)}")

            if results:
                best_url = best_search_result_agent(client, model, user_input, results)
                ordered_urls: list[str] = []
                if best_url:
                    ordered_urls.append(best_url)
                for item in results:
                    if item["url"] not in ordered_urls:
                        ordered_urls.append(item["url"])

                for url in ordered_urls[:3]:
                    candidate_context = best_result_scraper(ollama, url)
                    if not candidate_context:
                        continue

                    if data_validation_agent(client, model, user_input, candidate_context):
                        chosen_url = url
                        context = candidate_context
                        if debug:
                            print(f"[agent] context validated from: {url}")
                        break

                if debug and not context:
                    print("[agent] no validated context found")
        except Exception as exc:
            if debug:
                print(f"[agent] web pipeline failed: {exc}")

    user_payload = add_context_to_user_prompt(user_input, chosen_url, context) if (chosen_url and context) else user_input

    messages = history + [{"role": "user", "content": user_payload}]

    try:
        assistant_text = stream_assistant_response(client, model, messages)
    except Exception as exc:
        print(f"[agent] assistant response failed: {exc}")
        return

    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": assistant_text})


def main() -> int:
    load_dotenv()

    default_model = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b").strip() or "qwen2.5:0.5b"
    default_debug = os.getenv("AGENT_DEBUG", "1").strip().lower() not in {"0", "false", "no", "off"}

    parser = argparse.ArgumentParser(description="Local agentic web search flow with Ollama")
    parser.add_argument("query", nargs="*", help="Optional one-shot user prompt")
    parser.add_argument("--model", default=default_model, help="Model for all agent steps")
    parser.add_argument("--max-results", type=int, default=5, help="Max web search results")
    parser.add_argument("--debug", action="store_true", default=default_debug, help="Show agent step logs")
    args = parser.parse_args()

    ollama = _import_ollama()
    client = _build_chat_client(ollama)

    history: list[dict[str, str]] = [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT}]

    first_query = " ".join(args.query).strip()
    if first_query:
        run_turn(
            ollama=ollama,
            client=client,
            model=args.model,
            user_input=first_query,
            history=history,
            max_results=args.max_results,
            debug=args.debug,
        )
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

        run_turn(
            ollama=ollama,
            client=client,
            model=args.model,
            user_input=user_input,
            history=history,
            max_results=args.max_results,
            debug=args.debug,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Decision engine — determines whether a user message needs web search."""
from __future__ import annotations

import asyncio
import re
from typing import Any

SEARCH_OR_NOT_PROMPT = (
    'Respond with only "search" or "skip".\n'
    "Output \"search\" if the question needs current web data (news, prices, live events, recent facts).\n"
    "Output \"skip\" if it can be answered from general knowledge (math, definitions, history, greetings).\n"
    "Do not output anything else."
    # "Analyze if the user query requires looking up recent information, prices, news, or dynamic facts from the internet."
)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""



def _sync_should_search(client: Any, model: str, user_input: str) -> bool:
    """Runs the Ollama call synchronously — called via asyncio.to_thread."""
    prompt = user_input.strip().lower()
    if prompt in {"hi", "hello", "hey"}:
        return False
    if re.fullmatch(r"[0-9\s\+\-\*\/\(\)\.=]+", prompt):
        return False

    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": SEARCH_OR_NOT_PROMPT},
            {"role": "user", "content": user_input},
        ],
    )
    content = _message_content(response.message).strip().lower()
    return content.startswith("search")


class DecisionEngineService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    async def should_search(self, user_input: str) -> bool:
        return await asyncio.to_thread(_sync_should_search, self.client, self.model, user_input)

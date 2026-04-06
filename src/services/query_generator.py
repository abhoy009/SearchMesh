"""Query generator — creates a concise search query from a user message."""
from __future__ import annotations

import asyncio
from typing import Any

QUERY_GENERATION_PROMPT = (
    "Rewrite the user message as a short web search query (5 words max).\n"
    "Output ONLY the query. No explanation, no quotes, no punctuation."
)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def _sync_generate(client: Any, model: str, user_input: str) -> str:
    """Sync Ollama call — executed in a thread by asyncio.to_thread."""
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": QUERY_GENERATION_PROMPT},
            {"role": "user", "content": user_input},
        ],
    )
    query = _message_content(response.message).strip().strip('"')
    return query or user_input


class QueryGeneratorService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    async def generate(self, user_input: str) -> str:
        return await asyncio.to_thread(_sync_generate, self.client, self.model, user_input)

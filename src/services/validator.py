"""Context validator — decides if fetched web content is relevant to the query."""
from __future__ import annotations

import asyncio
import json
from typing import Any

DATA_VALIDATION_PROMPT = (
    "Evaluate if the provided web context contains information relevant to answering the user prompt."
)
MAX_VALIDATION_CHARS = 4000


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""



def _sync_is_relevant(client: Any, model: str, user_input: str, context: str) -> bool:
    """Sync Ollama call — executed in a thread by asyncio.to_thread."""
    if not context:
        return False
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": DATA_VALIDATION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"User prompt: {user_input}\n\n"
                    f"Web context:\n{context[:MAX_VALIDATION_CHARS]}"
                ),
            },
        ],
        format={
            "type": "object",
            "properties": {"is_relevant": {"type": "boolean"}},
            "required": ["is_relevant"]
        }
    )
    content = _message_content(response.message)
    try:
        return bool(json.loads(content).get("is_relevant", False))
    except Exception:
        return False


class ValidatorService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    async def is_relevant(self, user_input: str, context: str) -> bool:
        if not context:
            return False
        return await asyncio.to_thread(_sync_is_relevant, self.client, self.model, user_input, context)

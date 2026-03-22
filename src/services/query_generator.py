from __future__ import annotations

from typing import Any

QUERY_GENERATION_PROMPT = (
    "Generate one concise search query for the user message. "
    "Return only the query text."
)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


class QueryGeneratorService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def generate(self, user_input: str) -> str:
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": QUERY_GENERATION_PROMPT},
                {"role": "user", "content": user_input},
            ],
        )
        query = _message_content(response.message).strip().strip('"')
        return query or user_input

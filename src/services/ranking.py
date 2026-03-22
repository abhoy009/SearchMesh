from __future__ import annotations

import json
from typing import Any

from src.app.models import SearchResult

BEST_RESULT_PROMPT = (
    "Pick the single best URL from candidate web search results for answering the user message. "
    "Return exactly one URL and nothing else."
)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


class RankingService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def pick_best(self, user_input: str, results: list[SearchResult]) -> str | None:
        if not results:
            return None

        serializable = [{"title": r.title, "url": r.url, "content": r.content} for r in results]
        formatted = json.dumps(serializable, ensure_ascii=True, indent=2)
        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": BEST_RESULT_PROMPT},
                {
                    "role": "user",
                    "content": f"User prompt: {user_input}\n\nCandidate results:\n{formatted}",
                },
            ],
        )

        raw = _message_content(response.message).strip()
        if not raw:
            return results[0].url

        token = raw.split()[0]
        for item in results:
            if item.url == token:
                return token

        for item in results:
            if item.url in raw:
                return item.url

        return results[0].url

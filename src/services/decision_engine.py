from __future__ import annotations

import re
from typing import Any

SEARCH_OR_NOT_PROMPT = (
    "You decide whether web search is needed for the user message. "
    "Reply with exactly one token: True or False. "
    "Return True for current events, prices, weather, schedules, releases, or any fact likely to change. "
    "Return False for reasoning, coding, writing, math, and stable knowledge."
)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def _bool_from_text(text: str) -> bool:
    return text.strip().lower().startswith("true")


class DecisionEngineService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def should_search(self, user_input: str) -> bool:
        prompt = user_input.strip().lower()
        if prompt in {"hi", "hello", "hey"}:
            return False
        if re.fullmatch(r"[0-9\\s\\+\\-\\*\\/\\(\\)\\.\\=]+", prompt):
            return False

        response = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": SEARCH_OR_NOT_PROMPT},
                {"role": "user", "content": user_input},
            ],
        )
        return _bool_from_text(_message_content(response.message))

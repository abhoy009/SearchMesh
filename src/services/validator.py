from __future__ import annotations

from typing import Any

DATA_VALIDATION_PROMPT = (
    "You are a strict validator. Decide if the provided web context is relevant and useful "
    "for answering the user message. Reply exactly True or False."
)
MAX_VALIDATION_CHARS = 4000


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def _bool_from_text(text: str) -> bool:
    return text.strip().lower().startswith("true")


class ValidatorService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def is_relevant(self, user_input: str, context: str) -> bool:
        if not context:
            return False

        response = self.client.chat(
            model=self.model,
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
        )
        return _bool_from_text(_message_content(response.message))

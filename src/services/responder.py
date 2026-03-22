from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class ResponderService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def stream(self, messages: Sequence[Mapping[str, str]]) -> str:
        stream = self.client.chat(model=self.model, messages=list(messages), stream=True)
        collected: list[str] = []
        print("Assistant: ", end="", flush=True)
        for chunk in stream:
            content = getattr(chunk.message, "content", "")
            text = content if isinstance(content, str) else ""
            if text:
                print(text, end="", flush=True)
                collected.append(text)
        print()
        return "".join(collected)

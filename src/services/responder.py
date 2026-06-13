"""Responder service — generates the assistant response via Ollama.

Removed the CLI print() side-effects from the original implementation.
Returns the full assembled string without any stdout output.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any


def _sync_respond(client: Any, model: str, messages: list[dict]) -> str:
    """Sync streaming call to Ollama — run in a thread."""
    stream = client.chat(model=model, messages=messages, stream=True)
    collected: list[str] = []
    for chunk in stream:
        content = getattr(chunk.message, "content", "")
        text = content if isinstance(content, str) else ""
        if text:
            collected.append(text)
    return "".join(collected)


class ResponderService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    async def respond(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Generate a response from the model. Returns full text (no streaming to caller)."""
        return await asyncio.to_thread(_sync_respond, self.client, self.model, list(messages))

    async def stream_respond(self, messages: Sequence[Mapping[str, str]]):
        """Generate a response as an async stream, wrapping the sync Ollama stream."""
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def producer():
            try:
                stream = self.client.chat(model=self.model, messages=list(messages), stream=True)
                for chunk in stream:
                    content = getattr(chunk.message, "content", "")
                    if isinstance(content, str) and content:
                        loop.call_soon_threadsafe(queue.put_nowait, content)
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)

        import threading
        threading.Thread(target=producer, daemon=True).start()

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item

"""Decision engine — determines whether a user message needs web search."""
from __future__ import annotations

import asyncio
import re
from typing import Any

SEARCH_OR_NOT_PROMPT = """You are a routing agent. Your job is to decide whether a web search is needed to answer the user's message.
Respond with EXACTLY ONE WORD: "search" or "skip".

- Output "search" for: current events, real-time data, unknown facts, weather, news, specific product prices, sports scores, match schedules, etc.
- Output "skip" for: greetings, small talk, general knowledge, math, coding, translation, summarizing provided text, or questions about who you are.

Examples:
User: "What is the capital of France?"
Assistant: skip

User: "Who won the game last night?"
Assistant: search

User: "What matches are today in FIFA World Cup?"
Assistant: search

User: "Write a python loop"
Assistant: skip

User: "What's the weather in Tokyo?"
Assistant: search

User: "Hello, who are you?"
Assistant: skip

User: "Explain how photosynthesis works"
Assistant: skip

User: "Latest stock price of AAPL"
Assistant: search
"""

# Keywords that always indicate a real-time / live-data query.
# Checked BEFORE calling the LLM to avoid mis-classification by small models.
_REALTIME_KEYWORDS = {
    "today", "tonight", "now", "live", "current", "latest", "right now",
    "this week", "this month", "score", "scores", "match", "matches",
    "fixture", "fixtures", "schedule", "result", "results", "news",
    "update", "updates", "weather", "price", "prices", "stock",
    "trending", "breaking",
}

# Regex patterns for conversational / personal messages that NEVER need a search.
# Evaluated BEFORE the LLM to avoid mis-classification by small models.
_CONVERSATIONAL_PATTERNS = re.compile(
    r"^"
    r"(?:"
    # Greetings (multi-word, with punctuation)
    r"(?:hi|hello|hey|greetings|howdy|sup|good\s+(?:morning|afternoon|evening|night))\b"
    # Self-introductions: "my name is X", "i am X", "i'm X"
    r"|(?:(?:hi|hello|hey|greetings)\b.{0,30})?(?:my\s+name\s+is|i\s+am|i'm|i\s+go\s+by)\s+\w+"
    # Feeling / status: "i feel", "i'm feeling", "i'm good", "i'm fine"
    r"|i(?:'m|\s+am)\s+(?:good|great|fine|okay|ok|bad|tired|happy|sad|excited|bored)"
    # Thanks / acknowledgements
    r"|(?:thanks|thank\s+you|thx|ty|cheers|np|no\s+problem|you're\s+welcome|ok|okay|got\s+it|sure|alright)"
    r")\b.*$",
    re.IGNORECASE,
)


def _message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""



def _sync_should_search(client: Any, model: str, user_input: str) -> bool:
    """Runs the Ollama call synchronously — called via asyncio.to_thread."""
    prompt = user_input.strip().lower()

    # Fast-path: trivially non-searchable (greetings, intros, small talk)
    if _CONVERSATIONAL_PATTERNS.match(prompt):
        return False
    if re.fullmatch(r"[0-9\s\+\-\*\/\(\)\.=]+", prompt):
        return False

    # Fast-path: obvious real-time keywords → always search without an LLM call.
    # This prevents small local models from mis-classifying live-data queries
    # (e.g. "matches today", "weather now") as general knowledge.
    prompt_words = set(re.findall(r"\w+", prompt))
    if prompt_words & _REALTIME_KEYWORDS:
        return True

    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": SEARCH_OR_NOT_PROMPT},
            {"role": "user", "content": user_input},
        ],
    )
    # Strip surrounding quotes that some small models add (e.g. '"search"' → 'search')
    content = _message_content(response.message).strip().lower().strip('"\'')
    return content.startswith("search")


class DecisionEngineService:
    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    async def should_search(self, user_input: str) -> bool:
        return await asyncio.to_thread(_sync_should_search, self.client, self.model, user_input)

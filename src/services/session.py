import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

class SessionStore:
    def __init__(self, redis: Any, ttl: int = 3600, max_turns: int = 20):
        self.redis = redis
        self.ttl = ttl
        self.max_turns = max_turns

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}"

    async def get_history(self, session_id: str) -> list[dict]:
        if not self.redis:
            return []
        try:
            raw = await self.redis.get(self._key(session_id))
            return json.loads(raw) if raw else []
        except Exception as e:
            logger.warning("Failed to get session history: %s", e)
            return []

    async def append_turn(self, session_id: str, user: str, assistant: str, sources: list = None) -> None:
        if not self.redis:
            return
        try:
            history = await self.get_history(session_id)
            history.append({"role": "user", "content": user})
            history.append({"role": "assistant", "content": assistant})
            # Cap to last N messages to bound context size (each turn has 2 messages)
            history = history[-(self.max_turns * 2):]
            await self.redis.setex(self._key(session_id), self.ttl, json.dumps(history))
        except Exception as e:
            logger.warning("Failed to append session turn: %s", e)

    async def delete(self, session_id: str) -> bool:
        if not self.redis:
            return False
        try:
            return bool(await self.redis.delete(self._key(session_id)))
        except Exception as e:
            logger.warning("Failed to delete session: %s", e)
            return False

    async def get_full_session(self, session_id: str) -> dict | None:
        if not self.redis:
            return None
        try:
            raw = await self.redis.get(self._key(session_id))
            if not raw:
                return None
            ttl = await self.redis.ttl(self._key(session_id))
            history = json.loads(raw)
            return {
                "session_id": session_id,
                "turn_count": len(history) // 2,
                "ttl_seconds": ttl,
                "turns": history
            }
        except Exception as e:
            logger.warning("Failed to get full session: %s", e)
            return None

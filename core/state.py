# core/state.py
"""Redis-backed StateAdapter implementation."""
from __future__ import annotations

import json
from typing import Any

from core.adapters import StateAdapter


class RedisStateAdapter(StateAdapter):
    """Async Redis state adapter using redis-py[asyncio].

    Install the optional dep: pip install 'redis[asyncio]'
    or: uv add --optional redis 'redis[asyncio]'
    """

    def __init__(self, url: str = "redis://localhost:6379") -> None:
        import redis.asyncio as aioredis  # lazy import — optional dep

        self._client = aioredis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any:
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        serialised = json.dumps(value)
        if ttl is not None:
            await self._client.setex(key, ttl, serialised)
        else:
            await self._client.set(key, serialised)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

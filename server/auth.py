# server/auth.py
"""API key authentication middleware for Eva gateway.

Keys stored in Redis:
    eva:apikey:<key>  →  "1"   (any truthy value = valid)

Provision a key:
    redis-cli SET "eva:apikey:eva_mykey" 1

Eva does not ship a key management API in Phase 4.
Keys are provisioned directly in Redis or via operator tooling.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.adapters import StateAdapter

# Paths exempt from auth checks
_EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/health", "/.well-known/agent.json", "/docs", "/openapi.json", "/redoc"}
)


class _NullStateAdapter(StateAdapter):
    """Fallback adapter when Redis is not configured — rejects all keys."""

    async def get(self, key: str) -> Any:
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass


def _make_state_adapter() -> StateAdapter:
    """Return a RedisStateAdapter if EVA_REDIS_URL is set, else NullStateAdapter."""
    url = os.environ.get("EVA_REDIS_URL", "")
    if url:
        try:
            from core.state import RedisStateAdapter

            return RedisStateAdapter(url=url)
        except Exception:
            pass
    return _NullStateAdapter()


# Module-level singleton — patch this in tests: `patch("server.auth.state_adapter")`
state_adapter: StateAdapter = _make_state_adapter()


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Check X-Eva-Key header against Redis for every non-exempt request."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        key = request.headers.get("X-Eva-Key")
        if not key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-Eva-Key header"},
            )

        exists = await state_adapter.get(f"eva:apikey:{key}")
        if not exists:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"},
            )

        # Attach to request.state for downstream use (e.g. rate limiting)
        request.state.api_key = key
        return await call_next(request)

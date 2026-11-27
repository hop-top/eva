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
from typing import Any, Mapping

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


# Set by `eva serve --no-auth` so child processes (uvicorn workers, reload
# subprocess) build their app unauthenticated. Not a user-facing switch.
NO_AUTH_ENV = "EVA_NO_AUTH"


class AuthNotConfiguredError(RuntimeError):
    """`eva serve` was asked to start with no key store and without --no-auth."""


def auth_enabled() -> bool:
    """True when a key store is configured (EVA_REDIS_URL set) and
    `eva serve --no-auth` has not switched auth off (EVA_NO_AUTH)."""
    if os.environ.get(NO_AUTH_ENV, ""):
        return False
    return bool(os.environ.get("EVA_REDIS_URL", ""))


def serve_auth_mode(no_auth: bool, environ: Mapping[str, str] | None = None) -> str:
    """Decide how `eva serve` handles authentication.

    Returns "disabled" (--no-auth; wins even when a key store is configured)
    or "enforced" (key store configured). Raises AuthNotConfiguredError when
    neither holds.
    """
    env = os.environ if environ is None else environ
    if no_auth:
        return "disabled"
    if env.get("EVA_REDIS_URL", ""):
        return "enforced"
    raise AuthNotConfiguredError(
        "no API key store configured. Refusing to start an unauthenticated "
        "gateway. Either configure the key store (set EVA_REDIS_URL), or pass "
        "--no-auth to serve without authentication."
    )


def _unauthorized(message: str) -> JSONResponse:
    """401 in the gateway's structured-error shape (plus legacy `detail`)."""
    return JSONResponse(
        status_code=401,
        content={
            "detail": message,
            "eva_status": "unauthorized",
            "violations": [{"field": "X-Eva-Key", "message": message}],
        },
    )


# Module-level singleton — patch this in tests: `patch("server.auth.state_adapter")`
state_adapter: StateAdapter = _make_state_adapter()


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Check X-Eva-Key header against Redis for every non-exempt request."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        key = request.headers.get("X-Eva-Key")
        if not key:
            return _unauthorized("Missing X-Eva-Key header")

        exists = await state_adapter.get(f"eva:apikey:{key}")
        if not exists:
            return _unauthorized("Invalid API key")

        # Attach to request.state for downstream use (e.g. rate limiting)
        request.state.api_key = key
        return await call_next(request)

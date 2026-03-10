# server/app.py — Eva Gateway FastAPI application
from __future__ import annotations
from typing import Callable, Sequence

from fastapi import FastAPI
from server.contracts.registry import ContractRegistry
from server.gateway.routes import router as gateway_router, set_registry


def create_app(
    registry: ContractRegistry | None = None,
    middleware_factories: Sequence[Callable] | None = None,
) -> FastAPI:
    """Create and return the Eva Gateway FastAPI application.

    Args:
        registry: Optional contract registry to wire into gateway routes.
        middleware_factories: Optional list of Starlette/FastAPI middleware
            classes to mount on the app. EE and plugins use this hook —
            CE core is not modified.
    """
    _app = FastAPI(title="Eva — Enforcement & Validation for Agents", version="1.0.0")
    if registry is not None:
        set_registry(registry)
    _app.include_router(gateway_router)

    @_app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    for factory in middleware_factories or []:
        _app.add_middleware(factory)

    return _app


app = create_app()

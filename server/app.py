# server/app.py — Eva Gateway FastAPI application
from __future__ import annotations
from fastapi import FastAPI
from server.contracts.registry import ContractRegistry
from server.gateway.routes import router as gateway_router, set_registry


def create_app(registry: ContractRegistry | None = None) -> FastAPI:
    _app = FastAPI(title="Eva Gateway", version="1.0.0")
    if registry is not None:
        set_registry(registry)
    _app.include_router(gateway_router)

    @_app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return _app


app = create_app()

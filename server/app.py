# server/app.py — Eva Gateway FastAPI application
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Callable, Sequence

from fastapi import FastAPI
from importlib.metadata import version, PackageNotFoundError
from core.config import EvaConfig, find_and_load_config
from core.llm import build_llm_adapter
from server.auth import ApiKeyMiddleware, auth_enabled
from server.contracts.registry import ContractRegistry
from server.gateway.routes import (
    router as gateway_router,
    set_judge_adapter,
    set_registry,
    set_sample_rate,
)

try:
    _VERSION = version("hop-top-eva")
except PackageNotFoundError:
    _VERSION = "0.0.0"


def create_app(
    registry: ContractRegistry | None = None,
    middleware_factories: Sequence[Callable] | None = None,
    config: EvaConfig | None = None,
    judge_adapter: Any | None = None,
) -> FastAPI:
    """Create and return the Eva Gateway FastAPI application.

    Args:
        registry: Optional contract registry to wire into gateway routes.
        middleware_factories: Optional list of Starlette/FastAPI middleware
            classes to mount on the app. EE and plugins use this hook —
            CE core is not modified.
        config: Optional pre-loaded EvaConfig. When None, config is
            discovered from eva.yaml in the working directory.
        judge_adapter: Optional pre-built judge adapter. When None, one is
            built from the judge settings (EVA_JUDGE_* env, ``judge:`` in
            eva.yaml); no model configured means judge evaluators are skipped
            per request. Raises JudgeConfigError when the settings cannot
            be built. One judge per process, shared by all requests.
    """
    cfg = config or find_and_load_config()

    _app = FastAPI(title="Eva — Enforcement & Validation for Agents", version=_VERSION)
    if registry is not None:
        set_registry(registry)
    set_sample_rate(cfg.observability.sample_rate)
    set_judge_adapter(
        judge_adapter if judge_adapter is not None else build_llm_adapter(cfg)
    )
    _app.include_router(gateway_router)

    @_app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    for factory in middleware_factories or []:
        _app.add_middleware(factory)

    # With a key store configured, API-key auth is applied here so no gateway
    # route is reachable without it. Added last = outermost, so it runs before
    # any factory-supplied middleware (e.g. per-key rate limiting).
    if auth_enabled() and ApiKeyMiddleware not in (middleware_factories or []):
        _app.add_middleware(ApiKeyMiddleware)

    return _app


# Internal handoff from `eva serve` to processes that build their own app
# (uvicorn workers, reload subprocess). Set by the CLI; not a user setting.
SERVE_CONTRACTS_DIR_ENV = "EVA_SERVE_CONTRACTS_DIR"


def create_serve_app() -> FastAPI:
    """App factory for `eva serve` worker/reload processes.

    Uvicorn needs an import string (not an app object) for multiple workers
    or reload; each such process calls this to build its own app.
    """
    registry = ContractRegistry()
    contracts_dir = os.environ.get(SERVE_CONTRACTS_DIR_ENV, "")
    if contracts_dir and Path(contracts_dir).exists():
        registry.load_dir(Path(contracts_dir))
    return create_app(registry=registry)


app = create_app()

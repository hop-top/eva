# tests/server/test_app_factory.py
"""Tests for create_app() middleware_factories extension hook (T-0090)."""
import pytest
from httpx import AsyncClient, ASGITransport
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from server.app import create_app


class _TrackingMiddleware(BaseHTTPMiddleware):
    """Records that it was invoked."""

    invoked: list[str] = []

    async def dispatch(self, request: Request, call_next):
        _TrackingMiddleware.invoked.append(request.url.path)
        return await call_next(request)


@pytest.fixture(autouse=True)
def _reset_tracking():
    _TrackingMiddleware.invoked.clear()
    yield
    _TrackingMiddleware.invoked.clear()


@pytest.mark.asyncio
async def test_middleware_factory_is_called_on_request():
    """Middleware passed via middleware_factories must be invoked."""
    app = create_app(middleware_factories=[_TrackingMiddleware])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/health")
    assert "/health" in _TrackingMiddleware.invoked


@pytest.mark.asyncio
async def test_no_middleware_factories_no_regression():
    """create_app() with no args must behave identically to the original."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_none_middleware_factories_treated_as_empty():
    """Explicit None must not raise."""
    app = create_app(middleware_factories=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_multiple_middleware_factories_all_invoked():
    """All factories in the list must be applied."""
    calls: list[str] = []

    class Mid1(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            calls.append("mid1")
            return await call_next(request)

    class Mid2(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            calls.append("mid2")
            return await call_next(request)

    app = create_app(middleware_factories=[Mid1, Mid2])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/health")

    assert "mid1" in calls
    assert "mid2" in calls

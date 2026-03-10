"""
End-to-end: Eva Gateway talking to a real echo target (ASGI, in-process).
No external process needed. Verifies proxy -> evaluate -> return flow.
"""
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

# A minimal echo agent that echoes the message field and the hint if present
echo_app = FastAPI()


@echo_app.post("/respond")
async def respond(body: dict) -> dict:
    return {"echo": body.get("message", ""), "hint": body.get("_eva_hint")}


@pytest.mark.asyncio
async def test_proxy_pass_through_e2e():
    # US-010: As Sam, I want per-request evaluator configuration on the `/v1/proxy` endpoint
    # so that each integration can enforce its own quality contract at runtime.
    """Eva proxy -> echo agent -> contains evaluator passes -> 200 pass."""
    from server.app import create_app
    from server.contracts.registry import ContractRegistry
    from server.gateway.proxy import ProxyResponse

    registry = ContractRegistry()
    eva_app = create_app(registry=registry)

    async def fake_forward(target, body, headers, timeout=30.0):
        async with AsyncClient(
            transport=ASGITransport(app=echo_app), base_url="http://echo"
        ) as c:
            resp = await c.post("/respond", json=body)
        return ProxyResponse(
            status_code=resp.status_code,
            text=resp.text,
            headers=dict(resp.headers),
        )

    with patch("server.gateway.routes.forward_request", side_effect=fake_forward):
        async with AsyncClient(
            transport=ASGITransport(app=eva_app), base_url="http://eva"
        ) as client:
            resp = await client.post(
                "/v1/proxy",
                json={
                    "target": "http://echo/respond",
                    "body": {"message": "hello"},
                    "evaluators": [
                        {"name": "contains", "mode": "binary", "config": {"substring": "hello"}}
                    ],
                    "max_retries": 0,
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["eva_status"] == "pass"
    assert data["response"]["echo"] == "hello"


@pytest.mark.asyncio
async def test_proxy_retry_with_hint_e2e():
    # US-008: As Sam, I want the proxy to retry failed requests with injected hints so that
    # transient LLM quality failures are recovered without client involvement.
    """
    Eva proxy retries when evaluator fails, injects hint as _eva_hint.
    Echo agent returns _eva_hint value in response body.
    Contains evaluator finds MAGIC in the retry response — passes.
    """
    from server.app import create_app
    from server.contracts.registry import ContractRegistry
    from server.gateway.proxy import ProxyResponse

    registry = ContractRegistry()
    eva_app = create_app(registry=registry)
    call_count = [0]

    async def fake_forward(target, body, headers, timeout=30.0):
        call_count[0] += 1
        async with AsyncClient(
            transport=ASGITransport(app=echo_app), base_url="http://echo"
        ) as c:
            resp = await c.post("/respond", json=body)
        return ProxyResponse(
            status_code=resp.status_code,
            text=resp.text,
            headers=dict(resp.headers),
        )

    with patch("server.gateway.routes.forward_request", side_effect=fake_forward):
        async with AsyncClient(
            transport=ASGITransport(app=eva_app), base_url="http://eva"
        ) as client:
            resp = await client.post(
                "/v1/proxy",
                json={
                    "target": "http://echo/respond",
                    "body": {"message": "hi"},
                    # evaluator looks for MAGIC — first call won't have it, retry will
                    "evaluators": [
                        {"name": "contains", "mode": "binary", "config": {"substring": "MAGIC"}}
                    ],
                    "max_retries": 1,
                    "hint": "MAGIC",
                },
            )

    # On retry body includes _eva_hint="MAGIC", echo returns {"hint": "MAGIC"}, contains finds "MAGIC"
    assert resp.status_code == 200
    data = resp.json()
    assert data["eva_status"] == "pass"
    assert data["attempts"] == 2
    assert call_count[0] == 2

"""Tests for eva-agntcy: ACP manifest endpoint + OASF local registry."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from core.models import Contract, EvaluatorRef, RetryPolicy


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_test_app() -> FastAPI:
    from eva_agntcy.acp import acp_router
    app = FastAPI()
    app.include_router(acp_router)
    return app


def make_contract() -> Contract:
    return Contract(
        name="billing_contract",
        provider="billing-agent",
        consumer="support-agent",
        request_schema={"type": "object"},
        evaluators=[EvaluatorRef(name="relevance", mode="threshold", min_score=0.7)],
        retry_policy=RetryPolicy(max_retries=2),
    )


# ── ACP manifest endpoint tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_well_known_agent_json_returns_200():
    async with AsyncClient(
        transport=ASGITransport(app=make_test_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/.well-known/agent.json")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_manifest_content_type_is_json():
    async with AsyncClient(
        transport=ASGITransport(app=make_test_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/.well-known/agent.json")
    assert "application/json" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_manifest_has_required_acp_fields():
    async with AsyncClient(
        transport=ASGITransport(app=make_test_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/.well-known/agent.json")
    body = resp.json()
    assert "schema_version" in body
    assert "name" in body
    assert "description" in body
    assert "capabilities" in body
    assert "endpoints" in body


@pytest.mark.asyncio
async def test_manifest_endpoints_include_proxy_and_invoke():
    async with AsyncClient(
        transport=ASGITransport(app=make_test_app()), base_url="http://test"
    ) as client:
        resp = await client.get("/.well-known/agent.json")
    endpoints = resp.json()["endpoints"]
    paths = [e.get("url", e.get("path", "")) for e in endpoints]
    assert any("proxy" in p for p in paths)
    assert any("invoke" in p for p in paths)


def test_build_manifest_returns_valid_structure():
    from eva_agntcy.acp import build_manifest
    m = build_manifest(base_url="https://eva.example.com")
    assert m["name"] == "eva-gateway"
    assert "https://eva.example.com/v1/proxy" in str(m["endpoints"])
    assert "https://eva.example.com/v1/contract/invoke" in str(m["endpoints"])


def test_build_manifest_schema_version():
    from eva_agntcy.acp import build_manifest
    m = build_manifest()
    assert m["schema_version"] == "1.0"


def test_build_manifest_has_capabilities_list():
    from eva_agntcy.acp import build_manifest
    m = build_manifest()
    assert isinstance(m["capabilities"], list)
    assert len(m["capabilities"]) > 0


# ── OASF registry tests ───────────────────────────────────────────────────────

def test_register_agent_returns_oasf_dict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from eva_agntcy import oasf
    oasf._registry.clear()
    entry = oasf.register_agent(make_contract())
    assert entry["agent_id"] == "billing-agent"
    assert entry["name"] == "billing_contract"
    assert len(entry["evaluators"]) == 1
    assert entry["evaluators"][0]["name"] == "relevance"


def test_registered_agent_appears_in_registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from eva_agntcy import oasf
    oasf._registry.clear()
    contract = make_contract()
    oasf.register_agent(contract)
    registry = oasf.get_registry()
    assert contract.name in registry


def test_slim_send_raises_not_implemented():
    from eva_agntcy.oasf import SLIMNotImplementedError, slim_send
    with pytest.raises(SLIMNotImplementedError):
        slim_send("any-agent", {"payload": "data"})


def test_oasf_registry_flushes_to_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from eva_agntcy import oasf
    oasf._registry.clear()
    oasf.register_agent(make_contract())
    registry_file = tmp_path / "oasf_registry.json"
    assert registry_file.exists()


# ── Registry client tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_registry_client_posts_manifest(monkeypatch):
    """RegistryClient.register() POSTs to the configured URL."""
    import httpx
    from unittest.mock import AsyncMock, MagicMock, patch

    posted = {}

    async def fake_post(url, json=None, **kwargs):
        posted["url"] = url
        posted["json"] = json
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    with patch.dict("os.environ", {"EVA_AGNTCY_REGISTRY_URL": "https://registry.agntcy.org"}):
        from eva_agntcy.registry import RegistryClient
        client = RegistryClient()

        with patch.object(client._http, "post", side_effect=fake_post):
            manifest = {"name": "eva-gateway", "version": "0.4.0"}
            await client.register(manifest)

    assert posted["url"] == "https://registry.agntcy.org/agents"
    assert posted["json"]["name"] == "eva-gateway"


@pytest.mark.asyncio
async def test_registry_client_missing_url_skips_silently(monkeypatch):
    """When EVA_AGNTCY_REGISTRY_URL is unset, registration is a no-op."""
    import os
    monkeypatch.delenv("EVA_AGNTCY_REGISTRY_URL", raising=False)

    from eva_agntcy.registry import RegistryClient
    client = RegistryClient()
    # Should not raise even though no URL is configured
    await client.register({"name": "eva-gateway"})


# ── Plugin registration tests ─────────────────────────────────────────────────

def test_plugin_register_mounts_router():
    """eva_agntcy.register(app) installs the ACP router."""
    app = FastAPI()
    from eva_agntcy import register
    register(app)
    routes = [r.path for r in app.routes]
    assert "/.well-known/agent.json" in routes

# tests/server/test_gateway_source_usage.py
"""Gateway invocation source per route, usage keyed by invocation id, app wiring."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, select

from core.storage import EvaluatorResultRecord, InvocationRecord, SqliteStorage, UsageRecordRecord
from server.app import SERVE_DB_ENV, create_app, create_serve_app
from server.contracts.registry import ContractRegistry
from server.gateway import routes as gateway_routes

REPLY = json.dumps(
    {
        "answer": "hello",
        "model": "prov/m1",
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    }
)


def _resp(text: str):
    from server.gateway.proxy import ProxyResponse

    return ProxyResponse(status_code=200, text=text, headers={})


@pytest.fixture
def storage(tmp_path):
    return SqliteStorage(db_url=f"sqlite:///{tmp_path}/gw.db")


@pytest.fixture
def registry(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text(
        yaml.dump(
            {
                "name": "c",
                "provider": "http://agent/respond",
                "request_schema": {"type": "object"},
                "evaluators": [],
            }
        )
    )
    reg = ContractRegistry()
    reg.load_file(f)
    return reg


@pytest.fixture(autouse=True)
def _detach():
    yield
    gateway_routes.set_storage(None)
    gateway_routes.set_sample_rate(1.0)


async def _post(app, path: str, payload: dict):
    with patch(
        "server.gateway.routes.forward_request", new_callable=AsyncMock
    ) as fwd:
        fwd.return_value = _resp(REPLY)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(path, json=payload)


def _rows(storage, model):
    with Session(storage.engine) as s:
        return s.exec(select(model)).all()


@pytest.mark.asyncio
async def test_proxy_source_is_gateway_proxy(storage):
    app = create_app(storage=storage)
    r = await _post(
        app,
        "/v1/proxy",
        {"target": "http://agent/x", "body": {"q": "hi"}, "evaluators": []},
    )
    assert r.status_code == 200
    (row,) = _rows(storage, InvocationRecord)
    assert row.source == "gateway_proxy"


@pytest.mark.asyncio
async def test_invoke_source_is_contract_invoke(storage, registry):
    app = create_app(registry=registry, storage=storage)
    r = await _post(app, "/v1/contract/invoke", {"contract": "c", "body": {"q": "hi"}})
    assert r.status_code == 200
    (row,) = _rows(storage, InvocationRecord)
    assert row.source == "contract_invoke"
    assert row.contract_name == "c"


@pytest.mark.asyncio
async def test_invoke_usage_keyed_by_invocation_id(storage, registry):
    app = create_app(registry=registry, storage=storage)
    r = await _post(app, "/v1/contract/invoke", {"contract": "c", "body": {"q": "hi"}})
    request_id = r.json()["request_id"]
    (inv,) = _rows(storage, InvocationRecord)
    (usage,) = _rows(storage, UsageRecordRecord)
    assert usage.invocation_id == inv.invocation_id
    assert usage.invocation_id != request_id
    assert inv.request_id == request_id
    assert usage.total_tokens == 7


@pytest.mark.asyncio
async def test_evaluate_persists_nothing(storage, registry):
    app = create_app(registry=registry, storage=storage)
    r = await _post(app, "/v1/contract/evaluate", {"contract": "c", "output": "x"})
    assert r.status_code == 200
    assert _rows(storage, InvocationRecord) == []
    assert _rows(storage, UsageRecordRecord) == []


@pytest.mark.asyncio
async def test_create_app_without_storage_records_nothing(registry):
    app = create_app(registry=registry)
    r = await _post(app, "/v1/contract/invoke", {"contract": "c", "body": {"q": "hi"}})
    assert r.status_code == 200
    assert gateway_routes._storage is None


def test_create_app_storage_param_wires_gateway(storage):
    create_app(storage=storage)
    assert gateway_routes._storage is storage


def test_create_serve_app_wires_storage_from_env(tmp_path, monkeypatch):
    db = tmp_path / "sub" / "w.db"
    monkeypatch.setenv(SERVE_DB_ENV, str(db))
    create_serve_app()
    assert gateway_routes._storage is not None
    assert db.exists()


def test_create_serve_app_defaults_to_eva_state_db(tmp_path, monkeypatch):
    monkeypatch.delenv(SERVE_DB_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    create_serve_app()
    assert (tmp_path / ".eva" / "state.db").exists()


@pytest.mark.asyncio
async def test_failed_gateway_call_persists_failing_evaluator_result(storage):
    app = create_app(storage=storage)
    r = await _post(
        app,
        "/v1/proxy",
        {
            "target": "http://agent/x",
            "body": {"q": "hi"},
            "evaluators": [{"name": "contains", "config": {"substring": "NOPE-ZZZ"}}],
            "max_retries": 0,
        },
    )
    assert r.status_code == 422
    (inv,) = _rows(storage, InvocationRecord)
    (ev,) = _rows(storage, EvaluatorResultRecord)
    assert inv.status == "fail"
    assert ev.invocation_id == inv.invocation_id
    assert ev.evaluator == "contains" and ev.passed is False

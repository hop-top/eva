# Phase 3: Eva Server + Official Plugins — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Production gateway operational. `eva serve` starts a FastAPI gateway that enforces behavioral contracts on live traffic — validating requests, evaluating responses, retrying with hint injection, and returning structured errors on violation. Four official plugin packages published: `eva-postgres`, `eva-otlp`, `eva-a2a`, `eva-mcp`.

**Architecture:** The server lives at `server/` inside the monorepo (not `eva_server/`). It imports from `core/` directly. Plugins live at `plugins/<name>/` — each is a separate installable package with its own `pyproject.toml`. The server has three sub-packages: `server/gateway/` (request interception, retry, self-healing), `server/contracts/` (registry, hot-reload), and `server/queue/` (ARQ workers for async eval). Tests use `httpx.AsyncClient` against a live `TestClient`. All tests are written before implementation (TDD: Red then Green).

**Dependencies introduced in Phase 3:**
- `fastapi>=0.111` — HTTP framework
- `uvicorn[standard]>=0.30` — ASGI server
- `httpx>=0.27` — async HTTP client (proxy forwarding + test client)
- `arq>=0.26` — async task queue (requires Redis)
- `watchfiles>=0.21` — file watching for contract hot-reload
- `redis>=5` — ARQ state backend
- **Redis is required for ARQ async evaluation mode.** Run locally: `docker run -p 6379:6379 redis:7-alpine`. Inline (sync) mode works without Redis.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, ARQ, Redis, watchfiles, jsonschema, pluggy, pytest, pytest-asyncio, uv

---

## Section A — Eva Server

---

### Task 1: Server package scaffold

**Files:**
- Create: `server/__init__.py`
- Create: `server/py.typed` — Required to mark the server package as PEP 561 typed — consumers get type checking support.
- Create: `server/app.py`
- Create: `server/gateway/__init__.py`
- Create: `server/contracts/__init__.py`
- Create: `server/queue/__init__.py`
- Edit: `pyproject.toml` — add server extras + `eva serve` script entry point
- Create: `tests/server/__init__.py`

**Step 1: Add server dependencies to pyproject.toml**

```toml
# pyproject.toml — add under [project.optional-dependencies]
[project.optional-dependencies]
server = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "arq>=0.26",
    "watchfiles>=0.21",
    "redis>=5",
]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "anyio[trio]>=4",
]
```

**Step 2: Create minimal server package files**

```python
# server/__init__.py
# server/py.typed  (empty)
# server/gateway/__init__.py
# server/contracts/__init__.py
# server/queue/__init__.py
# tests/server/__init__.py
```

**Step 3: Create the minimal FastAPI app**

```python
# server/app.py
from fastapi import FastAPI

app = FastAPI(title="Eva Gateway", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

**Step 4: Install server extras**

```bash
uv pip install -e ".[server,dev]"
```

Expected: no errors. `python -c "from server.app import app; print(app.title)"` prints `Eva Gateway`.

**Step 5: Write smoke test**

```python
# tests/server/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from server.app import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

```bash
pytest tests/server/test_health.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add server/ tests/server/ pyproject.toml
git commit -m "feat(server): FastAPI app scaffold with /health endpoint"
```

---

### Task 2: Contract registry

**Files:**
- Create: `server/contracts/registry.py`
- Create: `tests/server/test_registry.py`
- Create: `tests/fixtures/contracts/echo_agent.yaml`

**Step 1: Create fixture contract**

```yaml
# tests/fixtures/contracts/echo_agent.yaml
name: echo_agent
provider: echo-agent
request_schema:
  type: object
  required: [message]
  properties:
    message:
      type: string
evaluators:
  - name: contains
    mode: binary
retry_policy:
  max_retries: 2
  hint: "Respond with the original message echoed back"
  backoff_ms: 100
```

**Step 2: Write failing tests**

```python
# tests/server/test_registry.py
import pytest
from pathlib import Path
from server.contracts.registry import ContractRegistry

FIXTURES = Path("tests/fixtures/contracts")


def test_load_single_contract():
    registry = ContractRegistry()
    registry.load_file(FIXTURES / "echo_agent.yaml")
    contract = registry.get("echo_agent")
    assert contract is not None
    assert contract.name == "echo_agent"
    assert contract.provider == "echo-agent"


def test_get_missing_returns_none():
    registry = ContractRegistry()
    assert registry.get("does_not_exist") is None


def test_load_directory_loads_all_yaml():
    registry = ContractRegistry()
    registry.load_dir(FIXTURES)
    # fixtures dir has at least valid.yaml and echo_agent.yaml
    assert len(registry.all()) >= 2


def test_reload_updates_contract(tmp_path):
    import yaml
    contract_data = {
        "name": "dynamic",
        "provider": "agent-x",
        "request_schema": {"type": "object"},
        "evaluators": [],
        "retry_policy": {"max_retries": 1},
    }
    f = tmp_path / "dynamic.yaml"
    f.write_text(yaml.dump(contract_data))
    registry = ContractRegistry()
    registry.load_file(f)
    assert registry.get("dynamic").retry_policy.max_retries == 1

    # Update file and reload
    contract_data["retry_policy"]["max_retries"] = 5
    f.write_text(yaml.dump(contract_data))
    registry.load_file(f)
    assert registry.get("dynamic").retry_policy.max_retries == 5


def test_list_returns_all_names():
    registry = ContractRegistry()
    registry.load_file(FIXTURES / "echo_agent.yaml")
    names = registry.list_names()
    assert "echo_agent" in names
```

**Step 3: Run tests to verify they fail**

```bash
pytest tests/server/test_registry.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.contracts.registry'`

**Step 4: Implement the registry**

```python
# server/contracts/registry.py
from __future__ import annotations
from pathlib import Path
from core.contract import load_contract
from core.models import Contract


class ContractRegistry:
    """In-memory contract registry. Thread-safe for reads; reload is not concurrent."""

    def __init__(self) -> None:
        self._contracts: dict[str, Contract] = {}

    def load_file(self, path: Path) -> None:
        contract = load_contract(path)
        self._contracts[contract.name] = contract

    def load_dir(self, directory: Path) -> None:
        for yaml_file in sorted(directory.glob("*.yaml")):
            try:
                self.load_file(yaml_file)
            except Exception as exc:
                import warnings
                warnings.warn(f"Skipping {yaml_file}: {exc}")

    def get(self, name: str) -> Contract | None:
        return self._contracts.get(name)

    def all(self) -> list[Contract]:
        return list(self._contracts.values())

    def list_names(self) -> list[str]:
        return list(self._contracts.keys())
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/server/test_registry.py -v
```

Expected: all PASS.

**Step 6: Commit**

```bash
git add server/contracts/registry.py tests/server/test_registry.py tests/fixtures/contracts/echo_agent.yaml
git commit -m "feat(server): contract registry — load, reload, directory scan"
```

---

### Task 3: Contract registry hot-reload (file watching)

**Files:**
- Edit: `server/contracts/registry.py` — add `watch_dir` async method
- Create: `tests/server/test_registry_hotreload.py`

**Step 1: Write failing tests**

```python
# tests/server/test_registry_hotreload.py
import asyncio
import pytest
import yaml
from pathlib import Path
from server.contracts.registry import ContractRegistry


@pytest.mark.asyncio
async def test_watch_dir_reloads_on_change(tmp_path):
    """Registry picks up a new file written after watch starts."""
    contract_data = {
        "name": "hot_contract",
        "provider": "agent-hot",
        "request_schema": {"type": "object"},
        "evaluators": [],
        "retry_policy": {"max_retries": 1},
    }

    registry = ContractRegistry()

    # Start watcher as a background task
    watch_task = asyncio.create_task(registry.watch_dir(tmp_path))

    # Give the watcher time to start
    await asyncio.sleep(0.1)

    # Write a new contract file
    f = tmp_path / "hot_contract.yaml"
    f.write_text(yaml.dump(contract_data))

    # Poll for up to 3s for the registry to pick it up
    for _ in range(30):
        await asyncio.sleep(0.1)
        if registry.get("hot_contract") is not None:
            break

    watch_task.cancel()
    try:
        await watch_task
    except asyncio.CancelledError:
        pass

    assert registry.get("hot_contract") is not None
    assert registry.get("hot_contract").provider == "agent-hot"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_registry_hotreload.py -v
```

Expected: `AttributeError: 'ContractRegistry' object has no attribute 'watch_dir'`

**Step 3: Add watch_dir to registry**

```python
# server/contracts/registry.py — add after load_dir method

    async def watch_dir(self, directory: Path) -> None:
        """Watch a directory for YAML changes and hot-reload. Runs forever until cancelled."""
        from watchfiles import awatch
        async for changes in awatch(str(directory)):
            for change_type, path_str in changes:
                path = Path(path_str)
                if path.suffix in (".yaml", ".yml"):
                    try:
                        self.load_file(path)
                    except Exception as exc:
                        import warnings
                        warnings.warn(f"Hot-reload failed for {path}: {exc}")
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/server/test_registry_hotreload.py -v
```

Expected: PASS (may take up to 3s for the watcher to fire).

**Step 5: Commit**

```bash
git add server/contracts/registry.py tests/server/test_registry_hotreload.py
git commit -m "feat(server): contract registry hot-reload via watchfiles"
```

---

### Task 4: Request schema validation middleware

**Files:**
- Create: `server/gateway/validation.py`
- Create: `tests/server/test_validation.py`

**Step 1: Write failing tests**

```python
# tests/server/test_validation.py
import pytest
from server.gateway.validation import validate_request_body, RequestValidationError


def test_valid_body_passes():
    schema = {
        "type": "object",
        "required": ["message"],
        "properties": {"message": {"type": "string"}},
    }
    # Should not raise
    validate_request_body({"message": "hello"}, schema)


def test_missing_required_field_raises():
    schema = {
        "type": "object",
        "required": ["message"],
        "properties": {"message": {"type": "string"}},
    }
    with pytest.raises(RequestValidationError) as exc_info:
        validate_request_body({}, schema)
    assert "message" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()


def test_wrong_type_raises():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
    with pytest.raises(RequestValidationError):
        validate_request_body({"count": "not-an-int"}, schema)


def test_empty_schema_allows_anything():
    # An empty schema {} validates everything
    validate_request_body({"anything": "goes"}, {})


def test_violations_list_has_detail():
    schema = {
        "type": "object",
        "required": ["order_id", "amount"],
        "properties": {
            "order_id": {"type": "string"},
            "amount": {"type": "number"},
        },
    }
    with pytest.raises(RequestValidationError) as exc_info:
        validate_request_body({}, schema)
    err = exc_info.value
    assert len(err.violations) > 0
    assert all("field" in v or "message" in v for v in err.violations)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_validation.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.gateway.validation'`

**Step 3: Implement validation**

```python
# server/gateway/validation.py
from __future__ import annotations
import jsonschema
from jsonschema import ValidationError as JSValidationError


class RequestValidationError(Exception):
    def __init__(self, message: str, violations: list[dict]) -> None:
        super().__init__(message)
        self.violations = violations


def validate_request_body(body: dict, schema: dict) -> None:
    """Validate body against JSON Schema. Raises RequestValidationError on failure."""
    if not schema:
        return
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
    if not errors:
        return
    violations = [
        {
            "field": ".".join(str(p) for p in err.absolute_path) or "$root",
            "message": err.message,
        }
        for err in errors
    ]
    raise RequestValidationError(
        f"Request body failed schema validation: {violations[0]['message']}",
        violations=violations,
    )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/server/test_validation.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add server/gateway/validation.py tests/server/test_validation.py
git commit -m "feat(server): request body JSON Schema validation"
```

---

### Task 5: Proxy forwarder

**Files:**
- Create: `server/gateway/proxy.py`
- Create: `tests/server/test_proxy.py`

**Step 1: Write failing tests**

```python
# tests/server/test_proxy.py
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from server.gateway.proxy import forward_request, ProxyError


@pytest.mark.asyncio
async def test_forward_returns_response_text():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"answer": "42"}'
    mock_response.headers = {"content-type": "application/json"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("server.gateway.proxy.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await forward_request(
            target="http://agent:8000/chat",
            body={"input": "hello"},
            headers={},
        )

    assert result.status_code == 200
    assert result.text == '{"answer": "42"}'


@pytest.mark.asyncio
async def test_forward_raises_proxy_error_on_connection_failure():
    import httpx

    with patch("server.gateway.proxy.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(ProxyError, match="refused"):
            await forward_request(
                target="http://dead-agent:9999/chat",
                body={"input": "hello"},
                headers={},
            )


@pytest.mark.asyncio
async def test_forward_passes_custom_headers():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "{}"
    mock_response.headers = {}
    mock_response.raise_for_status = MagicMock()

    captured_headers: dict = {}

    async def capture_post(url, json, headers, timeout):
        captured_headers.update(headers)
        return mock_response

    mock_client = AsyncMock()
    mock_client.post = capture_post

    with patch("server.gateway.proxy.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        await forward_request(
            target="http://agent/chat",
            body={},
            headers={"X-Trace-Id": "abc123"},
        )

    assert captured_headers.get("X-Trace-Id") == "abc123"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_proxy.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.gateway.proxy'`

**Step 3: Implement proxy forwarder**

```python
# server/gateway/proxy.py
from __future__ import annotations
from dataclasses import dataclass
import httpx


class ProxyError(Exception):
    pass


@dataclass
class ProxyResponse:
    status_code: int
    text: str
    headers: dict


async def forward_request(
    target: str,
    body: dict,
    headers: dict,
    timeout: float = 30.0,
) -> ProxyResponse:
    """Forward a POST request to the target agent and return its raw response."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                target,
                json=body,
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            return ProxyResponse(
                status_code=resp.status_code,
                text=resp.text,
                headers=dict(resp.headers),
            )
    except httpx.HTTPStatusError as exc:
        raise ProxyError(f"Target returned {exc.response.status_code}: {exc.response.text}") from exc
    except httpx.TransportError as exc:
        raise ProxyError(str(exc)) from exc
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/server/test_proxy.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add server/gateway/proxy.py tests/server/test_proxy.py
git commit -m "feat(server): async HTTP proxy forwarder"
```

---

### Task 6: Response evaluator (inline / sync)

**Files:**
- Create: `server/gateway/evaluator.py`
- Create: `tests/server/test_gateway_evaluator.py`

**Step 1: Write failing tests**

```python
# tests/server/test_gateway_evaluator.py
import pytest
from core.models import Contract, RetryPolicy, EvaluatorRef, Score
from server.gateway.evaluator import evaluate_response, EvaluationResult


def make_contract(evaluators=None, max_retries=2, hint=None):
    return Contract(
        name="test_contract",
        provider="test-agent",
        request_schema={},
        evaluators=evaluators or [],
        retry_policy=RetryPolicy(max_retries=max_retries, hint=hint),
    )


@pytest.mark.asyncio
async def test_evaluate_no_evaluators_passes():
    contract = make_contract(evaluators=[])
    result = await evaluate_response(response_text='{"ok": true}', contract=contract, context={})
    assert result.passed is True
    assert result.violations == []


@pytest.mark.asyncio
async def test_evaluate_all_pass():
    from core.evaluators.contains import ContainsEvaluator

    contract = make_contract(
        evaluators=[EvaluatorRef(name="contains", mode="binary")]
    )
    evaluator_map = {"contains": ContainsEvaluator(substring="ok")}
    result = await evaluate_response(
        response_text='{"ok": true}',
        contract=contract,
        context={},
        evaluator_map=evaluator_map,
    )
    assert result.passed is True
    assert result.violations == []


@pytest.mark.asyncio
async def test_evaluate_binary_fail_produces_violation():
    from core.evaluators.contains import ContainsEvaluator

    contract = make_contract(
        evaluators=[EvaluatorRef(name="contains", mode="binary")]
    )
    evaluator_map = {"contains": ContainsEvaluator(substring="REQUIRED_WORD")}
    result = await evaluate_response(
        response_text="nothing here",
        contract=contract,
        context={},
        evaluator_map=evaluator_map,
    )
    assert result.passed is False
    assert len(result.violations) == 1
    assert result.violations[0]["evaluator"] == "contains"
    assert result.violations[0]["score"] == 0.0


@pytest.mark.asyncio
async def test_evaluate_warn_mode_never_fails():
    from core.evaluators.contains import ContainsEvaluator

    contract = make_contract(
        evaluators=[EvaluatorRef(name="contains", mode="warn")]
    )
    evaluator_map = {"contains": ContainsEvaluator(substring="MISSING")}
    result = await evaluate_response(
        response_text="no match",
        contract=contract,
        context={},
        evaluator_map=evaluator_map,
    )
    assert result.passed is True  # warn never blocks
    assert len(result.violations) == 0


@pytest.mark.asyncio
async def test_evaluate_threshold_fail():
    from core.evaluators.contains import ContainsEvaluator

    contract = make_contract(
        evaluators=[EvaluatorRef(name="contains", mode="threshold", min_score=0.9)]
    )
    evaluator_map = {"contains": ContainsEvaluator(substring="MISSING")}
    result = await evaluate_response(
        response_text="no match",
        contract=contract,
        context={},
        evaluator_map=evaluator_map,
    )
    assert result.passed is False
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_gateway_evaluator.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.gateway.evaluator'`

**Step 3: Implement response evaluator**

```python
# server/gateway/evaluator.py
from __future__ import annotations
import time
from dataclasses import dataclass, field
from core.models import Contract, Result, Score


@dataclass
class EvaluationResult:
    passed: bool
    violations: list[dict] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)


async def evaluate_response(
    response_text: str,
    contract: Contract,
    context: dict,
    evaluator_map: dict | None = None,
) -> EvaluationResult:
    """Run all evaluators in contract against response_text. Returns EvaluationResult."""
    if evaluator_map is None:
        evaluator_map = {}

    violations: list[dict] = []
    results: list[Result] = []

    for ref in contract.evaluators:
        evaluator = evaluator_map.get(ref.name)
        if evaluator is None:
            # Unknown evaluator — skip gracefully
            continue

        t0 = time.monotonic()
        score: Score = evaluator._run(response_text)
        duration_ms = int((time.monotonic() - t0) * 1000)

        result = Result(
            test_id=context.get("request_id", "unknown"),
            evaluator=ref.name,
            score=score,
            mode=ref.mode,
            min_score=ref.min_score,
            duration_ms=duration_ms,
            trace_id=context.get("trace_id"),
        )
        results.append(result)

        if not result.passed:
            violations.append(
                {
                    "evaluator": ref.name,
                    "score": score.value,
                    "reason": score.reason,
                }
            )

    return EvaluationResult(
        passed=len(violations) == 0,
        violations=violations,
        results=results,
    )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/server/test_gateway_evaluator.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add server/gateway/evaluator.py tests/server/test_gateway_evaluator.py
git commit -m "feat(server): inline response evaluator — runs contract evaluators, returns violations"
```

---

### Task 7: Retry + self-healing engine

**Files:**
- Create: `server/gateway/retry.py`
- Create: `tests/server/test_retry.py`

**Step 1: Write failing tests**

A "fake agent" returns failure N times then succeeds. Tests verify hint injection and backoff.

```python
# tests/server/test_retry.py
import asyncio
import pytest
from core.models import Contract, RetryPolicy, EvaluatorRef
from core.evaluators.contains import ContainsEvaluator
from server.gateway.retry import retry_with_hint, RetryExhausted


def make_contract(max_retries=2, hint="Include the word SUCCESS", backoff_ms=0):
    return Contract(
        name="retry_test",
        provider="fake-agent",
        request_schema={},
        evaluators=[EvaluatorRef(name="contains", mode="binary")],
        retry_policy=RetryPolicy(
            max_retries=max_retries,
            hint=hint,
            backoff_ms=backoff_ms,
        ),
    )


@pytest.mark.asyncio
async def test_succeeds_on_first_attempt():
    call_log = []

    async def fake_agent(body: dict) -> str:
        call_log.append(body)
        return "SUCCESS response"

    contract = make_contract()
    evaluator_map = {"contains": ContainsEvaluator(substring="SUCCESS")}

    result = await retry_with_hint(
        agent_fn=fake_agent,
        initial_body={"input": "hello"},
        contract=contract,
        evaluator_map=evaluator_map,
        context={},
    )

    assert result.response_text == "SUCCESS response"
    assert result.attempts == 1
    assert result.passed is True
    assert len(call_log) == 1


@pytest.mark.asyncio
async def test_retries_and_succeeds_on_second_attempt():
    call_log = []

    async def fake_agent(body: dict) -> str:
        call_log.append(body)
        if len(call_log) < 2:
            return "FAILURE response"
        return "SUCCESS response"

    contract = make_contract(max_retries=2, hint="Include the word SUCCESS")
    evaluator_map = {"contains": ContainsEvaluator(substring="SUCCESS")}

    result = await retry_with_hint(
        agent_fn=fake_agent,
        initial_body={"input": "hello"},
        contract=contract,
        evaluator_map=evaluator_map,
        context={},
    )

    assert result.passed is True
    assert result.attempts == 2
    # Verify the hint was injected on retry
    assert "_eva_hint" in call_log[1]
    assert call_log[1]["_eva_hint"] == "Include the word SUCCESS"


@pytest.mark.asyncio
async def test_exhausts_retries_raises():
    async def always_fail(body: dict) -> str:
        return "FAILURE always"

    contract = make_contract(max_retries=2, hint="Try harder")
    evaluator_map = {"contains": ContainsEvaluator(substring="SUCCESS")}

    with pytest.raises(RetryExhausted) as exc_info:
        await retry_with_hint(
            agent_fn=always_fail,
            initial_body={"input": "hello"},
            contract=contract,
            evaluator_map=evaluator_map,
            context={},
        )

    exc = exc_info.value
    assert exc.attempts == 3  # initial + 2 retries
    assert len(exc.violations) > 0


@pytest.mark.asyncio
async def test_backoff_is_respected(monkeypatch):
    """Verify asyncio.sleep is called with backoff_ms / 1000."""
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def always_fail(body: dict) -> str:
        return "nope"

    contract = make_contract(max_retries=1, backoff_ms=200)
    evaluator_map = {"contains": ContainsEvaluator(substring="SUCCESS")}

    with pytest.raises(RetryExhausted):
        await retry_with_hint(
            agent_fn=always_fail,
            initial_body={},
            contract=contract,
            evaluator_map=evaluator_map,
            context={},
        )

    assert any(abs(s - 0.2) < 0.01 for s in sleep_calls)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_retry.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.gateway.retry'`

**Step 3: Implement retry engine**

```python
# server/gateway/retry.py
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from core.models import Contract
from server.gateway.evaluator import evaluate_response, EvaluationResult


@dataclass
class RetryResult:
    response_text: str
    attempts: int
    passed: bool
    violations: list[dict] = field(default_factory=list)
    eval_result: EvaluationResult | None = None


class RetryExhausted(Exception):
    def __init__(self, attempts: int, violations: list[dict], last_response: str) -> None:
        super().__init__(
            f"Contract violated after {attempts} attempt(s): {violations}"
        )
        self.attempts = attempts
        self.violations = violations
        self.last_response = last_response


async def retry_with_hint(
    agent_fn: Callable[[dict], Awaitable[str]],
    initial_body: dict,
    contract: Contract,
    evaluator_map: dict,
    context: dict,
) -> RetryResult:
    """
    Call agent_fn, evaluate the response, retry up to max_retries times on failure.
    On each retry, injects contract.retry_policy.hint as `_eva_hint` in the request body.
    Raises RetryExhausted if all attempts fail.
    """
    policy = contract.retry_policy
    max_attempts = 1 + policy.max_retries
    body = dict(initial_body)
    eval_result = None
    response_text = ""

    for attempt in range(1, max_attempts + 1):
        if attempt > 1 and policy.hint:
            body["_eva_hint"] = policy.hint

        if attempt > 1 and policy.backoff_ms > 0:
            await asyncio.sleep(policy.backoff_ms / 1000)

        response_text = await agent_fn(body)
        eval_result = await evaluate_response(
            response_text=response_text,
            contract=contract,
            context={**context, "attempt": attempt},
            evaluator_map=evaluator_map,
        )

        if eval_result.passed:
            return RetryResult(
                response_text=response_text,
                attempts=attempt,
                passed=True,
                violations=[],
                eval_result=eval_result,
            )

    raise RetryExhausted(
        attempts=max_attempts,
        violations=eval_result.violations if eval_result else [],
        last_response=response_text,
    )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/server/test_retry.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add server/gateway/retry.py tests/server/test_retry.py
git commit -m "feat(server): retry engine — hint injection, backoff, RetryExhausted on max attempts"
```

---

### Task 8: `POST /v1/proxy` endpoint

**Files:**
- Edit: `server/app.py` — mount router
- Create: `server/gateway/routes.py`
- Create: `tests/server/test_routes_proxy.py`

**Step 1: Write failing tests**

```python
# tests/server/test_routes_proxy.py
import pytest
import json
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from server.app import app


def _make_proxy_response(text: str, status: int = 200):
    from server.gateway.proxy import ProxyResponse
    return ProxyResponse(status_code=status, text=text, headers={})


@pytest.mark.asyncio
async def test_proxy_passes_through_valid_response():
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _make_proxy_response('{"answer": "hello"}')

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/proxy",
                json={
                    "target": "http://agent:8000/chat",
                    "body": {"input": "hi"},
                    "evaluators": [],
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["eva_status"] == "pass"
    assert data["response"] == {"answer": "hello"}


@pytest.mark.asyncio
async def test_proxy_returns_contract_violation_on_eval_failure():
    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = _make_proxy_response('{"answer": "bad"}')

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/proxy",
                json={
                    "target": "http://agent:8000/chat",
                    "body": {"input": "hi"},
                    "evaluators": [
                        {"name": "contains", "mode": "binary", "config": {"substring": "REQUIRED"}}
                    ],
                },
            )

    assert resp.status_code == 422
    data = resp.json()
    assert data["eva_status"] == "contract_violation"
    assert isinstance(data["violations"], list)
    assert data["attempts"] >= 1


@pytest.mark.asyncio
async def test_proxy_missing_target_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/proxy",
            json={"body": {"input": "hi"}},  # missing target
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_proxy_upstream_error_returns_502():
    from server.gateway.proxy import ProxyError

    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.side_effect = ProxyError("connection refused")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/proxy",
                json={"target": "http://dead:9999/", "body": {}, "evaluators": []},
            )

    assert resp.status_code == 502
    assert "connection refused" in resp.json()["detail"]
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_routes_proxy.py -v
```

Expected: 404 on `/v1/proxy` (route not yet registered).

**Step 3: Implement routes and wire into app**

```python
# server/gateway/routes.py
from __future__ import annotations
import json
import uuid
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from core.evaluators.contains import ContainsEvaluator
from core.evaluators.regex_match import RegexEvaluator
from core.evaluators.json_schema_valid import JsonSchemaEvaluator
from core.evaluators.no_pii import NoPiiEvaluator
from core.models import Contract, RetryPolicy, EvaluatorRef
from server.gateway.proxy import forward_request, ProxyError
from server.gateway.evaluator import evaluate_response
from server.gateway.retry import retry_with_hint, RetryExhausted

router = APIRouter(prefix="/v1")

_registry = None


def set_registry(registry) -> None:
    global _registry
    _registry = registry


# Built-in evaluator constructors keyed by name
_BUILTIN_EVALUATOR_FACTORIES = {
    "contains": lambda cfg: ContainsEvaluator(
        substring=cfg.get("substring", ""),
        case_sensitive=cfg.get("case_sensitive", True),
    ),
    "regex": lambda cfg: RegexEvaluator(pattern=cfg.get("pattern", ".*")),
    "json_schema_valid": lambda cfg: JsonSchemaEvaluator(schema=cfg.get("schema", {})),
    "no_pii": lambda cfg: NoPiiEvaluator(),
}


class EvaluatorSpec(BaseModel):
    name: str
    mode: str = "binary"
    min_score: float = 1.0
    config: dict = Field(default_factory=dict)


class ProxyRequest(BaseModel):
    target: str
    body: dict = Field(default_factory=dict)
    evaluators: list[EvaluatorSpec] = Field(default_factory=list)
    max_retries: int = 0
    hint: str | None = None
    backoff_ms: int = 0


def _build_evaluator_map(specs: list[EvaluatorSpec]) -> dict:
    evaluator_map = {}
    for spec in specs:
        factory = _BUILTIN_EVALUATOR_FACTORIES.get(spec.name)
        if factory:
            evaluator_map[spec.name] = factory(spec.config)
    return evaluator_map


def _violation_response(
    eva_status: str,
    attempts: int,
    violations: list[dict],
    request_id: str,
    trace_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "eva_status": eva_status,
            "attempts": attempts,
            "violations": violations,
            "request_id": request_id,
            "trace_id": trace_id,
        },
    )


@router.post("/proxy")
async def proxy(req: ProxyRequest) -> Any:
    from server.gateway.tracing import get_tracer, start_span
    tracer = get_tracer()
    request_id = str(uuid.uuid4())

    with start_span(tracer, "eva.proxy.request", {"target": req.target, "request_id": request_id}) as span_ctx:
        trace_id = span_ctx.trace_id
        context = {"request_id": request_id, "trace_id": trace_id}
        evaluator_map = _build_evaluator_map(req.evaluators)

        contract = Contract(
            name="inline",
            provider=req.target,
            request_schema={},
            evaluators=[
                EvaluatorRef(name=s.name, mode=s.mode, min_score=s.min_score)
                for s in req.evaluators
            ],
            retry_policy=RetryPolicy(
                max_retries=req.max_retries,
                hint=req.hint,
                backoff_ms=req.backoff_ms,
            ),
        )

        async def call_agent(body: dict) -> str:
            proxy_resp = await forward_request(target=req.target, body=body, headers={})
            return proxy_resp.text

        try:
            retry_result = await retry_with_hint(
                agent_fn=call_agent,
                initial_body=req.body,
                contract=contract,
                evaluator_map=evaluator_map,
                context=context,
            )
        except ProxyError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except RetryExhausted as exc:
            return _violation_response(
                eva_status="contract_violation",
                attempts=exc.attempts,
                violations=exc.violations,
                request_id=request_id,
                trace_id=trace_id,
            )

        try:
            response_data = json.loads(retry_result.response_text)
        except (json.JSONDecodeError, ValueError):
            response_data = retry_result.response_text

        return {
            "eva_status": "pass",
            "attempts": retry_result.attempts,
            "response": response_data,
            "request_id": request_id,
            "trace_id": trace_id,
        }


class InvokeRequest(BaseModel):
    contract: str
    body: dict = Field(default_factory=dict)


@router.post("/contract/invoke")
async def contract_invoke(req: InvokeRequest) -> Any:
    if _registry is None:
        raise HTTPException(status_code=503, detail="Contract registry not initialized")

    contract = _registry.get(req.contract)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"Contract '{req.contract}' not found")

    from server.gateway.validation import validate_request_body, RequestValidationError
    from server.gateway.tracing import get_tracer, start_span
    tracer = get_tracer()
    request_id = str(uuid.uuid4())

    try:
        validate_request_body(req.body, contract.request_schema)
    except RequestValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "eva_status": "request_invalid",
                "violations": exc.violations,
                "contract": req.contract,
            },
        )

    with start_span(tracer, "eva.contract.invoke", {"contract": req.contract, "request_id": request_id}) as span_ctx:
        trace_id = span_ctx.trace_id
        context = {"request_id": request_id, "trace_id": trace_id}
        evaluator_map = _build_evaluator_map(
            [EvaluatorSpec(name=ref.name, mode=ref.mode, min_score=ref.min_score)
             for ref in contract.evaluators]
        )

        async def call_agent(body: dict) -> str:
            proxy_resp = await forward_request(target=contract.provider, body=body, headers={})
            return proxy_resp.text

        try:
            retry_result = await retry_with_hint(
                agent_fn=call_agent,
                initial_body=req.body,
                contract=contract,
                evaluator_map=evaluator_map,
                context=context,
            )
        except ProxyError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except RetryExhausted as exc:
            return _violation_response(
                eva_status="contract_violation",
                attempts=exc.attempts,
                violations=exc.violations,
                request_id=request_id,
                trace_id=trace_id,
            )

        try:
            response_data = json.loads(retry_result.response_text)
        except (json.JSONDecodeError, ValueError):
            response_data = retry_result.response_text

        return {
            "eva_status": "pass",
            "attempts": retry_result.attempts,
            "response": response_data,
            "request_id": request_id,
            "trace_id": trace_id,
        }
```

```python
# server/app.py
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/server/test_routes_proxy.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add server/gateway/routes.py server/app.py tests/server/test_routes_proxy.py
git commit -m "feat(server): POST /v1/proxy — forward, evaluate, retry, structured response"
```

---

### Task 9: `POST /v1/contract/invoke` endpoint tests

**Files:**
- Create: `tests/server/test_routes_invoke.py`

(Implementation is already in `server/gateway/routes.py` from Task 8.)

**Step 1: Write tests**

```python
# tests/server/test_routes_invoke.py
import pytest
import yaml
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch


@pytest.fixture
def app_with_registry(tmp_path):
    """Return a fresh app instance with a contract loaded into its registry."""
    from server.app import create_app
    from server.contracts.registry import ContractRegistry

    contract_data = {
        "name": "echo_policy",
        "provider": "http://echo-agent:8000/respond",
        "request_schema": {
            "type": "object",
            "required": ["message"],
            "properties": {"message": {"type": "string"}},
        },
        "evaluators": [{"name": "contains", "mode": "binary"}],
        "retry_policy": {"max_retries": 1, "hint": "Include a greeting"},
    }
    f = tmp_path / "echo_policy.yaml"
    f.write_text(yaml.dump(contract_data))

    registry = ContractRegistry()
    registry.load_file(f)
    return create_app(registry=registry)


@pytest.mark.asyncio
async def test_invoke_validates_request_schema(app_with_registry):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_registry), base_url="http://test"
    ) as client:
        # Missing required 'message' field
        resp = await client.post(
            "/v1/contract/invoke",
            json={"contract": "echo_policy", "body": {}},
        )
    assert resp.status_code == 400
    data = resp.json()
    assert data["eva_status"] == "request_invalid"
    assert len(data["violations"]) > 0


@pytest.mark.asyncio
async def test_invoke_passes_valid_request(app_with_registry):
    from server.gateway.proxy import ProxyResponse

    with patch("server.gateway.routes.forward_request", new_callable=AsyncMock) as mock_fwd:
        mock_fwd.return_value = ProxyResponse(
            status_code=200, text='{"reply": "hello"}', headers={}
        )
        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/contract/invoke",
                json={"contract": "echo_policy", "body": {"message": "hi"}},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["eva_status"] == "pass"


@pytest.mark.asyncio
async def test_invoke_unknown_contract_returns_404(app_with_registry):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_registry), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/v1/contract/invoke",
            json={"contract": "nonexistent", "body": {"message": "hi"}},
        )
    assert resp.status_code == 404
```

**Step 2: Run tests to verify they pass**

```bash
pytest tests/server/test_routes_invoke.py -v
```

Expected: all PASS.

**Step 3: Run full server test suite**

```bash
pytest tests/server/ -v
```

Expected: all PASS.

**Step 4: Commit**

```bash
git add tests/server/test_routes_invoke.py
git commit -m "test(server): POST /v1/contract/invoke — request validation, pass, 404 on missing contract"
```

---

### Task 10: OTEL spans throughout request lifecycle

**Files:**
- Create: `server/gateway/tracing.py`
- Create: `tests/server/test_tracing.py`

(Tracing calls are already wired into routes.py from Task 8.)

**Step 1: Write failing tests**

```python
# tests/server/test_tracing.py
import pytest
from server.gateway.tracing import get_tracer, start_span, SpanContext


def test_get_tracer_returns_tracer():
    tracer = get_tracer()
    assert tracer is not None


def test_start_span_returns_context_manager():
    tracer = get_tracer()
    ctx = start_span(tracer, "test.operation", {"key": "value"})
    assert ctx is not None


def test_span_context_has_trace_id():
    tracer = get_tracer()
    with start_span(tracer, "test.op", {}) as span_ctx:
        assert isinstance(span_ctx, SpanContext)
        # trace_id is a hex string or None when using NoopTracer
        assert span_ctx.trace_id is None or isinstance(span_ctx.trace_id, str)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_tracing.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.gateway.tracing'`

**Step 3: Implement tracing wrapper**

```python
# server/gateway/tracing.py
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator

try:
    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


@dataclass
class SpanContext:
    trace_id: str | None
    span_id: str | None


class _NoopTracer:
    """Fallback when opentelemetry is not installed."""

    @contextmanager
    def _noop_span(self, name: str, attributes: dict) -> Generator[SpanContext, None, None]:
        yield SpanContext(trace_id=None, span_id=None)


def get_tracer(name: str = "eva.server"):
    if _OTEL_AVAILABLE:
        return trace.get_tracer(name)
    return _NoopTracer()


@contextmanager
def start_span(tracer, operation: str, attributes: dict) -> Generator[SpanContext, None, None]:
    if isinstance(tracer, _NoopTracer):
        with tracer._noop_span(operation, attributes) as ctx:
            yield ctx
        return

    with tracer.start_as_current_span(operation) as span:
        for k, v in attributes.items():
            span.set_attribute(k, str(v))
        ctx_obj = span.get_span_context()
        trace_id = format(ctx_obj.trace_id, "032x") if ctx_obj.trace_id else None
        span_id = format(ctx_obj.span_id, "016x") if ctx_obj.span_id else None
        yield SpanContext(trace_id=trace_id, span_id=span_id)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/server/test_tracing.py -v
```

Expected: all PASS.

**Step 5: Run full server suite**

```bash
pytest tests/server/ -v
```

Expected: all PASS.

**Step 6: Commit**

```bash
git add server/gateway/tracing.py tests/server/test_tracing.py
git commit -m "feat(server): OTEL span instrumentation — noop fallback when opentelemetry not installed"
```

---

### Task 11: ARQ async evaluation queue

**Files:**
- Create: `server/queue/worker.py`
- Create: `server/queue/tasks.py`
- Create: `tests/server/test_arq_tasks.py`

**Note:** ARQ requires Redis. These tests mock the Redis layer. To run integration tests: `docker run -p 6379:6379 redis:7-alpine`. The ARQ worker is started separately: `arq server.queue.worker.WorkerSettings`.

**Step 1: Write failing tests**

```python
# tests/server/test_arq_tasks.py
import pytest
from server.queue.tasks import evaluate_async


@pytest.mark.asyncio
async def test_evaluate_async_returns_result():
    """evaluate_async is an ARQ task — test it as a plain async function."""
    contract_dict = {
        "name": "async_test",
        "provider": "http://agent:8000",
        "request_schema": {},
        "evaluators": [{"name": "contains", "mode": "binary", "min_score": 1.0}],
        "retry_policy": {"max_retries": 0},
    }

    result = await evaluate_async(
        ctx={},  # ARQ passes a ctx dict to tasks
        response_text='{"answer": "hello world"}',
        contract_dict=contract_dict,
        evaluator_specs=[{"name": "contains", "mode": "binary", "config": {"substring": "hello"}}],
        context={"request_id": "req_test_1"},
    )

    assert result["passed"] is True
    assert result["violations"] == []


@pytest.mark.asyncio
async def test_evaluate_async_captures_violations():
    contract_dict = {
        "name": "strict_test",
        "provider": "http://agent:8000",
        "request_schema": {},
        "evaluators": [{"name": "contains", "mode": "binary", "min_score": 1.0}],
        "retry_policy": {"max_retries": 0},
    }

    result = await evaluate_async(
        ctx={},
        response_text="no match here",
        contract_dict=contract_dict,
        evaluator_specs=[{"name": "contains", "mode": "binary", "config": {"substring": "REQUIRED"}}],
        context={"request_id": "req_test_2"},
    )

    assert result["passed"] is False
    assert len(result["violations"]) == 1
    assert result["violations"][0]["evaluator"] == "contains"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_arq_tasks.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.queue.tasks'`

**Step 3: Implement ARQ tasks**

```python
# server/queue/tasks.py
from __future__ import annotations
from core.models import Contract
from server.gateway.evaluator import evaluate_response
from server.gateway.routes import _build_evaluator_map, EvaluatorSpec


async def evaluate_async(
    ctx: dict,
    response_text: str,
    contract_dict: dict,
    evaluator_specs: list[dict],
    context: dict,
) -> dict:
    """
    ARQ task: evaluate a response against a contract asynchronously.
    Called fire-and-forget; result is stored in ARQ job store.
    ctx is the ARQ context dict (contains redis connection, job_id, etc.).
    """
    contract = Contract.model_validate(contract_dict)
    specs = [EvaluatorSpec(**s) for s in evaluator_specs]
    evaluator_map = _build_evaluator_map(specs)

    eval_result = await evaluate_response(
        response_text=response_text,
        contract=contract,
        context=context,
        evaluator_map=evaluator_map,
    )

    return {
        "passed": eval_result.passed,
        "violations": eval_result.violations,
        "request_id": context.get("request_id"),
    }
```

```python
# server/queue/worker.py
from arq.connections import RedisSettings


class WorkerSettings:
    """
    ARQ worker configuration.
    Start the worker with: arq server.queue.worker.WorkerSettings
    Requires Redis: docker run -p 6379:6379 redis:7-alpine
    """
    functions = ["server.queue.tasks.evaluate_async"]
    redis_settings = RedisSettings()  # defaults to localhost:6379
    max_jobs = 10
    job_timeout = 60
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/server/test_arq_tasks.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add server/queue/tasks.py server/queue/worker.py tests/server/test_arq_tasks.py
git commit -m "feat(server): ARQ async eval task + worker settings (requires Redis for production use)"
```

---

### Task 12: `eva serve` CLI command

**Files:**
- Edit: `cli/main.py` — add `serve` command
- Create: `tests/e2e/test_serve_command.py`

**Step 1: Write failing E2E test**

```python
# tests/e2e/test_serve_command.py
import subprocess
import sys
import time
import httpx


def test_eva_serve_starts_and_responds():
    """Start eva serve as subprocess, poll /health, then terminate."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "cli.main", "serve", "--host", "127.0.0.1", "--port", "18765"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Poll until server is up (max 5s)
        for _ in range(50):
            time.sleep(0.1)
            try:
                resp = httpx.get("http://127.0.0.1:18765/health", timeout=0.5)
                if resp.status_code == 200:
                    break
            except Exception:
                continue
        else:
            proc.terminate()
            raise AssertionError("Server did not start within 5s")

        resp = httpx.get("http://127.0.0.1:18765/health", timeout=2)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        proc.terminate()
        proc.wait(timeout=5)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/e2e/test_serve_command.py -v
```

Expected: server process fails to start (no `serve` command yet).

**Step 3: Implement `eva serve`**

```python
# cli/main.py — add serve command (alongside existing init, run, contract commands)
import typer
from pathlib import Path

app = typer.Typer()

# ... existing commands ...


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8080, help="Bind port"),
    contracts_dir: Path = typer.Option(
        Path("contracts"), help="Directory of contract YAML files to load"
    ),
    reload: bool = typer.Option(False, help="Enable hot-reload (dev mode)"),
    workers: int = typer.Option(1, help="Number of uvicorn workers"),
) -> None:
    """Start the Eva gateway server."""
    import uvicorn
    from server.app import create_app
    from server.contracts.registry import ContractRegistry

    registry = ContractRegistry()
    if contracts_dir.exists():
        registry.load_dir(contracts_dir)
        typer.echo(f"Loaded {len(registry.all())} contract(s) from {contracts_dir}")
    else:
        typer.echo(
            f"Warning: contracts directory '{contracts_dir}' not found — starting with empty registry"
        )

    _app = create_app(registry=registry)

    uvicorn.run(
        _app,
        host=host,
        port=port,
        workers=workers if not reload else 1,
        reload=reload,
    )
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/e2e/test_serve_command.py -v
```

Expected: PASS (server starts and responds on /health).

**Step 5: Commit**

```bash
git add cli/main.py tests/e2e/test_serve_command.py
git commit -m "feat(cli): eva serve command — starts FastAPI gateway with contract registry"
```

---

### Task 13: Full server E2E integration test

**Files:**
- Create: `tests/e2e/test_server_e2e.py`

**Step 0: Ensure pytest markers and conftest hook are declared**

Add or update `[tool.pytest.ini_options]` in `pyproject.toml` to declare all markers used across Phase 3 tests. This is required when `--strict-markers` is active — any undeclared marker causes a collection error.

```toml
# pyproject.toml — [tool.pytest.ini_options]
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "asyncio: async tests",
    "integration: requires external services — run with --integration flag",
    "slow: slow-running tests",
    "e2e: end-to-end CLI tests via subprocess",
    "llm: tests that would make real LLM calls if not mocked",
]
addopts = ["--strict-markers", "-v"]
```

Also ensure `tests/conftest.py` contains the pytest hook that gates `integration`-marked tests behind `--integration`:

```python
# tests/conftest.py — add if not already present
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run tests that require external services (Postgres, Redis, etc.)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="Pass --integration to run integration tests")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
```

> **Note:** The `--integration` flag must be declared in root `conftest.py` (not in individual plugin test files) so that it is visible to the pytest session regardless of which test paths are collected. Individual plugin conftest files that redeclare it will cause a duplicate-option error — remove any such redeclarations.

**Step 1: Write the test**

```python
# tests/e2e/test_server_e2e.py
"""
End-to-end: Eva Gateway talking to a real echo target (ASGI, in-process).
No external process needed. Verifies proxy → evaluate → return flow.
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
    """Eva proxy → echo agent → contains evaluator passes → 200 pass."""
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
```

**Step 2: Run to verify they pass**

```bash
pytest tests/e2e/test_server_e2e.py -v
```

Expected: all PASS.

**Step 3: Commit**

```bash
git add tests/e2e/test_server_e2e.py
git commit -m "test(server): E2E integration tests — proxy pass-through and retry with hint injection"
```

---

## Section B — Official Plugins

---

### Task 14: Plugin package scaffold

Each plugin lives at `plugins/<name>/` as a separate installable package.

> **Entry-point group prerequisite:** The core `pyproject.toml` (created in Phase 1) should already contain placeholder entry-point group tables (`[project.entry-points."eva.storage"]`, `[project.entry-points."eva.otel"]`, etc.) so that the groups are registered at package install time. Plugins created here register into those same groups. If the Phase 1 fix was not applied, add the group tables to the core `pyproject.toml` now before installing any plugin in development mode:
>
> ```toml
> # pyproject.toml (core) — add if not already present
> [project.entry-points."eva.storage"]
> # populated by eva-postgres when installed
>
> [project.entry-points."eva.otel"]
> # populated by eva-otlp when installed
>
> [project.entry-points."eva.a2a"]
> # populated by eva-a2a when installed
>
> [project.entry-points."eva.mcp"]
> # populated by eva-mcp when installed
> ```

**Files:**
```
plugins/
├── eva-postgres/
│   ├── pyproject.toml
│   ├── eva_postgres/__init__.py
│   └── eva_postgres/py.typed
├── eva-otlp/
│   ├── pyproject.toml
│   ├── eva_otlp/__init__.py
│   └── eva_otlp/py.typed
├── eva-a2a/
│   ├── pyproject.toml
│   ├── eva_a2a/__init__.py
│   └── eva_a2a/py.typed
└── eva-mcp/
    ├── pyproject.toml
    ├── eva_mcp/__init__.py
    └── eva_mcp/py.typed
```

**Step 1: Create pyproject.toml for each plugin**

```toml
# plugins/eva-postgres/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "eva-postgres"
version = "0.1.0"
description = "Eva Plugin — PostgreSQL storage adapter"
requires-python = ">=3.11"
dependencies = [
    "eva>=0.1.0",
    "sqlmodel>=0.0.21",
    "psycopg2-binary>=2.9",
]

[project.entry-points."eva.storage"]
postgres = "eva_postgres.adapter:PostgresStorageAdapter"
```

```toml
# plugins/eva-otlp/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "eva-otlp"
version = "0.1.0"
description = "Eva Plugin — OTLP trace exporter"
requires-python = ">=3.11"
dependencies = [
    "eva>=0.1.0",
    "opentelemetry-sdk>=1.24",
    "opentelemetry-exporter-otlp-proto-grpc>=1.24",
]

[project.entry-points."eva.otel"]
otlp = "eva_otlp.exporter:OtlpExporter"
```

```toml
# plugins/eva-a2a/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "eva-a2a"
version = "0.1.0"
description = "Eva Plugin — Import A2A Agent Cards as Eva contracts"
requires-python = ">=3.11"
dependencies = [
    "eva>=0.1.0",
    "pyyaml>=6",
    "typer>=0.12",
]

[project.scripts]
eva-a2a = "eva_a2a.cli:app"
```

```toml
# plugins/eva-mcp/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "eva-mcp"
version = "0.1.0"
description = "Eva Plugin — Import MCP server manifests as Eva contracts"
requires-python = ">=3.11"
dependencies = [
    "eva>=0.1.0",
    "pyyaml>=6",
    "typer>=0.12",
]

[project.scripts]
eva-mcp = "eva_mcp.cli:app"
```

**Step 2: Create empty __init__.py and py.typed for all four packages**

```bash
mkdir -p plugins/eva-postgres/eva_postgres plugins/eva-otlp/eva_otlp plugins/eva-a2a/eva_a2a plugins/eva-mcp/eva_mcp
touch plugins/eva-postgres/eva_postgres/__init__.py plugins/eva-postgres/eva_postgres/py.typed
touch plugins/eva-otlp/eva_otlp/__init__.py plugins/eva-otlp/eva_otlp/py.typed
touch plugins/eva-a2a/eva_a2a/__init__.py plugins/eva-a2a/eva_a2a/py.typed
touch plugins/eva-mcp/eva_mcp/__init__.py plugins/eva-mcp/eva_mcp/py.typed
```

**Step 3: Commit**

```bash
git add plugins/
git commit -m "chore(plugins): scaffold four plugin packages with pyproject.toml"
```

---

### Task 15: `eva-postgres` — PostgreSQL storage adapter

**Files:**
- Create: `plugins/eva-postgres/eva_postgres/adapter.py`
- Create: `plugins/eva-postgres/tests/__init__.py`
- Create: `plugins/eva-postgres/tests/test_postgres_adapter.py`

**Step 1: Write tests**

Integration tests — marked to skip without `--integration` flag. Run with a live Postgres.

```python
# plugins/eva-postgres/tests/test_postgres_adapter.py
"""
Integration tests — requires Postgres.
Run: pytest --integration plugins/eva-postgres/tests/
Docker: docker run -e POSTGRES_PASSWORD=eva -e POSTGRES_DB=eva_test -p 5432:5432 postgres:16-alpine
"""
import os
import pytest
from datetime import datetime
from core.models import Run, Result, Score

POSTGRES_URL = os.getenv("EVA_POSTGRES_URL", "postgresql://postgres:eva@localhost:5432/eva_test")


def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", default=False)


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="Pass --integration to run Postgres tests")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.mark.integration
def test_save_and_retrieve_run():
    from eva_postgres.adapter import PostgresStorageAdapter

    adapter = PostgresStorageAdapter(url=POSTGRES_URL)
    adapter.setup()

    run = Run(
        run_id="pg_test_001",
        dataset="test_dataset",
        target="http://agent:8000",
        started_at=datetime.utcnow(),
        results=[
            Result(
                test_id="t1",
                evaluator="contains",
                score=Score(value=1.0),
                mode="binary",
                duration_ms=5,
                trace_id=None,
            )
        ],
        passed=True,
    )
    adapter.save_run(run)

    retrieved = adapter.get_run("pg_test_001")
    assert retrieved is not None
    assert retrieved.run_id == "pg_test_001"
    assert retrieved.passed is True
    assert len(retrieved.results) == 1


@pytest.mark.integration
def test_list_runs():
    from eva_postgres.adapter import PostgresStorageAdapter

    adapter = PostgresStorageAdapter(url=POSTGRES_URL)
    adapter.setup()
    runs = adapter.list_runs(limit=10)
    assert isinstance(runs, list)
```

**Step 2: Run tests to verify they skip without --integration**

```bash
cd plugins/eva-postgres && pytest tests/ -v
```

Expected: tests SKIPPED.

**Step 3: Implement the adapter**

```python
# plugins/eva-postgres/eva_postgres/adapter.py
from __future__ import annotations
import json
from datetime import datetime
from sqlmodel import SQLModel, Field, Session, create_engine, select
from sqlalchemy import Column, Text
from core.models import Run, Result


class RunRecord(SQLModel, table=True):
    __tablename__ = "eva_runs"

    run_id: str = Field(primary_key=True)
    dataset: str
    target: str
    started_at: datetime
    duration_ms: int = 0
    passed: bool = False
    results_json: str = Field(sa_column=Column(Text))


class PostgresStorageAdapter:
    """
    PostgreSQL storage adapter for Eva. Implements the storage interface from Phase 2.

    Usage:
        adapter = PostgresStorageAdapter(url="postgresql://user:pass@host/dbname")
        adapter.setup()  # creates tables
        adapter.save_run(run)
        run = adapter.get_run("run_id")
    """

    def __init__(self, url: str) -> None:
        self.engine = create_engine(url)

    def setup(self) -> None:
        SQLModel.metadata.create_all(self.engine)

    def save_run(self, run: Run) -> None:
        record = RunRecord(
            run_id=run.run_id,
            dataset=run.dataset,
            target=run.target,
            started_at=run.started_at,
            duration_ms=run.duration_ms,
            passed=run.passed,
            results_json=json.dumps([r.model_dump() for r in run.results]),
        )
        with Session(self.engine) as session:
            session.merge(record)
            session.commit()

    def get_run(self, run_id: str) -> Run | None:
        with Session(self.engine) as session:
            record = session.get(RunRecord, run_id)
            if record is None:
                return None
            return self._to_run(record)

    def list_runs(self, limit: int = 100) -> list[Run]:
        with Session(self.engine) as session:
            records = session.exec(select(RunRecord).limit(limit)).all()
            return [self._to_run(r) for r in records]

    def _to_run(self, record: RunRecord) -> Run:
        results_data = json.loads(record.results_json)
        results = [Result.model_validate(r) for r in results_data]
        return Run(
            run_id=record.run_id,
            dataset=record.dataset,
            target=record.target,
            started_at=record.started_at,
            duration_ms=record.duration_ms,
            passed=record.passed,
            results=results,
        )
```

**Step 4: Commit**

```bash
git add plugins/eva-postgres/
git commit -m "feat(plugins): eva-postgres — PostgreSQL storage adapter via SQLModel"
```

---

### Task 16: `eva-otlp` — OTLP trace exporter

**Files:**
- Create: `plugins/eva-otlp/eva_otlp/exporter.py`
- Create: `plugins/eva-otlp/tests/__init__.py`
- Create: `plugins/eva-otlp/tests/test_otlp_exporter.py`

**Step 1: Write failing tests**

```python
# plugins/eva-otlp/tests/test_otlp_exporter.py
import pytest
from unittest.mock import patch, MagicMock


def test_otlp_exporter_imports():
    from eva_otlp.exporter import OtlpExporter
    assert OtlpExporter is not None


def test_otlp_exporter_configures_endpoint():
    from eva_otlp.exporter import OtlpExporter
    exporter = OtlpExporter(endpoint="http://localhost:4317")
    assert exporter.endpoint == "http://localhost:4317"


def test_otlp_exporter_default_endpoint():
    from eva_otlp.exporter import OtlpExporter
    exporter = OtlpExporter()
    assert exporter.endpoint == "http://localhost:4317"


def test_otlp_exporter_setup_registers_provider():
    """setup() installs a TracerProvider with OTLP exporter."""
    from eva_otlp.exporter import OtlpExporter

    with patch("eva_otlp.exporter.OTLPSpanExporter") as MockExporter, \
         patch("eva_otlp.exporter.TracerProvider") as MockProvider, \
         patch("eva_otlp.exporter.trace") as mock_trace:

        MockProvider.return_value = MagicMock()
        exporter = OtlpExporter(endpoint="http://collector:4317")
        exporter.setup()

        MockExporter.assert_called_once_with(endpoint="http://collector:4317")
        mock_trace.set_tracer_provider.assert_called_once()
```

**Step 2: Run tests to verify they fail**

```bash
cd plugins/eva-otlp && pytest tests/ -v
```

Expected: `ModuleNotFoundError: No module named 'eva_otlp.exporter'`

**Step 3: Implement the exporter**

```python
# plugins/eva-otlp/eva_otlp/exporter.py
from __future__ import annotations
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


class OtlpExporter:
    """
    OTLP trace exporter for Eva.
    Pipes Eva spans to any OTEL-compatible backend (Jaeger, Datadog, Grafana Tempo).

    Usage:
        from eva_otlp.exporter import OtlpExporter
        exporter = OtlpExporter(endpoint="http://collector:4317")
        exporter.setup()  # Call once at startup — installs the global TracerProvider
    """

    def __init__(self, endpoint: str = "http://localhost:4317") -> None:
        self.endpoint = endpoint

    def setup(self) -> None:
        otlp_exporter = OTLPSpanExporter(endpoint=self.endpoint)
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(provider)
```

**Step 4: Run tests to verify they pass**

```bash
cd plugins/eva-otlp && uv pip install -e "." && pytest tests/ -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add plugins/eva-otlp/
git commit -m "feat(plugins): eva-otlp — OTLP trace exporter wrapping opentelemetry-sdk"
```

---

### Task 17: `eva-a2a` — A2A Agent Card importer

**A2A Agent Card format (JSON):**
```json
{
  "name": "billing-agent",
  "description": "Handles refunds and billing inquiries",
  "capabilities": ["refund", "invoice"],
  "skills": [
    {
      "name": "process_refund",
      "description": "Process a refund request",
      "inputSchema": {
        "type": "object",
        "required": ["order_id"],
        "properties": { "order_id": {"type": "string"} }
      }
    }
  ]
}
```

One Eva contract is produced per skill. The contract `name` is `{agent_name}.{skill_name}`. The `provider` is the agent name. The `request_schema` comes from `skill.inputSchema`.

**Files:**
- Create: `plugins/eva-a2a/eva_a2a/importer.py`
- Create: `plugins/eva-a2a/eva_a2a/cli.py`
- Create: `plugins/eva-a2a/tests/__init__.py`
- Create: `plugins/eva-a2a/tests/test_a2a_importer.py`
- Create: `plugins/eva-a2a/tests/fixtures/billing_agent_card.json`

**Step 1: Create fixture**

```json
{
  "name": "billing-agent",
  "description": "Handles billing and refund inquiries",
  "capabilities": ["refund", "invoice"],
  "skills": [
    {
      "name": "process_refund",
      "description": "Process a refund for an order",
      "inputSchema": {
        "type": "object",
        "required": ["order_id"],
        "properties": {
          "order_id": {"type": "string"},
          "reason": {"type": "string"}
        }
      }
    },
    {
      "name": "get_invoice",
      "description": "Retrieve an invoice by ID",
      "inputSchema": {
        "type": "object",
        "required": ["invoice_id"],
        "properties": {
          "invoice_id": {"type": "string"}
        }
      }
    }
  ]
}
```

Save as: `plugins/eva-a2a/tests/fixtures/billing_agent_card.json`

**Step 2: Write failing tests**

```python
# plugins/eva-a2a/tests/test_a2a_importer.py
import json
import pytest
from pathlib import Path
from eva_a2a.importer import import_agent_card, contracts_to_yaml, A2AImportError

FIXTURES = Path(__file__).parent / "fixtures"


def test_import_produces_contracts_per_skill():
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    assert len(contracts) == 2  # one per skill


def test_import_contract_names():
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    names = [c.name for c in contracts]
    assert "billing-agent.process_refund" in names
    assert "billing-agent.get_invoice" in names


def test_import_preserves_request_schema():
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    refund = next(c for c in contracts if "process_refund" in c.name)
    assert refund.request_schema["required"] == ["order_id"]
    assert "order_id" in refund.request_schema["properties"]


def test_import_sets_provider():
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    for c in contracts:
        assert c.provider == "billing-agent"


def test_import_missing_name_raises():
    with pytest.raises(A2AImportError, match="name"):
        import_agent_card({"skills": []})


def test_import_skill_without_input_schema_uses_empty():
    card = {
        "name": "simple-agent",
        "skills": [{"name": "do_thing", "description": "Does a thing"}],
    }
    contracts = import_agent_card(card)
    assert contracts[0].request_schema == {}


def test_to_yaml_produces_valid_files(tmp_path):
    card = json.loads((FIXTURES / "billing_agent_card.json").read_text())
    contracts = import_agent_card(card)
    paths = contracts_to_yaml(contracts, tmp_path / "out")
    assert len(paths) == 2
    for p in paths:
        assert p.exists()
        import yaml
        data = yaml.safe_load(p.read_text())
        assert "name" in data
        assert "provider" in data
        assert data["provider"] == "billing-agent"
```

**Step 3: Run tests to verify they fail**

```bash
cd plugins/eva-a2a && pytest tests/ -v
```

Expected: `ModuleNotFoundError: No module named 'eva_a2a.importer'`

**Step 4: Implement the importer**

```python
# plugins/eva-a2a/eva_a2a/importer.py
from __future__ import annotations
from pathlib import Path
import yaml
from core.models import Contract, RetryPolicy


class A2AImportError(Exception):
    pass


def import_agent_card(card: dict) -> list[Contract]:
    """
    Convert an A2A Agent Card JSON dict into a list of Eva contracts.
    One contract is produced per skill in card['skills'].
    """
    name = card.get("name")
    if not name:
        raise A2AImportError("Agent Card must have a 'name' field")

    contracts = []
    for skill in card.get("skills", []):
        skill_name = skill.get("name", "unknown")
        request_schema = skill.get("inputSchema", {})
        contracts.append(
            Contract(
                name=f"{name}.{skill_name}",
                provider=name,
                consumer=None,
                request_schema=request_schema,
                evaluators=[],
                retry_policy=RetryPolicy(),
            )
        )
    return contracts


def contracts_to_yaml(contracts: list[Contract], output_dir: Path) -> list[Path]:
    """Write each contract as a YAML file in output_dir. Returns list of written paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for contract in contracts:
        filename = contract.name.replace("/", "_").replace(".", "_") + ".yaml"
        path = output_dir / filename
        data = {
            "name": contract.name,
            "provider": contract.provider,
            "request_schema": contract.request_schema,
            "evaluators": [e.model_dump() for e in contract.evaluators],
            "retry_policy": contract.retry_policy.model_dump(),
        }
        if contract.consumer:
            data["consumer"] = contract.consumer
        path.write_text(yaml.dump(data, sort_keys=False))
        paths.append(path)
    return paths
```

**Step 5: Implement the CLI**

```python
# plugins/eva-a2a/eva_a2a/cli.py
import json
import typer
from pathlib import Path
from eva_a2a.importer import import_agent_card, contracts_to_yaml, A2AImportError

app = typer.Typer()


@app.command()
def convert(
    card_file: Path = typer.Argument(..., help="Path to A2A Agent Card JSON file"),
    output_dir: Path = typer.Option(Path("contracts"), help="Output directory for YAML contracts"),
) -> None:
    """Convert an A2A Agent Card JSON file to Eva contract YAML files."""
    if not card_file.exists():
        typer.echo(f"Error: file not found: {card_file}", err=True)
        raise typer.Exit(1)

    try:
        card = json.loads(card_file.read_text())
        contracts = import_agent_card(card)
        paths = contracts_to_yaml(contracts, output_dir)
    except A2AImportError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Converted {len(paths)} contract(s) to {output_dir}/")
    for p in paths:
        typer.echo(f"  {p}")


if __name__ == "__main__":
    app()
```

**Step 6: Run tests to verify they pass**

```bash
cd plugins/eva-a2a && uv pip install -e "." && pytest tests/ -v
```

Expected: all PASS.

**Step 7: Commit**

```bash
git add plugins/eva-a2a/
git commit -m "feat(plugins): eva-a2a — A2A Agent Card JSON to Eva contract YAML importer"
```

---

### Task 18: `eva-mcp` — MCP server manifest importer

**MCP manifest format (JSON):**
```json
{
  "name": "file-tools",
  "tools": [
    {
      "name": "read_file",
      "description": "Read contents of a file",
      "inputSchema": {
        "type": "object",
        "required": ["path"],
        "properties": { "path": {"type": "string"} }
      }
    }
  ]
}
```

One Eva contract per tool. Same mapping as `eva-a2a`: `{server_name}.{tool_name}` → contract name.

**Files:**
- Create: `plugins/eva-mcp/eva_mcp/importer.py`
- Create: `plugins/eva-mcp/eva_mcp/cli.py`
- Create: `plugins/eva-mcp/tests/__init__.py`
- Create: `plugins/eva-mcp/tests/test_mcp_importer.py`
- Create: `plugins/eva-mcp/tests/fixtures/file_tools_manifest.json`

**Step 1: Create fixture**

```json
{
  "name": "file-tools",
  "tools": [
    {
      "name": "read_file",
      "description": "Read contents of a file from disk",
      "inputSchema": {
        "type": "object",
        "required": ["path"],
        "properties": {
          "path": {"type": "string"},
          "encoding": {"type": "string", "default": "utf-8"}
        }
      }
    },
    {
      "name": "write_file",
      "description": "Write content to a file",
      "inputSchema": {
        "type": "object",
        "required": ["path", "content"],
        "properties": {
          "path": {"type": "string"},
          "content": {"type": "string"}
        }
      }
    }
  ]
}
```

Save as: `plugins/eva-mcp/tests/fixtures/file_tools_manifest.json`

**Step 2: Write failing tests**

```python
# plugins/eva-mcp/tests/test_mcp_importer.py
import json
import pytest
from pathlib import Path
from eva_mcp.importer import import_mcp_manifest, contracts_to_yaml, MCPImportError

FIXTURES = Path(__file__).parent / "fixtures"


def test_import_produces_contracts_per_tool():
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    assert len(contracts) == 2


def test_import_contract_names():
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    names = [c.name for c in contracts]
    assert "file-tools.read_file" in names
    assert "file-tools.write_file" in names


def test_import_preserves_input_schema():
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    read = next(c for c in contracts if "read_file" in c.name)
    assert "path" in read.request_schema.get("required", [])
    assert "path" in read.request_schema.get("properties", {})


def test_import_sets_provider():
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    for c in contracts:
        assert c.provider == "file-tools"


def test_import_missing_name_raises():
    with pytest.raises(MCPImportError, match="name"):
        import_mcp_manifest({"tools": []})


def test_import_empty_tools_list():
    manifest = {"name": "empty-server", "tools": []}
    contracts = import_mcp_manifest(manifest)
    assert contracts == []


def test_import_tool_without_input_schema():
    manifest = {
        "name": "bare-tools",
        "tools": [{"name": "ping", "description": "Ping the server"}],
    }
    contracts = import_mcp_manifest(manifest)
    assert len(contracts) == 1
    assert contracts[0].request_schema == {}


def test_to_yaml_roundtrip(tmp_path):
    manifest = json.loads((FIXTURES / "file_tools_manifest.json").read_text())
    contracts = import_mcp_manifest(manifest)
    paths = contracts_to_yaml(contracts, tmp_path / "out")
    assert len(paths) == 2
    for p in paths:
        import yaml
        data = yaml.safe_load(p.read_text())
        assert "name" in data
        assert "provider" in data
        assert data["provider"] == "file-tools"
```

**Step 3: Run tests to verify they fail**

```bash
cd plugins/eva-mcp && pytest tests/ -v
```

Expected: `ModuleNotFoundError: No module named 'eva_mcp.importer'`

**Step 4: Implement the importer**

```python
# plugins/eva-mcp/eva_mcp/importer.py
from __future__ import annotations
from pathlib import Path
import yaml
from core.models import Contract, RetryPolicy


class MCPImportError(Exception):
    pass


def import_mcp_manifest(manifest: dict) -> list[Contract]:
    """
    Convert an MCP server manifest JSON dict into a list of Eva contracts.
    One contract is produced per tool in manifest['tools'].
    """
    name = manifest.get("name")
    if not name:
        raise MCPImportError("MCP manifest must have a 'name' field")

    contracts = []
    for tool in manifest.get("tools", []):
        tool_name = tool.get("name", "unknown")
        request_schema = tool.get("inputSchema", {})
        contracts.append(
            Contract(
                name=f"{name}.{tool_name}",
                provider=name,
                consumer=None,
                request_schema=request_schema,
                evaluators=[],
                retry_policy=RetryPolicy(),
            )
        )
    return contracts


def contracts_to_yaml(contracts: list[Contract], output_dir: Path) -> list[Path]:
    """Write each contract as a YAML file. Returns list of written paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for contract in contracts:
        filename = contract.name.replace("/", "_").replace(".", "_") + ".yaml"
        path = output_dir / filename
        data = {
            "name": contract.name,
            "provider": contract.provider,
            "request_schema": contract.request_schema,
            "evaluators": [e.model_dump() for e in contract.evaluators],
            "retry_policy": contract.retry_policy.model_dump(),
        }
        path.write_text(yaml.dump(data, sort_keys=False))
        paths.append(path)
    return paths
```

**Step 5: Implement the CLI**

```python
# plugins/eva-mcp/eva_mcp/cli.py
import json
import typer
from pathlib import Path
from eva_mcp.importer import import_mcp_manifest, contracts_to_yaml, MCPImportError

app = typer.Typer()


@app.command()
def convert(
    manifest_file: Path = typer.Argument(..., help="Path to MCP server manifest JSON file"),
    output_dir: Path = typer.Option(Path("contracts"), help="Output directory for YAML contracts"),
) -> None:
    """Convert an MCP server manifest JSON to Eva contract YAML files."""
    if not manifest_file.exists():
        typer.echo(f"Error: file not found: {manifest_file}", err=True)
        raise typer.Exit(1)

    try:
        manifest = json.loads(manifest_file.read_text())
        contracts = import_mcp_manifest(manifest)
        paths = contracts_to_yaml(contracts, output_dir)
    except MCPImportError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Converted {len(paths)} contract(s) to {output_dir}/")
    for p in paths:
        typer.echo(f"  {p}")


if __name__ == "__main__":
    app()
```

**Step 6: Run tests to verify they pass**

```bash
cd plugins/eva-mcp && uv pip install -e "." && pytest tests/ -v
```

Expected: all PASS.

**Step 7: Commit**

```bash
git add plugins/eva-mcp/
git commit -m "feat(plugins): eva-mcp — MCP server manifest JSON to Eva contract YAML importer"
```

---

## Final Verification

### Run the full test suite

```bash
pytest tests/ -v --tb=short
```

Expected output:
```
tests/server/test_health.py                PASSED
tests/server/test_registry.py             PASSED
tests/server/test_registry_hotreload.py   PASSED
tests/server/test_validation.py           PASSED
tests/server/test_proxy.py                PASSED
tests/server/test_gateway_evaluator.py    PASSED
tests/server/test_retry.py                PASSED
tests/server/test_routes_proxy.py         PASSED
tests/server/test_routes_invoke.py        PASSED
tests/server/test_arq_tasks.py            PASSED
tests/server/test_tracing.py              PASSED
tests/e2e/test_serve_command.py           PASSED
tests/e2e/test_server_e2e.py              PASSED
```

### Run plugin tests

```bash
pytest plugins/eva-a2a/tests/ -v
pytest plugins/eva-mcp/tests/ -v
pytest plugins/eva-otlp/tests/ -v
pytest plugins/eva-postgres/tests/ -v   # integration tests skipped without --integration
```

### Smoke test the CLI

```bash
# Start the server with an empty registry
eva serve --port 18080 &
curl http://localhost:18080/health
# Expected: {"status": "ok"}

# Convert an A2A agent card
eva-a2a convert path/to/agent_card.json --output-dir contracts/
# Expected: Converted N contract(s) to contracts/

# Convert an MCP manifest
eva-mcp convert path/to/manifest.json --output-dir contracts/

# Serve with generated contracts
eva serve --contracts-dir contracts/ --port 18081
```

### Verify the structured error response format

```bash
curl -s -X POST http://localhost:18080/v1/proxy \
  -H "Content-Type: application/json" \
  -d '{
    "target": "http://agent:8000/chat",
    "body": {"input": "test"},
    "evaluators": [{"name": "contains", "mode": "binary", "config": {"substring": "REQUIRED"}}],
    "max_retries": 2
  }' | python -m json.tool
```

Expected (when agent responds without "REQUIRED"):
```json
{
  "eva_status": "contract_violation",
  "attempts": 3,
  "violations": [
    {
      "evaluator": "contains",
      "score": 0.0,
      "reason": "Response does not contain 'REQUIRED'"
    }
  ],
  "request_id": "...",
  "trace_id": null
}
```

---

## Phase 3 Completion Checklist

- [ ] `eva serve` starts FastAPI gateway, loads contracts from directory
- [ ] Contract registry loads YAML files, hot-reloads on file change (watchfiles polling)
- [ ] `POST /v1/proxy` — dumb proxy with inline evaluation and retry
- [ ] `POST /v1/contract/invoke` — request schema validation then contract-aware proxy
- [ ] Retry engine injects `_eva_hint`, respects `max_retries` and `backoff_ms`
- [ ] Structured error response: `eva_status`, `attempts`, `violations`, `request_id`, `trace_id`
- [ ] ARQ task `evaluate_async` for fire-and-forget evaluation (requires Redis in production)
- [ ] OTEL spans throughout request lifecycle with noop fallback when opentelemetry not installed
- [ ] `eva-postgres` storage adapter — separate installable package
- [ ] `eva-otlp` OTLP exporter — separate installable package
- [ ] `eva-a2a` A2A Agent Card importer + `eva-a2a convert` CLI
- [ ] `eva-mcp` MCP manifest importer + `eva-mcp convert` CLI
- [ ] All server tests pass: `pytest tests/server/ tests/e2e/ -v`
- [ ] All plugin unit tests pass: `pytest plugins/eva-a2a/tests/ plugins/eva-mcp/tests/ plugins/eva-otlp/tests/ -v`

### Gate to Phase 4

Gateway API v1 is stable when: both `/v1/proxy` and `/v1/contract/invoke` handle all error cases with the structured error format, retry + self-healing works end-to-end, and at least one integration test verifies the full flow without mocks. Ecosystem builders depend on this API from this point.

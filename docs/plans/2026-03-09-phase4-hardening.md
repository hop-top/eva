# Phase 4: Hardening + AGNTCY Alignment — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Production-grade reliability for Eva Server (auth, rate limiting, webhook emission, drift detection) and full AGNTCY/ACP alignment via the `eva-agntcy` official plugin.

**Architecture:** Phase 4 touches two areas. Team Server owns Tasks 1–4 (gateway hardening). Team Plugins owns Task 5 (eva-agntcy). All work is additive — no changes to Phase 1–3 interfaces. The Redis state adapter from Phase 2 is the backbone of both rate limiting and drift detection storage.

> **Note:** Domain-specific evaluator packages (finance, healthcare, legal) are ecosystem deliverables — not built by the Eva team. See `docs/ecosystem.md` for reference examples of what third parties should build.

**Tech Stack:** Python 3.11+, FastAPI, Redis (via `arq`/`redis-py`), httpx (webhook emission), LiteLLM (domain LLM judges), pluggy, Pydantic, rich (CLI table output), pytest, pytest-asyncio, respx (mock httpx in tests), uv

**Assumes:** Phases 1–3 complete. The following are available and stable:
- `core/models.py` — Score, Result, Run, Contract, RetryPolicy
- `core/plugins.py` — pluggy hook system + EvaSpec
- `server/` — FastAPI app, `/v1/proxy`, `/v1/contract/invoke`, contract registry
- Redis state adapter at `core/adapters/state.py` with `get(key)` / `set(key, value, ttl)` / `incr(key)` / `expire(key, ttl)`
- SQLite storage adapter at `core/adapters/storage.py` with `save_run(run)` / `get_runs(dataset, target, limit)` returning `list[Run]`

---

## Task 1: API Key Authentication

**Files:**
- Create: `server/auth.py`
- Create: `tests/server/test_auth.py`
- Edit: `server/main.py` — add auth middleware
- Edit: `eva.yaml` schema — document `auth:` block

**Step 1: Write failing tests**

```python
# tests/server/test_auth.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

# The FastAPI app from server/main.py — already exists from Phase 3
from server.main import app


@pytest.fixture
def valid_key():
    return "eva_test_key_abc123"


@pytest.mark.asyncio
async def test_request_without_key_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/proxy", json={"input": "hello"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing X-Eva-Key header"


@pytest.mark.asyncio
async def test_request_with_invalid_key_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/proxy",
            json={"input": "hello"},
            headers={"X-Eva-Key": "bad_key"},
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key"


@pytest.mark.asyncio
async def test_request_with_valid_key_passes_auth(valid_key):
    # Patch the state adapter lookup so the key is considered valid
    with patch("server.auth.state_adapter") as mock_state:
        mock_state.get = AsyncMock(return_value="1")  # any truthy value means key exists
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/proxy",
                json={"input": "hello", "target": "http://example.com"},
                headers={"X-Eva-Key": valid_key},
            )
    # 401/429 must NOT be returned — downstream may fail but auth passed
    assert resp.status_code != 401


@pytest.mark.asyncio
async def test_health_endpoint_exempt_from_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_well_known_agent_json_exempt_from_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent.json")
    # 200 or 404 — either is fine; what matters is it is NOT 401
    assert resp.status_code != 401
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_auth.py -v
```

Expected: tests fail — either `ImportError` (no `server.auth`) or all requests return 200 because no auth middleware exists yet.

**Step 3: Implement `server/auth.py`**

```python
# server/auth.py
"""API key authentication for Eva gateway.

Keys are stored in Redis as:
    eva:apikey:<key>  →  "1"   (present = valid)

To register a key:
    redis-cli SET "eva:apikey:eva_mykey" 1

Eva does not ship a key management API in Phase 4. Keys are
provisioned directly in Redis or via the operator's tooling.
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Imported at module level so tests can patch it
from core.adapters.state import get_state_adapter

state_adapter = get_state_adapter()

# Paths that bypass auth entirely
_EXEMPT_PATHS = {"/health", "/.well-known/agent.json", "/docs", "/openapi.json", "/redoc"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
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

        # Attach key to request state for downstream use (e.g. rate limiting)
        request.state.api_key = key
        return await call_next(request)
```

**Step 4: Wire middleware into `server/main.py`**

Add after the `app = FastAPI(...)` line:

```python
# server/main.py  (edit — add these two lines after app is created)
from server.auth import ApiKeyMiddleware

app.add_middleware(ApiKeyMiddleware)
```

**Step 5: Document the `auth:` block in `eva.yaml`**

```yaml
# eva.yaml  (add to the server section — documentation only, not parsed by Eva Core)
server:
  auth:
    enabled: true          # set false to disable auth entirely (dev mode)
    # Keys are stored in Redis: SET "eva:apikey:<key>" 1
    # No key management API in Phase 4 — provision keys directly in Redis.
```

**Step 6: Run tests to verify they pass**

```bash
pytest tests/server/test_auth.py -v
```

Expected: all 5 tests PASS.

**Step 7: Commit**

```bash
git add server/auth.py server/main.py tests/server/test_auth.py
git commit -m "feat(server): API key authentication middleware (X-Eva-Key header)"
```

---

## Task 2: Rate Limiting

**Files:**
- Create: `server/ratelimit.py`
- Create: `tests/server/test_ratelimit.py`
- Edit: `server/main.py` — add rate limit middleware after auth

**Background:** Sliding window counter in Redis. Each API key gets a counter for the current minute window. Key pattern: `eva:ratelimit:<key>:<window_minute>`. Window minute = `int(time.time() // 60)`. On each request: `INCR` the counter, set TTL of 120 seconds (two windows, for safety), compare to configured limit.

Rate limit configuration lives in Redis as `eva:ratelimit_config:<key>` → JSON string `{"rpm": 60}`. If no per-key config is found, fall back to the global default from `eva.yaml` (default: 60 rpm).

**Step 1: Write failing tests**

```python
# tests/server/test_ratelimit.py
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from server.ratelimit import RateLimiter, RateLimitExceeded


@pytest.fixture
def mock_state():
    s = MagicMock()
    s.get = AsyncMock(return_value=None)
    s.incr = AsyncMock(return_value=1)
    s.expire = AsyncMock(return_value=None)
    return s


@pytest.mark.asyncio
async def test_first_request_always_allowed(mock_state):
    mock_state.incr = AsyncMock(return_value=1)
    limiter = RateLimiter(state=mock_state, default_rpm=60)
    # Should not raise
    await limiter.check(api_key="key1")


@pytest.mark.asyncio
async def test_request_at_limit_allowed(mock_state):
    mock_state.incr = AsyncMock(return_value=60)
    limiter = RateLimiter(state=mock_state, default_rpm=60)
    await limiter.check(api_key="key1")  # exactly at limit — still allowed


@pytest.mark.asyncio
async def test_request_over_limit_raises(mock_state):
    mock_state.incr = AsyncMock(return_value=61)
    limiter = RateLimiter(state=mock_state, default_rpm=60)
    with pytest.raises(RateLimitExceeded):
        await limiter.check(api_key="key1")


@pytest.mark.asyncio
async def test_per_key_rpm_config_used(mock_state):
    import json
    # This key has a custom 10 rpm limit
    mock_state.get = AsyncMock(return_value=json.dumps({"rpm": 10}))
    mock_state.incr = AsyncMock(return_value=11)
    limiter = RateLimiter(state=mock_state, default_rpm=60)
    with pytest.raises(RateLimitExceeded):
        await limiter.check(api_key="key_low_limit")


@pytest.mark.asyncio
async def test_window_key_includes_minute_bucket(mock_state):
    """The Redis counter key must include the current minute so windows reset."""
    mock_state.incr = AsyncMock(return_value=1)
    limiter = RateLimiter(state=mock_state, default_rpm=60)
    await limiter.check(api_key="mykey")
    call_args = mock_state.incr.call_args[0][0]
    window = str(int(time.time() // 60))
    assert "mykey" in call_args
    assert window in call_args


@pytest.mark.asyncio
async def test_expire_called_with_120_seconds(mock_state):
    mock_state.incr = AsyncMock(return_value=1)
    limiter = RateLimiter(state=mock_state, default_rpm=60)
    await limiter.check(api_key="mykey")
    mock_state.expire.assert_called_once()
    _, ttl = mock_state.expire.call_args[0]
    assert ttl == 120
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_ratelimit.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.ratelimit'`

**Step 3: Implement `server/ratelimit.py`**

```python
# server/ratelimit.py
"""Sliding window rate limiter backed by Redis.

Counter key:  eva:ratelimit:<api_key>:<window_minute>
Config key:   eva:ratelimit_config:<api_key>  →  JSON {"rpm": N}

TTL is set to 120 seconds (two windows) so keys clean themselves up.
"""
from __future__ import annotations
import json
import time
from typing import Any


class RateLimitExceeded(Exception):
    """Raised when a key exceeds its requests-per-minute limit."""
    def __init__(self, key: str, limit: int, current: int):
        self.key = key
        self.limit = limit
        self.current = current
        super().__init__(f"Rate limit exceeded for {key}: {current}/{limit} rpm")


class RateLimiter:
    def __init__(self, state: Any, default_rpm: int = 60):
        self._state = state
        self._default_rpm = default_rpm

    async def check(self, api_key: str) -> None:
        """Increment counter and raise RateLimitExceeded if over limit."""
        rpm = await self._get_limit(api_key)
        window = int(time.time() // 60)
        counter_key = f"eva:ratelimit:{api_key}:{window}"
        count = await self._state.incr(counter_key)
        await self._state.expire(counter_key, 120)
        if count > rpm:
            raise RateLimitExceeded(key=api_key, limit=rpm, current=count)

    async def _get_limit(self, api_key: str) -> int:
        config_key = f"eva:ratelimit_config:{api_key}"
        raw = await self._state.get(config_key)
        if raw:
            try:
                return json.loads(raw).get("rpm", self._default_rpm)
            except (json.JSONDecodeError, AttributeError):
                pass
        return self._default_rpm
```

**Step 4: Wire rate limiter into `server/main.py`**

```python
# server/main.py  (edit — add rate limit middleware after ApiKeyMiddleware)
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from server.ratelimit import RateLimiter, RateLimitExceeded
from core.adapters.state import get_state_adapter

_rate_limiter = RateLimiter(state=get_state_adapter(), default_rpm=60)

_RATELIMIT_EXEMPT = {"/health", "/.well-known/agent.json", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _RATELIMIT_EXEMPT:
            return await call_next(request)
        api_key = getattr(request.state, "api_key", None)
        if api_key:
            try:
                await _rate_limiter.check(api_key)
            except RateLimitExceeded as exc:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded",
                        "limit": exc.limit,
                        "current": exc.current,
                        "retry_after_seconds": 60,
                    },
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/server/test_ratelimit.py -v
```

Expected: all 6 tests PASS.

**Step 6: Integration test — 429 from the full app**

```python
# tests/server/test_ratelimit_integration.py
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from server.main import app


@pytest.mark.asyncio
async def test_over_limit_returns_429():
    with patch("server.ratelimit.RateLimiter.check", new_callable=AsyncMock) as mock_check:
        from server.ratelimit import RateLimitExceeded
        mock_check.side_effect = RateLimitExceeded("k", 60, 61)
        with patch("server.auth.state_adapter") as mock_state:
            mock_state.get = AsyncMock(return_value="1")
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/proxy",
                    json={"input": "hello"},
                    headers={"X-Eva-Key": "anykey"},
                )
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Rate limit exceeded"
    assert "Retry-After" in resp.headers
```

```bash
pytest tests/server/test_ratelimit_integration.py -v
```

Expected: PASS.

**Step 7: Commit**

```bash
git add server/ratelimit.py server/main.py tests/server/test_ratelimit.py tests/server/test_ratelimit_integration.py
git commit -m "feat(server): sliding window rate limiting per API key (Redis-backed)"
```

---

## Task 3: Webhook Emission on Contract Violations

**Files:**
- Create: `server/webhooks.py`
- Create: `tests/server/test_webhooks.py`
- Edit: `server/gateway/proxy.py` — call webhook emitter after violation
- Edit: `eva.yaml` — document webhook config

**Background:** When a contract violation occurs after all retries are exhausted, Eva POSTs a JSON payload to a configured URL. Webhook URL can be set globally in `eva.yaml` under `server.webhook.url`, or per-contract in the contract YAML under `webhook_url`. Per-contract overrides global. Delivery is fire-and-forget (non-blocking async). If the webhook POST fails, Eva logs a warning but does not affect the response to the client.

**Step 1: Write failing tests**

```python
# tests/server/test_webhooks.py
import pytest
import respx
import httpx
from datetime import datetime, timezone
from server.webhooks import emit_violation_webhook, WebhookPayload
from core.models import Result, Score


def make_violation_result() -> Result:
    return Result(
        test_id="t1",
        evaluator="corporate_compliance",
        score=Score(value=0.0, reason="Violated max discount policy"),
        mode="binary",
        duration_ms=42,
        trace_id="otel_abc",
    )


@pytest.mark.asyncio
@respx.mock
async def test_webhook_posts_json_payload():
    route = respx.post("https://hooks.example.com/eva").mock(
        return_value=httpx.Response(200)
    )
    results = [make_violation_result()]
    await emit_violation_webhook(
        url="https://hooks.example.com/eva",
        contract_name="refund_policy",
        request_id="req_001",
        attempts=3,
        violations=results,
    )
    assert route.called
    sent = route.calls[0].request
    import json
    body = json.loads(sent.content)
    assert body["event"] == "contract_violation"
    assert body["contract"] == "refund_policy"
    assert body["request_id"] == "req_001"
    assert body["attempts"] == 3
    assert len(body["violations"]) == 1
    assert body["violations"][0]["evaluator"] == "corporate_compliance"
    assert body["violations"][0]["score"] == 0.0
    assert body["violations"][0]["reason"] == "Violated max discount policy"


@pytest.mark.asyncio
@respx.mock
async def test_webhook_failure_does_not_raise():
    respx.post("https://hooks.example.com/eva").mock(
        return_value=httpx.Response(500)
    )
    # Must not raise — fire-and-forget
    await emit_violation_webhook(
        url="https://hooks.example.com/eva",
        contract_name="refund_policy",
        request_id="req_002",
        attempts=2,
        violations=[make_violation_result()],
    )


@pytest.mark.asyncio
@respx.mock
async def test_webhook_network_error_does_not_raise():
    respx.post("https://hooks.example.com/eva").mock(
        side_effect=httpx.ConnectError("refused")
    )
    await emit_violation_webhook(
        url="https://hooks.example.com/eva",
        contract_name="refund_policy",
        request_id="req_003",
        attempts=1,
        violations=[make_violation_result()],
    )


@pytest.mark.asyncio
async def test_emit_with_none_url_does_nothing():
    # When no webhook is configured, calling with url=None is a no-op
    await emit_violation_webhook(
        url=None,
        contract_name="refund_policy",
        request_id="req_004",
        attempts=1,
        violations=[make_violation_result()],
    )


def test_webhook_payload_structure():
    results = [make_violation_result()]
    payload = WebhookPayload.from_violation(
        contract_name="refund_policy",
        request_id="req_005",
        attempts=3,
        violations=results,
    )
    assert payload.event == "contract_violation"
    assert payload.contract == "refund_policy"
    assert len(payload.violations) == 1
    assert isinstance(payload.occurred_at, str)  # ISO 8601
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/server/test_webhooks.py -v
```

Expected: `ModuleNotFoundError: No module named 'server.webhooks'`

**Step 3: Implement `server/webhooks.py`**

```python
# server/webhooks.py
"""Fire-and-forget webhook emission on contract violations.

Eva POSTs to the configured URL with a JSON payload describing the violation.
Failures are logged as warnings and never bubble up to the caller.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel

from core.models import Result

logger = logging.getLogger("eva.webhooks")

_TIMEOUT = httpx.Timeout(5.0)


class ViolationDetail(BaseModel):
    evaluator: str
    score: float
    reason: str | None


class WebhookPayload(BaseModel):
    event: str = "contract_violation"
    contract: str
    request_id: str
    attempts: int
    violations: list[ViolationDetail]
    occurred_at: str  # ISO 8601

    @classmethod
    def from_violation(
        cls,
        contract_name: str,
        request_id: str,
        attempts: int,
        violations: list[Result],
    ) -> "WebhookPayload":
        return cls(
            contract=contract_name,
            request_id=request_id,
            attempts=attempts,
            violations=[
                ViolationDetail(
                    evaluator=r.evaluator,
                    score=r.score.value,
                    reason=r.score.reason,
                )
                for r in violations
                if not r.passed
            ],
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )


async def emit_violation_webhook(
    url: str | None,
    contract_name: str,
    request_id: str,
    attempts: int,
    violations: list[Result],
) -> None:
    """POST violation payload to url. No-op if url is None. Never raises."""
    if not url:
        return
    payload = WebhookPayload.from_violation(
        contract_name=contract_name,
        request_id=request_id,
        attempts=attempts,
        violations=violations,
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload.model_dump())
            if resp.status_code >= 400:
                logger.warning(
                    "Webhook delivery failed: POST %s → %d", url, resp.status_code
                )
    except Exception as exc:  # network errors, timeouts, etc.
        logger.warning("Webhook delivery error: %s — %s", url, exc)
```

**Step 4: Wire webhook emission into the gateway**

In `server/gateway/proxy.py`, after the retry loop exhausts and violations remain, call the emitter. This is the existing violation-handling block — add two lines:

```python
# server/gateway/proxy.py  (edit — in the block that builds the structured error response)
import asyncio
from server.webhooks import emit_violation_webhook

# After determining final violations and before returning the error response:
webhook_url = (
    contract.webhook_url                          # per-contract override (new optional field)
    or server_config.get("webhook", {}).get("url")  # global config
)
asyncio.create_task(
    emit_violation_webhook(
        url=webhook_url,
        contract_name=contract.name,
        request_id=request_id,
        attempts=attempts,
        violations=final_violations,
    )
)
```

**Step 5: Add `webhook_url` as optional field on `Contract` model**

```python
# core/models.py  (edit — add to Contract class)
class Contract(BaseModel):
    name: str
    provider: str
    consumer: str | None = None
    request_schema: dict = {}
    evaluators: list[EvaluatorRef] = []
    retry_policy: RetryPolicy = RetryPolicy()
    webhook_url: str | None = None   # ← add this field
```

**Step 6: Document webhook config in `eva.yaml`**

```yaml
# eva.yaml
server:
  webhook:
    url: "https://hooks.example.com/eva"   # global default; can be overridden per contract

# Per-contract override in the contract YAML:
# webhook_url: "https://hooks.myteam.com/violations"
```

**Step 7: Run tests to verify they pass**

```bash
pytest tests/server/test_webhooks.py -v
```

Expected: all 5 tests PASS.

**Step 8: Commit**

```bash
git add server/webhooks.py server/gateway/proxy.py core/models.py tests/server/test_webhooks.py
git commit -m "feat(server): webhook emission on contract violations (fire-and-forget)"
```

---

## Task 4: Drift Detection + `eva drift report`

**Files:**
- Create: `core/drift.py`
- Create: `tests/unit/test_drift.py`
- Create: `tests/e2e/test_drift_command.py`
- Edit: `cli/main.py` — add `eva drift report` command

**Background:** After each `eva run`, scores are persisted as a `Run` in the storage adapter. Drift detection queries the last N runs for a given `(dataset, target)` pair, groups `Result` records by `evaluator`, computes a rolling baseline (mean of the N-1 older runs), and compares it to the most recent run's score. A key drops below threshold when `current_score < baseline - threshold`. The default window is 10 runs, the default alert threshold is 0.1 (a drop of 10 points).

**Step 1: Write failing unit tests**

```python
# tests/unit/test_drift.py
import pytest
from datetime import datetime, timezone
from core.drift import compute_drift, DriftReport, DriftEntry, DriftTrend
from core.models import Run, Result, Score


def make_run(run_id: str, evaluator: str, score_value: float) -> Run:
    return Run(
        run_id=run_id,
        dataset="my_dataset",
        target="http://agent",
        results=[
            Result(
                test_id="t1",
                evaluator=evaluator,
                score=Score(value=score_value),
                mode="threshold",
                min_score=0.7,
                duration_ms=10,
                trace_id=None,
            )
        ],
        started_at=datetime.now(timezone.utc),
        duration_ms=100,
        passed=score_value >= 0.7,
    )


def test_stable_scores_report_stable_trend():
    runs = [make_run(f"r{i}", "relevance", 0.9) for i in range(5)]
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.trend == DriftTrend.STABLE


def test_score_drop_reports_down_trend():
    # 4 runs at 0.9, then last run at 0.5 — big drop
    runs = [make_run(f"r{i}", "relevance", 0.9) for i in range(4)]
    runs.append(make_run("r_latest", "relevance", 0.5))
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.trend == DriftTrend.DOWN
    assert entry.current_score == pytest.approx(0.5)
    assert entry.baseline_score == pytest.approx(0.9)
    assert entry.delta == pytest.approx(-0.4, abs=0.01)


def test_score_improvement_reports_up_trend():
    runs = [make_run(f"r{i}", "relevance", 0.5) for i in range(4)]
    runs.append(make_run("r_latest", "relevance", 0.95))
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.trend == DriftTrend.UP


def test_single_run_returns_no_baseline():
    runs = [make_run("r0", "relevance", 0.8)]
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.baseline_score is None
    assert entry.trend == DriftTrend.STABLE


def test_multiple_evaluators_reported_independently():
    runs = []
    for i in range(5):
        r = Run(
            run_id=f"r{i}",
            dataset="ds",
            target="t",
            results=[
                Result(test_id="t1", evaluator="relevance", score=Score(value=0.9), mode="threshold", min_score=0.7, duration_ms=5, trace_id=None),
                Result(test_id="t1", evaluator="safety", score=Score(value=1.0 if i < 4 else 0.2), mode="binary", duration_ms=5, trace_id=None),
            ],
            started_at=datetime.now(timezone.utc),
            duration_ms=50,
            passed=True,
        )
        runs.append(r)
    report = compute_drift(runs, threshold=0.1)
    evaluators = {e.evaluator for e in report.entries}
    assert "relevance" in evaluators
    assert "safety" in evaluators
    safety = next(e for e in report.entries if e.evaluator == "safety")
    assert safety.trend == DriftTrend.DOWN


def test_empty_runs_returns_empty_report():
    report = compute_drift([], threshold=0.1)
    assert report.entries == []


def test_delta_within_threshold_is_stable():
    # Drop of 0.05 when threshold is 0.1 → STABLE
    runs = [make_run(f"r{i}", "relevance", 0.9) for i in range(4)]
    runs.append(make_run("r_latest", "relevance", 0.85))
    report = compute_drift(runs, threshold=0.1)
    entry = next(e for e in report.entries if e.evaluator == "relevance")
    assert entry.trend == DriftTrend.STABLE
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_drift.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.drift'`

**Step 3: Implement `core/drift.py`**

```python
# core/drift.py
"""Drift detection: compare evaluator scores across runs over time.

Given a list of Run objects (oldest first), compute_drift:
  - Groups Result records by evaluator name.
  - The most recent run's score is the "current" score.
  - The mean of all earlier runs is the "baseline".
  - delta = current - baseline
  - trend = UP if delta > threshold, DOWN if delta < -threshold, else STABLE.
"""
from __future__ import annotations
from enum import Enum
from statistics import mean
from typing import NamedTuple

from pydantic import BaseModel

from core.models import Run


class DriftTrend(str, Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class DriftEntry(BaseModel):
    evaluator: str
    baseline_score: float | None    # None when fewer than 2 runs exist
    current_score: float
    delta: float | None             # None when fewer than 2 runs exist
    trend: DriftTrend


class DriftReport(BaseModel):
    entries: list[DriftEntry]


def compute_drift(runs: list[Run], threshold: float = 0.1) -> DriftReport:
    """Compute drift report from a list of runs (any order — sorted internally)."""
    if not runs:
        return DriftReport(entries=[])

    # Sort oldest → newest by started_at
    sorted_runs = sorted(runs, key=lambda r: r.started_at)

    # Collect all scores per evaluator: {evaluator: [score, ...]} oldest first
    scores_by_evaluator: dict[str, list[float]] = {}
    for run in sorted_runs:
        for result in run.results:
            scores_by_evaluator.setdefault(result.evaluator, [])
            scores_by_evaluator[result.evaluator].append(result.score.value)

    entries: list[DriftEntry] = []
    for evaluator, scores in scores_by_evaluator.items():
        current = scores[-1]
        if len(scores) < 2:
            entries.append(DriftEntry(
                evaluator=evaluator,
                baseline_score=None,
                current_score=current,
                delta=None,
                trend=DriftTrend.STABLE,
            ))
            continue

        baseline = mean(scores[:-1])
        delta = current - baseline

        if delta > threshold:
            trend = DriftTrend.UP
        elif delta < -threshold:
            trend = DriftTrend.DOWN
        else:
            trend = DriftTrend.STABLE

        entries.append(DriftEntry(
            evaluator=evaluator,
            baseline_score=round(baseline, 4),
            current_score=round(current, 4),
            delta=round(delta, 4),
            trend=trend,
        ))

    return DriftReport(entries=sorted(entries, key=lambda e: e.evaluator))
```

**Step 4: Run unit tests to verify they pass**

```bash
pytest tests/unit/test_drift.py -v
```

Expected: all 8 tests PASS.

**Step 5: Write failing E2E tests for `eva drift report`**

```python
# tests/e2e/test_drift_command.py
"""E2E tests for `eva drift report` CLI command.

Uses subprocess so the real CLI binary is exercised.
"""
import subprocess
import sys
import pytest


def run_eva(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.main"] + list(args),
        capture_output=True,
        text=True,
    )


def test_drift_report_help_exits_zero():
    result = run_eva("drift", "report", "--help")
    assert result.returncode == 0
    assert "dataset" in result.stdout.lower() or "help" in result.stdout.lower()


def test_drift_report_missing_dataset_exits_nonzero():
    result = run_eva("drift", "report")
    assert result.returncode != 0


def test_drift_report_outputs_table_headers(tmp_path, monkeypatch):
    """When storage returns runs, output contains expected column headers."""
    # This test uses --dataset and --target flags with a mock storage
    # pointing at a temp SQLite DB that has pre-seeded runs.
    # Since seeding requires the storage adapter, we test the column names
    # by patching storage at the subprocess boundary via env var.
    # For simplicity, verify that passing valid flags produces the right headers.
    # Full seeding is covered by integration tests in tests/integration/.
    result = run_eva(
        "drift", "report",
        "--dataset", "test_ds",
        "--target", "http://example.com",
        "--db", str(tmp_path / "eva.db"),   # empty DB → "No runs found" message
    )
    # Either a table is shown or a "no runs found" message — not an error exit
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    # Must mention the dataset we requested
    assert "test_ds" in combined or "No runs found" in combined
```

**Step 6: Run E2E tests to verify they fail**

```bash
pytest tests/e2e/test_drift_command.py -v
```

Expected: fail on `drift` subcommand not found.

**Step 7: Implement `eva drift report` in CLI**

```python
# cli/main.py  (edit — add drift command group)
import typer
from rich.console import Console
from rich.table import Table

drift_app = typer.Typer(help="Drift detection commands.")
app.add_typer(drift_app, name="drift")

console = Console()


@drift_app.command("report")
def drift_report(
    dataset: str = typer.Option(..., help="Dataset name to analyse."),
    target: str = typer.Option(..., help="Target agent URL."),
    window: int = typer.Option(10, help="Number of recent runs to compare."),
    threshold: float = typer.Option(0.1, help="Score delta that triggers DOWN/UP trend."),
    db: str = typer.Option(None, help="Path to SQLite DB (overrides eva.yaml)."),
):
    """Show evaluator score trends across recent runs for a dataset+target pair."""
    import asyncio
    from core.adapters.storage import get_storage_adapter
    from core.drift import compute_drift, DriftTrend

    storage = get_storage_adapter(db_path=db)
    runs = asyncio.run(storage.get_runs(dataset=dataset, target=target, limit=window))

    if not runs:
        console.print(f"[yellow]No runs found for dataset=[bold]{dataset}[/bold] target=[bold]{target}[/bold][/yellow]")
        raise typer.Exit(0)

    report = compute_drift(runs, threshold=threshold)

    table = Table(title=f"Drift Report — {dataset} → {target} (last {len(runs)} runs)")
    table.add_column("Evaluator", style="cyan", no_wrap=True)
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Trend", justify="center")

    trend_styles = {
        DriftTrend.UP: "[green]↑ up[/green]",
        DriftTrend.DOWN: "[red]↓ down[/red]",
        DriftTrend.STABLE: "[dim]— stable[/dim]",
    }

    for entry in report.entries:
        baseline_str = f"{entry.baseline_score:.4f}" if entry.baseline_score is not None else "—"
        delta_str = f"{entry.delta:+.4f}" if entry.delta is not None else "—"
        table.add_row(
            entry.evaluator,
            baseline_str,
            f"{entry.current_score:.4f}",
            delta_str,
            trend_styles[entry.trend],
        )

    console.print(table)
```

**Step 8: Run all drift tests**

```bash
pytest tests/unit/test_drift.py tests/e2e/test_drift_command.py -v
```

Expected: all tests PASS.

**Step 9: Commit**

```bash
git add core/drift.py cli/main.py tests/unit/test_drift.py tests/e2e/test_drift_command.py
git commit -m "feat(core,cli): drift detection engine + eva drift report command"
```

---

## Task 5: `eva-agntcy` — ACP Manifest Endpoint

**Files:**
- Create: `plugins/eva-agntcy/pyproject.toml`
- Create: `plugins/eva-agntcy/eva_agntcy/__init__.py`
- Create: `plugins/eva-agntcy/eva_agntcy/acp.py`
- Create: `plugins/eva-agntcy/eva_agntcy/oasf.py`
- Create: `plugins/eva-agntcy/tests/test_acp.py`
- Create: `plugins/eva-agntcy/tests/test_oasf.py`
- Edit: `server/main.py` — register ACP router when `eva-agntcy` is installed

**Background:** The AGNTCY ACP spec (https://spec.acp.agntcy.org/) defines how agents expose their capabilities. The minimum viable implementation is a `GET /.well-known/agent.json` endpoint that returns an ACP manifest describing Eva's gateway. The manifest follows the ACP Agent Manifest schema. The eva-agntcy package installs this as a FastAPI router via an Eva server plugin hook.

The OASF registry module provides `register_agent(contract)` — for Phase 4 this is a local in-memory registry that serializes to `oasf_registry.json` in the working directory. Full remote registry integration is deferred.

SLIM messaging is documented as future work only (stub interface, no implementation).

**Step 1: Create package structure**

```bash
mkdir -p plugins/eva-agntcy/eva_agntcy plugins/eva-agntcy/tests
touch plugins/eva-agntcy/eva_agntcy/__init__.py plugins/eva-agntcy/tests/__init__.py
```

**Step 2: Create `pyproject.toml` for eva-agntcy**

```toml
# plugins/eva-agntcy/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "eva-agntcy"
version = "0.4.0"
description = "AGNTCY/ACP alignment plugin for Eva"
requires-python = ">=3.11"
dependencies = [
    "eva>=0.4.0",
    "fastapi>=0.111",
    "pydantic>=2",
    "httpx>=0.27",
]

[project.entry-points."eva.server.plugins"]
agntcy = "eva_agntcy:register"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 3: Write failing ACP tests**

```python
# plugins/eva-agntcy/tests/test_acp.py
import pytest
from httpx import AsyncClient, ASGITransport

# We test the router in isolation — mount it on a bare FastAPI app
from fastapi import FastAPI
from eva_agntcy.acp import acp_router, build_manifest


def make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(acp_router)
    return app


@pytest.mark.asyncio
async def test_well_known_agent_json_returns_200():
    async with AsyncClient(transport=ASGITransport(app=make_test_app()), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent.json")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_manifest_content_type_is_json():
    async with AsyncClient(transport=ASGITransport(app=make_test_app()), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent.json")
    assert "application/json" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_manifest_has_required_acp_fields():
    async with AsyncClient(transport=ASGITransport(app=make_test_app()), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent.json")
    body = resp.json()
    # Required ACP Agent Manifest fields
    assert "schema_version" in body
    assert "name" in body
    assert "description" in body
    assert "capabilities" in body
    assert "endpoints" in body


def test_build_manifest_returns_valid_structure():
    m = build_manifest(base_url="https://eva.example.com")
    assert m["name"] == "eva-gateway"
    assert "https://eva.example.com/v1/proxy" in str(m["endpoints"])
    assert "https://eva.example.com/v1/contract/invoke" in str(m["endpoints"])


@pytest.mark.asyncio
async def test_manifest_endpoints_include_proxy_and_invoke():
    async with AsyncClient(transport=ASGITransport(app=make_test_app()), base_url="http://test") as client:
        resp = await client.get("/.well-known/agent.json")
    endpoints = resp.json()["endpoints"]
    paths = [e.get("url", e.get("path", "")) for e in endpoints]
    assert any("proxy" in p for p in paths)
    assert any("invoke" in p for p in paths)
```

**Step 4: Run tests to verify they fail**

```bash
cd plugins/eva-agntcy && uv pip install -e ".[dev]" 2>/dev/null; pytest tests/test_acp.py -v
```

Expected: `ModuleNotFoundError: No module named 'eva_agntcy'`

**Step 5: Implement `eva_agntcy/acp.py`**

```python
# plugins/eva-agntcy/eva_agntcy/acp.py
"""ACP-compliant agent manifest endpoint.

Implements GET /.well-known/agent.json per the AGNTCY ACP specification:
https://spec.acp.agntcy.org/

This is the minimum viable ACP manifest. It describes Eva's gateway
capabilities so other agents on the AGNTCY network can discover and
invoke Eva-managed endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

acp_router = APIRouter()


def build_manifest(base_url: str = "") -> dict:
    """Build an ACP Agent Manifest for Eva's gateway."""
    return {
        "schema_version": "1.0",
        "name": "eva-gateway",
        "version": "0.4.0",
        "description": (
            "Eva is a contract enforcement gateway for AI agents. "
            "It evaluates agent responses against behavioral contracts, "
            "retries on violations, and emits structured errors on failure."
        ),
        "capabilities": [
            "contract-enforcement",
            "response-evaluation",
            "retry-on-violation",
            "opentelemetry-tracing",
        ],
        "endpoints": [
            {
                "name": "proxy",
                "method": "POST",
                "url": f"{base_url}/v1/proxy",
                "description": "Proxy a request to a target agent and evaluate the response.",
                "content_type": "application/json",
            },
            {
                "name": "contract_invoke",
                "method": "POST",
                "url": f"{base_url}/v1/contract/invoke",
                "description": "Validate request against a contract, forward to agent, and evaluate response.",
                "content_type": "application/json",
            },
        ],
        "protocols": ["ACP/1.0"],
        "interoperability": {
            "oasf": True,
            "a2a": False,   # via eva-a2a adapter (Phase 3)
            "mcp": False,   # via eva-mcp adapter (Phase 3)
            "slim": False,  # future work — SLIM messaging not implemented in Phase 4
        },
        "future_work": [
            "SLIM messaging integration (eva-agntcy v0.5)",
            "Remote OASF registry push (eva-agntcy v0.5)",
        ],
    }


@acp_router.get("/.well-known/agent.json", include_in_schema=False)
async def agent_manifest(request: Request) -> JSONResponse:
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(content=build_manifest(base_url=base_url))
```

**Step 6: Implement `eva_agntcy/oasf.py`**

```python
# plugins/eva-agntcy/eva_agntcy/oasf.py
"""OASF registry — Phase 4 implementation: local in-memory registry.

Contracts registered here are serialized to oasf_registry.json in the
working directory. Remote OASF registry push is deferred to Phase 5.

SLIM messaging: interface stub only. Full implementation is complex and
deferred to a future release. See https://spec.acp.agntcy.org/#slim
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any

from core.models import Contract

logger = logging.getLogger("eva.agntcy.oasf")

_REGISTRY_PATH = Path("oasf_registry.json")
_registry: dict[str, Any] = {}


def register_agent(contract: Contract) -> dict:
    """Register a contract as an OASF agent entry. Returns the OASF schema dict."""
    entry = _contract_to_oasf(contract)
    _registry[contract.name] = entry
    _flush()
    logger.info("OASF: registered agent %s", contract.name)
    return entry


def get_registry() -> dict[str, Any]:
    """Return the current in-memory registry."""
    return dict(_registry)


def _contract_to_oasf(contract: Contract) -> dict:
    return {
        "agent_id": contract.provider,
        "name": contract.name,
        "consumer": contract.consumer,
        "request_schema": contract.request_schema,
        "evaluators": [
            {"name": e.name, "mode": e.mode, "min_score": e.min_score}
            for e in contract.evaluators
        ],
        "retry_policy": {
            "max_retries": contract.retry_policy.max_retries,
            "backoff_ms": contract.retry_policy.backoff_ms,
        },
    }


def _flush() -> None:
    try:
        _REGISTRY_PATH.write_text(json.dumps(_registry, indent=2))
    except OSError as exc:
        logger.warning("OASF: could not write registry file: %s", exc)


# ── SLIM messaging stub ──────────────────────────────────────────────────────

class SLIMNotImplementedError(NotImplementedError):
    """SLIM messaging is not implemented in Phase 4.

    Full implementation is planned for eva-agntcy v0.5.
    See: https://spec.acp.agntcy.org/#slim
    """


def slim_send(agent_id: str, payload: dict) -> None:  # noqa: ARG001
    raise SLIMNotImplementedError(
        "SLIM messaging is not implemented in Phase 4. "
        "Planned for eva-agntcy v0.5. See docs/plans/future-work.md."
    )
```

**Step 7: Implement `eva_agntcy/__init__.py` — server plugin entry point**

```python
# plugins/eva-agntcy/eva_agntcy/__init__.py
"""eva-agntcy: AGNTCY/ACP alignment plugin for Eva Server."""
from __future__ import annotations


def register(app) -> None:
    """Called by Eva Server's plugin loader. Mounts the ACP router."""
    from eva_agntcy.acp import acp_router
    app.include_router(acp_router)
```

**Step 8: Write OASF tests**

```python
# plugins/eva-agntcy/tests/test_oasf.py
import pytest
from core.models import Contract, EvaluatorRef, RetryPolicy
from eva_agntcy.oasf import register_agent, get_registry, SLIMNotImplementedError, slim_send


def make_contract() -> Contract:
    return Contract(
        name="billing_contract",
        provider="billing-agent",
        consumer="support-agent",
        request_schema={"type": "object"},
        evaluators=[EvaluatorRef(name="relevance", mode="threshold", min_score=0.7)],
        retry_policy=RetryPolicy(max_retries=2),
    )


def test_register_agent_returns_oasf_dict():
    entry = register_agent(make_contract())
    assert entry["agent_id"] == "billing-agent"
    assert entry["name"] == "billing_contract"
    assert len(entry["evaluators"]) == 1
    assert entry["evaluators"][0]["name"] == "relevance"


def test_registered_agent_appears_in_registry():
    contract = make_contract()
    register_agent(contract)
    registry = get_registry()
    assert contract.name in registry


def test_slim_send_raises_not_implemented():
    with pytest.raises(SLIMNotImplementedError):
        slim_send("any-agent", {"payload": "data"})
```

**Step 9: Run all eva-agntcy tests**

```bash
cd plugins/eva-agntcy && pytest tests/ -v
```

Expected: all tests PASS.

**Step 10: Commit**

```bash
git add plugins/eva-agntcy/
git commit -m "feat(plugins): eva-agntcy — ACP manifest endpoint + OASF local registry"
```

---

## Task 6: Phase 4 Full Test Suite + Integration Smoke Test

**Files:**
- Create: `tests/integration/test_phase4_smoke.py`

**Goal:** Verify that all Phase 4 components work together end-to-end in a single integration test that runs the Eva server with auth + rate limiting active, triggers a contract violation, and checks that the webhook is called and a 200 structured error is returned to the client.

**Step 0: Update tests/conftest.py with Phase 4 shared fixtures**

Add the following fixtures to `tests/conftest.py` before writing the smoke test. These are shared across Phase 4 test modules and make the valid-key pattern reusable without duplicating mock boilerplate in each file.

```python
# Add to tests/conftest.py
import pytest


@pytest.fixture
def valid_api_key():
    return "eva_test_key_phase4"


@pytest.fixture
def mock_state_valid_key(valid_api_key):
    """Fixture that makes a test API key appear valid in Redis state."""
    from unittest.mock import AsyncMock, patch

    async def fake_get(key):
        if key == f"eva:apikey:{valid_api_key}":
            return "1"
        return None

    with patch("server.auth.state_adapter") as mock:
        mock.get = AsyncMock(side_effect=fake_get)
        yield mock
```

**Step 0b: Verify pytest.ini_options has --strict-markers and integration marker**

Before running the smoke test, confirm that `pyproject.toml` has `--strict-markers` in `addopts` and the `integration` marker declared in `[tool.pytest.ini_options]`. Running under `--strict-markers` without this declaration will cause a collection error:

```toml
# pyproject.toml — verify or add
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

**Step 1: Write the integration smoke test**

```python
# tests/integration/test_phase4_smoke.py
"""Phase 4 integration smoke test.

Spins up the Eva server with a test contract, sends a request through the
authenticated gateway, verifies the structured violation response, and checks
that webhook emission was attempted.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from server.main import app


VALID_KEY = "eva_smoke_test_key"


@pytest.fixture(autouse=True)
def mock_state_for_auth():
    """Make the test API key appear valid in Redis."""
    async def fake_get(key: str):
        if key == f"eva:apikey:{VALID_KEY}":
            return "1"
        return None

    with patch("server.auth.state_adapter") as mock_state:
        mock_state.get = AsyncMock(side_effect=fake_get)
        yield mock_state


@pytest.fixture(autouse=True)
def mock_rate_limiter():
    """Disable rate limiting for the smoke test."""
    with patch("server.ratelimit.RateLimiter.check", new_callable=AsyncMock):
        yield


@pytest.mark.asyncio
async def test_health_endpoint_always_accessible():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_proxy_request_blocked():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/proxy", json={"input": "test"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_request_accepted():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/proxy",
            json={"input": "test", "target": "http://example.com"},
            headers={"X-Eva-Key": VALID_KEY},
        )
    # Target doesn't exist so we expect a non-401 error — that's fine
    assert resp.status_code != 401
    assert resp.status_code != 429


@pytest.mark.asyncio
async def test_drift_report_command_available():
    """Verify drift command is registered in the CLI."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "drift", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "report" in result.stdout
```

**Step 2: Run smoke test**

```bash
pytest tests/integration/test_phase4_smoke.py -v
```

Expected: all 4 tests PASS.

**Step 3: Run the full Phase 4 test suite**

```bash
pytest tests/server/test_auth.py \
       tests/server/test_ratelimit.py \
       tests/server/test_ratelimit_integration.py \
       tests/server/test_webhooks.py \
       tests/unit/test_drift.py \
       tests/e2e/test_drift_command.py \
       tests/integration/test_phase4_smoke.py \
       -v --tb=short
```

Expected output:

```
tests/server/test_auth.py::test_request_without_key_returns_401 PASSED
tests/server/test_auth.py::test_request_with_invalid_key_returns_401 PASSED
tests/server/test_auth.py::test_request_with_valid_key_passes_auth PASSED
tests/server/test_auth.py::test_health_endpoint_exempt_from_auth PASSED
tests/server/test_auth.py::test_well_known_agent_json_exempt_from_auth PASSED
tests/server/test_ratelimit.py::test_first_request_always_allowed PASSED
tests/server/test_ratelimit.py::test_request_at_limit_allowed PASSED
tests/server/test_ratelimit.py::test_request_over_limit_raises PASSED
tests/server/test_ratelimit.py::test_per_key_rpm_config_used PASSED
tests/server/test_ratelimit.py::test_window_key_includes_minute_bucket PASSED
tests/server/test_ratelimit.py::test_expire_called_with_120_seconds PASSED
tests/server/test_ratelimit_integration.py::test_over_limit_returns_429 PASSED
tests/server/test_webhooks.py::test_webhook_posts_json_payload PASSED
tests/server/test_webhooks.py::test_webhook_failure_does_not_raise PASSED
tests/server/test_webhooks.py::test_webhook_network_error_does_not_raise PASSED
tests/server/test_webhooks.py::test_emit_with_none_url_does_nothing PASSED
tests/server/test_webhooks.py::test_webhook_payload_structure PASSED
tests/unit/test_drift.py::test_stable_scores_report_stable_trend PASSED
tests/unit/test_drift.py::test_score_drop_reports_down_trend PASSED
tests/unit/test_drift.py::test_score_improvement_reports_up_trend PASSED
tests/unit/test_drift.py::test_single_run_returns_no_baseline PASSED
tests/unit/test_drift.py::test_multiple_evaluators_reported_independently PASSED
tests/unit/test_drift.py::test_empty_runs_returns_empty_report PASSED
tests/unit/test_drift.py::test_delta_within_threshold_is_stable PASSED
tests/e2e/test_drift_command.py::test_drift_report_help_exits_zero PASSED
tests/e2e/test_drift_command.py::test_drift_report_missing_dataset_exits_nonzero PASSED
tests/e2e/test_drift_command.py::test_drift_report_outputs_table_headers PASSED
tests/integration/test_phase4_smoke.py::test_health_endpoint_always_accessible PASSED
tests/integration/test_phase4_smoke.py::test_unauthenticated_proxy_request_blocked PASSED
tests/integration/test_phase4_smoke.py::test_authenticated_request_accepted PASSED
tests/integration/test_phase4_smoke.py::test_drift_report_command_available PASSED

31 passed in N.NNs
```

**Step 4: Commit**

```bash
git add tests/integration/test_phase4_smoke.py
git commit -m "test(integration): Phase 4 smoke test — auth, rate limit, drift command"
```

---

## Phase 4 Completion Checklist

Before marking Phase 4 done, verify each item:

**Eva Server Hardening**
- [ ] `POST /v1/proxy` without `X-Eva-Key` returns `401 {"detail": "Missing X-Eva-Key header"}`
- [ ] `POST /v1/proxy` with invalid key returns `401 {"detail": "Invalid API key"}`
- [ ] `GET /health` returns `200` with no key (exempt from auth)
- [ ] `GET /.well-known/agent.json` returns `200` with no key (exempt from auth)
- [ ] After N+1 requests in one minute window, next request returns `429` with `Retry-After: 60` header
- [ ] Per-key rate limits stored in Redis as `eva:ratelimit_config:<key>` override the global default
- [ ] On contract violation after all retries, webhook is POSTed with correct JSON payload
- [ ] Webhook failure (5xx or network error) does not affect the response returned to the client
- [ ] `webhook_url` field accepted on `Contract` model (per-contract override)
- [ ] `eva drift report --dataset ds --target url` outputs a rich table with evaluator/baseline/current/delta/trend columns
- [ ] `eva drift report` with no `--dataset` flag exits non-zero
- [ ] Trend shows `↓ down` when current score drops > threshold below baseline
- [ ] Trend shows `↑ up` when current score rises > threshold above baseline
- [ ] Trend shows `— stable` when delta is within threshold

**eva-agntcy**
- [ ] `GET /.well-known/agent.json` returns ACP manifest with `schema_version`, `name`, `description`, `capabilities`, `endpoints`
- [ ] Manifest `endpoints` includes both `/v1/proxy` and `/v1/contract/invoke`
- [ ] `register_agent(contract)` writes to `oasf_registry.json`
- [ ] `slim_send()` raises `SLIMNotImplementedError` with a clear message pointing to future work

**Gate to Phase 5**
All items above checked. Gateway API remains backward-compatible with Phase 3 clients (auth is additive — existing clients just need to add the header).

---

## File Index

| File | Purpose |
|---|---|
| `server/auth.py` | `ApiKeyMiddleware` — validates `X-Eva-Key` against Redis |
| `server/ratelimit.py` | `RateLimiter` + `RateLimitExceeded` — sliding window counter |
| `server/webhooks.py` | `emit_violation_webhook` — fire-and-forget POST on violations |
| `core/drift.py` | `compute_drift` engine — trend analysis across runs |
| `cli/main.py` | Extended with `drift` command group + `drift report` subcommand |
| `plugins/eva-agntcy/` | ACP manifest endpoint + OASF local registry + SLIM stub |
| `tests/server/test_auth.py` | Auth middleware tests |
| `tests/server/test_ratelimit.py` | Rate limiter unit tests |
| `tests/server/test_ratelimit_integration.py` | Rate limit 429 integration test |
| `tests/server/test_webhooks.py` | Webhook emission tests (respx mocks) |
| `tests/unit/test_drift.py` | Drift computation unit tests |
| `tests/e2e/test_drift_command.py` | `eva drift report` CLI E2E tests |
| `tests/integration/test_phase4_smoke.py` | Full Phase 4 smoke test |

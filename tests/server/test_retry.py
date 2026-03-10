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

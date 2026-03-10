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

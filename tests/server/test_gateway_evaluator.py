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

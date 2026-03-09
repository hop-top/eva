# tests/unit/test_models.py
from datetime import datetime
from core.models import Score, Result, Contract, RetryPolicy, Run, EvaluatorRef

def test_score_value_range():
    s = Score(value=0.5)
    assert 0.0 <= s.value <= 1.0

def test_score_defaults():
    s = Score(value=1.0)
    assert s.reason is None
    assert s.metadata == {}

def test_result_binary_pass():
    r = Result(
        test_id="t1", evaluator="contains", score=Score(value=1.0),
        mode="binary", duration_ms=10, trace_id=None
    )
    assert r.passed is True

def test_result_binary_fail():
    r = Result(
        test_id="t1", evaluator="contains", score=Score(value=0.0),
        mode="binary", duration_ms=10, trace_id=None
    )
    assert r.passed is False

def test_result_threshold_pass():
    r = Result(
        test_id="t1", evaluator="quality", score=Score(value=0.8),
        mode="threshold", min_score=0.7, duration_ms=10, trace_id=None
    )
    assert r.passed is True

def test_result_threshold_fail():
    r = Result(
        test_id="t1", evaluator="quality", score=Score(value=0.5),
        mode="threshold", min_score=0.7, duration_ms=10, trace_id=None
    )
    assert r.passed is False

def test_result_warn_always_passes():
    r = Result(
        test_id="t1", evaluator="tone", score=Score(value=0.0),
        mode="warn", duration_ms=10, trace_id=None
    )
    assert r.passed is True

def test_retry_policy_defaults():
    rp = RetryPolicy()
    assert rp.max_retries == 2
    assert rp.hint is None
    assert rp.backoff_ms == 0

def test_contract_minimal():
    c = Contract(
        name="refund_policy",
        provider="billing-agent",
        request_schema={"type": "object"},
        evaluators=[],
        retry_policy=RetryPolicy()
    )
    assert c.consumer is None

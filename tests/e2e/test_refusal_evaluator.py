# tests/e2e/test_refusal_evaluator.py
"""E2E: refusal evaluator (US-041, T-0294).

One test per acceptance bullet on docs/stories/US-041-refusal-evaluator.md.
"""
from __future__ import annotations

import pytest

from core.evaluators.refusal import RefusalEvaluator
from core.models import Score


# ---------------------------------------------------------------------------
# forbid mode (default)
# ---------------------------------------------------------------------------

def test_forbid_mode_refusal_fails():
    ev = RefusalEvaluator()  # default mode="forbid"
    score = ev.run("I'm sorry, but I cannot help with that.")
    assert isinstance(score, Score)
    assert score.value == 0.0
    assert score.reason is not None
    assert "refusal" in score.reason.lower()


def test_forbid_mode_substantive_response_passes():
    ev = RefusalEvaluator()
    score = ev.run("Sure — here are three options for you to consider.")
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# require mode
# ---------------------------------------------------------------------------

def test_require_mode_refusal_passes():
    ev = RefusalEvaluator(mode="require")
    score = ev.run("I cannot help with that.")
    assert score.value == 1.0


def test_require_mode_non_refusal_fails():
    ev = RefusalEvaluator(mode="require")
    score = ev.run("Sure, here is the answer.")
    assert score.value == 0.0
    assert score.reason == "expected a refusal but response is substantive"


# ---------------------------------------------------------------------------
# soft preamble + substantive answer → NOT a refusal
# ---------------------------------------------------------------------------

def test_soft_preamble_with_code_fence_is_not_a_refusal():
    """Marker phrase + code fence: code-fence substantive marker wins."""
    ev = RefusalEvaluator()
    response = (
        "I'm sorry I missed that earlier. Here is the answer:\n"
        "```python\n"
        "def foo():\n"
        "    return 42\n"
        "```\n"
    )
    score = ev.run(response)
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# long substantive body NOT a refusal
# ---------------------------------------------------------------------------

def test_long_substantive_body_not_a_refusal():
    """≥120 words: substantive-completion length guard overrides marker."""
    body = (
        "I cannot stress this enough — the architecture matters. "
        + ("Detail. " * 130)
    )
    ev = RefusalEvaluator()
    score = ev.run(body)
    assert score.value == 1.0


# ---------------------------------------------------------------------------
# empty input
# ---------------------------------------------------------------------------

def test_empty_response_forbid_mode_passes():
    """Empty response in forbid mode: nothing to forbid → pass."""
    ev = RefusalEvaluator()
    score = ev.run("")
    assert score.value == 1.0


def test_empty_response_require_mode_fails():
    """Empty response in require mode: no refusal detected → fail."""
    ev = RefusalEvaluator(mode="require")
    score = ev.run("")
    assert score.value == 0.0


# ---------------------------------------------------------------------------
# config validation
# ---------------------------------------------------------------------------

def test_unsupported_mode_raises():
    with pytest.raises(ValueError):
        RefusalEvaluator(mode="warn")

# tests/e2e/test_code_test_passes_evaluator.py
"""E2E tests: code_test_passes evaluator (T-0317, US-044).

One test case per acceptance bullet in docs/stories/US-044-code-test-passes-evaluator.md.
"""
from __future__ import annotations

import pytest

from core.evaluators.code_test_passes import CodeTestPassesEvaluator
from core.models import Score


# AC1: extracts first python fenced block.
def test_extracts_first_python_block():
    response = (
        "Some intro.\n\n```python\ndef add(a, b):\n    return a + b\n```\n"
        "Some outro.\n"
    )
    ev = CodeTestPassesEvaluator(test_code="assert add(1, 2) == 3")
    score = ev.run(response)
    assert isinstance(score, Score)
    assert score.value == 1.0


# AC2: combined program exits 0 -> pass.
def test_passes_when_test_assertion_holds():
    response = "```python\nx = 42\n```\n"
    ev = CodeTestPassesEvaluator(test_code="assert x == 42")
    score = ev.run(response)
    assert score.value == 1.0


# AC3: non-zero exit -> fail with stderr snippet.
def test_fails_when_assertion_fails():
    response = "```python\nx = 1\n```\n"
    ev = CodeTestPassesEvaluator(test_code="assert x == 2, 'oops not two'")
    score = ev.run(response)
    assert score.value == 0.0
    assert "exit code" in (score.reason or "")


# AC4: timeout -> fail with "execution timeout" reason.
def test_fails_on_timeout():
    response = "```python\nimport time\ntime.sleep(30)\n```\n"
    ev = CodeTestPassesEvaluator(test_code="", timeout=1)
    score = ev.run(response)
    assert score.value == 0.0
    assert "timeout" in (score.reason or "")


# AC5: no python block -> fail.
def test_fails_when_no_python_block():
    response = "No code here. Or ```js\nconsole.log(1)\n``` only js."
    ev = CodeTestPassesEvaluator(test_code="pass")
    score = ev.run(response)
    assert score.value == 0.0
    assert "no python code block" in (score.reason or "")


# AC6: never invokes a shell — args always a list.
def test_never_uses_shell(monkeypatch):
    import subprocess
    seen: list = []
    orig_run = subprocess.run

    def wrapped_run(args, *a, **kw):
        seen.append((args, kw.get("shell")))
        return orig_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", wrapped_run)
    response = "```python\nprint('ok')\n```\n"
    ev = CodeTestPassesEvaluator(test_code="")
    ev.run(response)
    assert seen, "subprocess.run was never called"
    args, shell = seen[0]
    assert isinstance(args, list)
    assert shell is False


# AC7: default timeout is 10; timeout=None raises ValueError.
def test_default_timeout_is_ten_and_none_raises():
    ev = CodeTestPassesEvaluator(test_code="")
    assert ev.timeout == 10
    with pytest.raises(ValueError):
        CodeTestPassesEvaluator(test_code="", timeout=None)


# AC8: captures stdout/stderr without raising — always returns a Score.
def test_returns_score_even_on_runtime_error():
    response = "```python\nraise RuntimeError('bang')\n```\n"
    ev = CodeTestPassesEvaluator(test_code="")
    score = ev.run(response)
    assert isinstance(score, Score)
    assert score.value == 0.0
    assert "bang" in (score.reason or "") or "exit code" in (score.reason or "")

# tests/e2e/test_code_block_runs_evaluator.py
"""E2E tests: code_block_runs evaluator (T-0315, US-043).

One test case per acceptance bullet in docs/stories/US-043-code-block-runs-evaluator.md.
"""
from __future__ import annotations

import shutil
import pytest

from core.evaluators.code_block_runs import CodeBlockRunsEvaluator
from core.models import Score


# AC1: extracts all fenced blocks; untagged blocks are "unsupported".
def test_untagged_block_is_unsupported_skip_default():
    ev = CodeBlockRunsEvaluator()  # unsupported_action="skip"
    score = ev.run("Here is code:\n\n```\nfoo bar baz\n```\n")
    # skip mode = pass when no supported errors found.
    assert isinstance(score, Score)
    assert score.value == 1.0


# AC2: zero blocks + require_code_block=False -> pass.
def test_passes_on_zero_blocks_default():
    ev = CodeBlockRunsEvaluator()
    score = ev.run("Just prose, no code at all.")
    assert score.value == 1.0


# AC3: every supported block parses -> pass.
def test_passes_when_all_supported_blocks_parse():
    body = (
        "```python\nx = 1\nprint(x)\n```\n\n"
        "```json\n{\"a\": 1}\n```\n\n"
        "```yaml\nkey: value\n```\n"
    )
    ev = CodeBlockRunsEvaluator()
    score = ev.run(body)
    assert score.value == 1.0


# AC4: python SyntaxError -> fail naming language and message.
def test_fails_on_python_syntax_error():
    body = "```python\ndef broken(:\n    pass\n```\n"
    ev = CodeBlockRunsEvaluator()
    score = ev.run(body)
    assert score.value == 0.0
    assert "python" in (score.reason or "")


# AC5: malformed json -> fail.
def test_fails_on_malformed_json():
    body = "```json\n{not json}\n```\n"
    ev = CodeBlockRunsEvaluator()
    score = ev.run(body)
    assert score.value == 0.0
    assert "json" in (score.reason or "")


# AC6: bash -n failure -> fail (skipped on hosts without bash).
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
def test_fails_on_bash_syntax_error():
    body = "```bash\nif then fi\n```\n"
    ev = CodeBlockRunsEvaluator()
    score = ev.run(body)
    assert score.value == 0.0
    assert "bash" in (score.reason or "")


# AC7: unsupported_action="fail" -> any unsupported lang fails.
def test_unsupported_action_fail_rejects_unknown_lang():
    body = "```ruby\nputs 'hi'\n```\n"
    ev = CodeBlockRunsEvaluator(unsupported_action="fail")
    score = ev.run(body)
    assert score.value == 0.0
    assert "ruby" in (score.reason or "")


# AC8: require_code_block=True and zero blocks -> fail.
def test_require_code_block_fails_on_empty():
    ev = CodeBlockRunsEvaluator(require_code_block=True)
    score = ev.run("Just prose.")
    assert score.value == 0.0
    assert "no fenced code blocks" in (score.reason or "")

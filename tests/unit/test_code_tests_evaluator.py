"""code_tests: executes generated code against per-case tests (python -I, temp dir)."""
import os
import time

import pytest

from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.code_tests import (
    CODE_LANGUAGES,
    CodeTestsEvaluator,
    extract_last_block,
)

PY = CODE_LANGUAGES["python"]


def fence(code, lang="python"):
    return f"```{lang}\n{code}\n```"


def run(resp, tests="assert add(1, 2) == 3", **kw):
    return CodeTestsEvaluator(**kw).run_case(resp, {"tests": tests})


def test_pass():
    s = run("here:\n" + fence("def add(a, b):\n    return a + b"))
    assert s.value == 1.0


def test_fail_assertion_reports_reason():
    s = run(fence("def add(a, b):\n    return a - b"))
    assert s.value == 0.0
    assert "exit code 1" in s.reason and "AssertionError" in s.reason


def test_syntax_error_fails():
    s = run(fence("def add(a, b) return a"))
    assert s.value == 0.0 and "SyntaxError" in s.reason


def test_no_code_block():
    s = run("just prose")
    assert s.value == 0.0 and "no python code block" in s.reason


def test_uses_last_block():
    resp = fence("def add(a, b):\n    return 0") + "\nfixed:\n" + fence("def add(a, b):\n    return a + b")
    assert run(resp).value == 1.0


def test_tagged_block_beats_later_other_language():
    resp = fence("def add(a, b):\n    return a + b") + "\n" + fence("echo hi", "bash")
    assert run(resp).value == 1.0


def test_untagged_block_fallback():
    assert run(fence("def add(a, b):\n    return a + b", "")).value == 1.0


def test_other_language_only_is_not_python():
    assert run(fence("def add(a, b):\n    return a + b", "javascript")).value == 0.0


def test_tests_list_joined():
    s = CodeTestsEvaluator().run_case(
        fence("def add(a, b):\n    return a + b"),
        {"tests": ["assert add(1, 2) == 3", "assert add(0, 0) == 0"]},
    )
    assert s.value == 1.0


def test_case_without_tests_is_not_applicable():
    assert CodeTestsEvaluator().run_case(fence("x = 1"), {}) is None
    assert CodeTestsEvaluator().run(fence("x = 1")).value == 0.0  # direct use: explicit fail


def test_shared_test_code_config_appended():
    s = CodeTestsEvaluator(test_code="assert add(2, 2) == 4").run_case(
        fence("def add(a, b):\n    return a + b"), {"tests": "assert add(1, 1) == 2"}
    )
    assert s.value == 1.0
    s = CodeTestsEvaluator(test_code="assert add(2, 2) == 5").run_case(
        fence("def add(a, b):\n    return a + b"), {"tests": "assert add(1, 1) == 2"}
    )
    assert s.value == 0.0


def test_timeout_kills_infinite_loop():
    t0 = time.time()
    s = run(fence("while True:\n    pass"), tests="pass", timeout=1)
    assert s.value == 0.0 and "timeout after 1" in s.reason
    assert time.time() - t0 < 8


def test_stdin_closed():
    s = run(fence("x = input()"), tests="pass")
    assert s.value == 0.0 and "EOFError" in s.reason


def test_env_has_no_inherited_secrets(monkeypatch):
    monkeypatch.setenv("EVA_TEST_SECRET", "hunter2")
    code = "import os\nassert 'EVA_TEST_SECRET' not in os.environ"
    assert run(fence(code), tests="pass").value == 1.0


def test_runs_isolated_in_temp_dir_and_cleans_up(tmp_path):
    code = "import os, sys\nprint(os.getcwd())\nassert sys.flags.isolated == 1\nopen('leak.txt','w').write('x')"
    cwd = os.getcwd()
    assert run(fence(code), tests="pass").value == 1.0
    assert not os.path.exists(os.path.join(cwd, "leak.txt"))


def test_cwd_not_importable(tmp_path, monkeypatch):
    # -I: cwd/script dir not on sys.path -> sibling modules are not importable
    code = "import sys\nassert '' not in sys.path"
    assert run(fence(code), tests="pass").value == 1.0


def test_reasoning_block_ignored():
    resp = "<think>```python\nassert False\n```</think>\n" + fence("def add(a, b):\n    return a + b")
    assert run(resp).value == 1.0


def test_unsupported_language_rejected():
    with pytest.raises(ValueError, match="unsupported language"):
        CodeTestsEvaluator(language="cobol")


def test_timeout_none_rejected():
    with pytest.raises(ValueError):
        CodeTestsEvaluator(timeout=None)


def test_extract_last_block_prefers_tagged():
    t = "```\nuntagged\n```\n```python\ntagged\n```\n```\nlater untagged\n```"
    assert extract_last_block(t, PY).strip() == "tagged"


def test_factory_registered():
    ev = BUILTIN_EVALUATOR_FACTORIES["code_tests"]({"timeout": 3}, None)
    assert ev.timeout == 3

"""code_tests stdin/stdout mode: run the program once per {stdin, expected_stdout}."""
import pytest

from core.dataset import EvaTestCase
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.code_tests import CodeTestsEvaluator


def fence(code):
    return f"```python\n{code}\n```"


def run(code, stdio, **kw):
    kw.setdefault("timeout", 30)  # generous: shared, loaded CI hosts
    return CodeTestsEvaluator(**kw).run_case(fence(code), {"stdio": stdio})


def pair(stdin, out):
    return {"stdin": stdin, "expected_stdout": out}


ADD = "a, b = map(int, input().split())\nprint(a + b)"


def test_pass_all_pairs():
    s = run(ADD, [pair("1 2\n", "3\n"), pair("10 5\n", "15\n")])
    assert s.value == 1.0 and "2/2" in s.reason


def test_wrong_output_fails_with_counts():
    s = run(ADD, [pair("1 2\n", "3\n"), pair("1 1\n", "3\n"), pair("4 4\n", "8\n")])
    assert s.value == 0.0
    assert "passed 2/3" in s.reason
    assert "test 2" in s.reason and "wrong output" in s.reason
    assert "expected '3'" in s.reason and "got '2'" in s.reason


def test_timeout_per_pair():
    code = "import time\nif input() == 'slow':\n    time.sleep(60)\nprint('ok')"
    s = run(code, [pair("fast\n", "ok\n"), pair("slow\n", "ok\n")], timeout=2)
    assert s.value == 0.0
    assert "passed 1/2" in s.reason and "timeout after 2" in s.reason


def test_runtime_error_reports_stderr():
    s = run("raise ValueError('boom')", [pair("", "x\n")])
    assert s.value == 0.0
    assert "passed 0/1" in s.reason and "runtime error" in s.reason and "ValueError" in s.reason


def test_reads_all_of_stdin():
    code = "import sys\ndata = sys.stdin.read().split()\nprint(sum(map(int, data)))"
    s = run(code, [pair("1 2 3\n4 5\n6\n", "21\n")])
    assert s.value == 1.0


def test_line_by_line_stdin_until_eof():
    code = "import sys\nfor line in sys.stdin:\n    print(line.strip()[::-1])"
    s = run(code, [pair("abc\nxyz\n", "cba\nzyx\n")])
    assert s.value == 1.0


def test_empty_stdin_is_eof_not_hang():
    s = run("import sys\nprint(len(sys.stdin.read()))", [pair("", "0\n")])
    assert s.value == 1.0


def test_trailing_whitespace_normalised_both_sides():
    code = "print('a  ')\nprint('b\\t')\nprint()\nprint()"
    assert run(code, [pair("", "a\nb")]).value == 1.0
    assert run("print('a')", [pair("", "a  \n\n\n")]).value == 1.0
    assert run("import sys\nsys.stdout.write('a\\r\\nb\\r\\n')", [pair("", "a\nb\n")]).value == 1.0


def test_leading_and_inner_whitespace_significant():
    assert run("print(' a')", [pair("", "a\n")]).value == 0.0
    assert run("print('a  b')", [pair("", "a b\n")]).value == 0.0
    assert run("print('a')\nprint()\nprint('b')", [pair("", "a\nb\n")]).value == 0.0


def test_all_or_nothing_default_not_partial():
    s = run(ADD, [pair("1 2\n", "3\n"), pair("1 1\n", "99\n")])
    assert s.value == 0.0


def test_partial_config_scores_fraction():
    s = run(ADD, [pair("1 2\n", "3\n"), pair("1 1\n", "99\n")], partial=True)
    assert s.value == pytest.approx(0.5) and "passed 1/2" in s.reason


def test_no_code_block():
    s = CodeTestsEvaluator().run_case("prose", {"stdio": [pair("", "x")]})
    assert s.value == 0.0 and "no python code block" in s.reason


def test_uses_last_block():
    resp = fence("print('old')") + "\n" + fence("print('new')")
    s = CodeTestsEvaluator().run_case(resp, {"stdio": [pair("", "new\n")]})
    assert s.value == 1.0


def test_empty_stdio_list_not_applicable():
    assert CodeTestsEvaluator().run_case(fence("x=1"), {"stdio": []}) is None
    assert CodeTestsEvaluator().run_case(fence("x=1"), {"stdio": None}) is None


def test_tests_and_stdio_together_is_a_clear_failure():
    s = CodeTestsEvaluator().run_case(
        fence("print(1)"), {"tests": "assert True", "stdio": [pair("", "1\n")]}
    )
    assert s.value == 0.0 and "both" in s.reason


def test_malformed_pair_is_a_clear_failure():
    s = CodeTestsEvaluator().run_case(fence("print(1)"), {"stdio": [{"stdin": "x"}]})
    assert s.value == 0.0 and "expected_stdout" in s.reason


def test_each_pair_gets_fresh_workdir():
    code = (
        "import os\n"
        "print(os.path.exists('state.txt'))\n"
        "open('state.txt', 'w').write('x')"
    )
    assert run(code, [pair("", "False\n"), pair("", "False\n")]).value == 1.0


def test_secret_env_not_visible_in_stdio_mode(monkeypatch):
    monkeypatch.setenv("EVA_TEST_SECRET", "fake-secret-value")
    code = "import os\nprint(os.environ.get('EVA_TEST_SECRET', 'absent'))"
    assert run(code, [pair("", "absent\n")]).value == 1.0


def test_assert_mode_unchanged():
    s = CodeTestsEvaluator().run_case(
        fence("def add(a, b):\n    return a + b"), {"tests": "assert add(1, 2) == 3"}
    )
    assert s.value == 1.0 and s.reason is None


def test_dataset_case_accepts_stdio_field():
    c = EvaTestCase(id="x", input="p", stdio=[{"stdin": "1\n", "expected_stdout": "2\n"}])
    assert c.model_dump()["stdio"] == [{"stdin": "1\n", "expected_stdout": "2\n"}]
    assert EvaTestCase(id="y", input="p").stdio is None


def test_factory_passes_partial():
    ev = BUILTIN_EVALUATOR_FACTORIES["code_tests"]({"partial": True}, None)
    assert ev.partial is True

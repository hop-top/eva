import pytest

from core.evaluators.answer_match import (
    ExactMatchEvaluator,
    FinalAnswerEvaluator,
    extract_final_answer,
    normalize_answer,
)
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES


def fa(resp, expected="6"):
    return FinalAnswerEvaluator().run_case(resp, {"expected_output": expected})


def em(resp, expected="6"):
    return ExactMatchEvaluator().run_case(resp, {"expected_output": expected})


def test_final_answer_basic():
    assert fa("3+5-2 = 6\nFinal answer: 6").value == 1.0


def test_final_answer_uses_last_line():
    assert fa("Final answer: 5\nwait, recheck\nFinal answer: 6").value == 1.0
    assert fa("Final answer: 6\nhmm\nFinal answer: 5").value == 0.0


@pytest.mark.parametrize("line", [
    "Final answer: 6", "final answer: 6.", "**Final answer:** 6", "Final Answer: **6**",
    "> Final answer: $6", "Final answer: \\boxed{6}", "Final answer: 6.0", "Final answer: `6`",
])
def test_final_answer_normalization(line):
    assert fa("work\n" + line).value == 1.0


def test_final_answer_thousands_separator():
    assert fa("Final answer: 1,234", "1234").value == 1.0


def test_final_answer_text_casefold():
    assert fa("Final answer: Paris", "paris").value == 1.0


def test_final_answer_wrong():
    s = fa("Final answer: 7")
    assert s.value == 0.0 and "expected '6'" in s.reason and "'7'" in s.reason


def test_final_answer_missing_line():
    s = fa("the result is 6")
    assert s.value == 0.0 and "Final answer" in s.reason


def test_final_answer_ignores_reasoning_block():
    assert fa("<think>Final answer: 5</think>\nFinal answer: 6").value == 1.0


def test_no_expected_output_is_not_applicable():
    assert FinalAnswerEvaluator().run_case("Final answer: 6", {}) is None
    assert ExactMatchEvaluator().run("6").value == 0.0


def test_expected_config_fallback():
    assert FinalAnswerEvaluator(expected="6").run_case("Final answer: 6", {}).value == 1.0


def test_exact_match_whole_response():
    assert em("6").value == 1.0
    assert em("  6.\n").value == 1.0
    assert em("The answer is 6").value == 0.0


def test_exact_match_strips_reasoning():
    assert em("<think>blah</think>6").value == 1.0


def test_exact_match_registered_for_ben_sample():
    # ben suites/testdata/gsm8k-sample.yaml: `- name: exact_match` + expected_output
    ev = BUILTIN_EVALUATOR_FACTORIES["exact_match"]({"name": "exact_match", "mode": "binary"}, None)
    assert ev.run_case("6", {"expected_output": "6"}).value == 1.0


def test_extract_and_normalize_helpers():
    assert extract_final_answer("a\nFinal answer: x\n") == "x"
    assert extract_final_answer("nothing") is None
    assert normalize_answer(" **\\boxed{1,000}.** ") == "1000"

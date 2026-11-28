"""tool_call_match: logged tool calls vs the case's expected calls."""
import asyncio

import pytest

from core.events import ToolCallEvent
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.tool_call_match import ToolCallMatchEvaluator


def ev(name, args=None, raw=None, idx=0):
    return ToolCallEvent(
        tool_name=name, args=args or {}, step_index=idx, raw_args=raw
    )


def log(*calls):
    return [ev(n, a, idx=i) for i, (n, a) in enumerate(calls)]


def check(events, expected, **cfg):
    return ToolCallMatchEvaluator(**cfg).check(events, expected)


WEATHER = [{"get_weather": {"city": ["Paris", "paris"], "unit": ["celsius", ""]}}]


# --- single ---------------------------------------------------------------

def test_single_passes_with_listed_value_and_omitted_optional():
    s = check(log(("get_weather", {"city": "paris"})), WEATHER)
    assert s.value == 1.0, s.reason


def test_single_passes_with_optional_given():
    assert check(log(("get_weather", {"city": "Paris", "unit": "celsius"})), WEATHER).value == 1.0


def test_single_wrong_tool():
    s = check(log(("get_time", {"city": "Paris"})), WEATHER)
    assert s.value == 0.0
    assert "get_time" in s.reason and "get_weather" in s.reason


def test_single_missing_required_argument():
    s = check(log(("get_weather", {"unit": "celsius"})), WEATHER)
    assert s.value == 0.0
    assert "missing" in s.reason and "city" in s.reason


def test_single_value_outside_accepted_list():
    s = check(log(("get_weather", {"city": "Lyon"})), WEATHER)
    assert s.value == 0.0
    assert "city" in s.reason and "Lyon" in s.reason and "Paris" in s.reason


def test_single_unexpected_argument():
    s = check(log(("get_weather", {"city": "Paris", "days": 3})), WEATHER)
    assert s.value == 0.0
    assert "days" in s.reason


def test_single_extra_call_fails():
    s = check(
        log(("get_weather", {"city": "Paris"}), ("get_weather", {"city": "Paris"})),
        WEATHER,
    )
    assert s.value == 0.0
    assert "extra" in s.reason


def test_single_no_call_logged():
    s = check([], WEATHER)
    assert s.value == 0.0
    assert "get_weather" in s.reason and "no tool call" in s.reason


def test_first_mismatch_reported_before_extra_call():
    s = check(log(("get_weather", {"city": "Lyon"}), ("x", {})), WEATHER)
    assert "Lyon" in s.reason


def test_single_accepts_bare_mapping_as_one_call():
    s = check(log(("get_weather", {"city": "Paris"})), WEATHER[0])
    assert s.value == 1.0, s.reason


def test_single_with_two_expected_calls_is_a_config_error():
    s = check(log(("a", {})), [{"a": {}}, {"b": {}}])
    assert s.value == 0.0 and "exactly one" in s.reason


# --- no call expected -----------------------------------------------------

def test_none_passes_on_empty_log():
    assert check([], [], match="none").value == 1.0


def test_none_fails_when_a_call_is_emitted():
    s = check(log(("get_weather", {"city": "Paris"})), [], match="none")
    assert s.value == 0.0
    assert "no tool call" in s.reason and "get_weather" in s.reason


def test_none_rejects_non_empty_expected_calls():
    s = check([], WEATHER, match="none")
    assert s.value == 0.0 and "no call" in s.reason


# --- first ----------------------------------------------------------------

def test_first_ignores_later_calls():
    s = check(
        log(("get_weather", {"city": "Paris"}), ("other", {"z": 1})),
        WEATHER, match="first",
    )
    assert s.value == 1.0, s.reason


def test_first_checks_the_first_call_only():
    s = check(
        log(("other", {}), ("get_weather", {"city": "Paris"})),
        WEATHER, match="first",
    )
    assert s.value == 0.0 and "other" in s.reason


def test_first_fails_on_empty_log():
    assert check([], WEATHER, match="first").value == 0.0


# --- parallel (order-free) ------------------------------------------------

PAIR = [
    {"get_weather": {"city": ["Paris"]}},
    {"get_weather": {"city": ["Rome"]}},
]


def test_parallel_any_order_passes():
    s = check(
        log(("get_weather", {"city": "Rome"}), ("get_weather", {"city": "Paris"})),
        PAIR, match="parallel",
    )
    assert s.value == 1.0, s.reason


def test_parallel_uses_one_to_one_pairing_not_greedy():
    expected = [
        {"f": {"x": [1, 2]}},
        {"f": {"x": [1]}},
    ]
    s = check(log(("f", {"x": 1}), ("f", {"x": 2})), expected, match="parallel")
    assert s.value == 1.0, s.reason


def test_parallel_duplicate_call_does_not_satisfy_two_expected():
    s = check(
        log(("get_weather", {"city": "Paris"}), ("get_weather", {"city": "Paris"})),
        PAIR, match="parallel",
    )
    assert s.value == 0.0


def test_parallel_missing_call():
    s = check(log(("get_weather", {"city": "Paris"})), PAIR, match="parallel")
    assert s.value == 0.0 and "Rome" in s.reason


def test_parallel_extra_call():
    s = check(
        log(
            ("get_weather", {"city": "Paris"}),
            ("get_weather", {"city": "Rome"}),
            ("get_time", {}),
        ),
        PAIR, match="parallel",
    )
    assert s.value == 0.0 and "extra" in s.reason and "get_time" in s.reason


def test_parallel_wrong_tool():
    s = check(
        log(("get_weather", {"city": "Paris"}), ("get_time", {"city": "Rome"})),
        PAIR, match="parallel",
    )
    assert s.value == 0.0 and "get_time" in s.reason or "Rome" in s.reason


def test_parallel_wrong_value_names_the_argument():
    s = check(
        log(("get_weather", {"city": "Paris"}), ("get_weather", {"city": "Oslo"})),
        PAIR, match="parallel",
    )
    assert s.value == 0.0 and "city" in s.reason and "Oslo" in s.reason


# --- ordered --------------------------------------------------------------

def test_ordered_passes_in_order():
    s = check(
        log(("get_weather", {"city": "Paris"}), ("get_weather", {"city": "Rome"})),
        PAIR, match="ordered",
    )
    assert s.value == 1.0, s.reason


def test_ordered_fails_out_of_order():
    s = check(
        log(("get_weather", {"city": "Rome"}), ("get_weather", {"city": "Paris"})),
        PAIR, match="ordered",
    )
    assert s.value == 0.0 and "call 1" in s.reason


def test_ordered_missing_and_extra():
    one = log(("get_weather", {"city": "Paris"}))
    s = check(one, PAIR, match="ordered")
    assert s.value == 0.0 and "Rome" in s.reason
    three = log(
        ("get_weather", {"city": "Paris"}),
        ("get_weather", {"city": "Rome"}),
        ("x", {}),
    )
    s = check(three, PAIR, match="ordered")
    assert s.value == 0.0 and "extra" in s.reason


# --- value comparison -----------------------------------------------------

def test_one_equals_one_point_zero_both_ways():
    assert check(log(("f", {"n": 1.0})), [{"f": {"n": [1]}}]).value == 1.0
    assert check(log(("f", {"n": 1})), [{"f": {"n": [1.0]}}]).value == 1.0


def test_bool_is_not_a_number():
    assert check(log(("f", {"n": True})), [{"f": {"n": [1]}}]).value == 0.0
    assert check(log(("f", {"n": 1})), [{"f": {"n": [True]}}]).value == 0.0
    assert check(log(("f", {"n": True})), [{"f": {"n": [True]}}]).value == 1.0


def test_string_is_not_a_number():
    assert check(log(("f", {"n": "1"})), [{"f": {"n": [1]}}]).value == 0.0
    assert check(log(("f", {"n": 1})), [{"f": {"n": ["1"]}}]).value == 0.0


def test_strings_case_and_whitespace_sensitive_by_default():
    assert check(log(("f", {"s": "paris"})), [{"f": {"s": ["Paris"]}}]).value == 0.0
    assert check(log(("f", {"s": " Paris "})), [{"f": {"s": ["Paris"]}}]).value == 0.0


def test_case_insensitive_option():
    s = check(log(("f", {"s": "PARIS"})), [{"f": {"s": ["Paris"]}}], case_sensitive=False)
    assert s.value == 1.0


def test_whitespace_option_trims_and_collapses():
    s = check(
        log(("f", {"s": "  New   York "})), [{"f": {"s": ["New York"]}}],
        normalize_whitespace=True,
    )
    assert s.value == 1.0
    assert check(
        log(("f", {"s": "NewYork"})), [{"f": {"s": ["New York"]}}],
        normalize_whitespace=True,
    ).value == 0.0


def test_nested_values_compare_recursively_with_options():
    exp = [{"f": {"o": [{"tags": ["A", 2]}]}}]
    assert check(log(("f", {"o": {"tags": ["a", 2.0]}})), exp, case_sensitive=False).value == 1.0
    assert check(log(("f", {"o": {"tags": ["a", 2.0]}})), exp).value == 0.0
    assert check(log(("f", {"o": {"tags": ["A"]}})), exp).value == 0.0
    assert check(log(("f", {"o": {"tags": ["A", 2], "x": 1}})), exp).value == 0.0


def test_list_valued_argument_needs_list_of_alternatives():
    exp = [{"f": {"ids": [[1, 2], [2, 1]]}}]
    assert check(log(("f", {"ids": [2, 1]})), exp).value == 1.0
    assert check(log(("f", {"ids": [1]})), exp).value == 0.0


def test_scalar_accepted_value_is_one_alternative():
    assert check(log(("f", {"n": 3})), [{"f": {"n": 3}}]).value == 1.0


def test_null_value():
    assert check(log(("f", {"n": None})), [{"f": {"n": [None]}}]).value == 1.0
    assert check(log(("f", {"n": None})), [{"f": {"n": [0]}}]).value == 0.0


def test_call_without_arguments_and_expected_none():
    assert check(log(("ping", {})), [{"ping": {}}]).value == 1.0
    assert check(log(("ping", {})), [{"ping": None}]).value == 1.0


def test_empty_string_alternative_matches_empty_value_too():
    assert check(log(("f", {"u": ""})), [{"f": {"u": ["c", ""]}}]).value == 1.0


# --- malformed arguments --------------------------------------------------

def test_malformed_arguments_never_match_required_arguments():
    events = [ev("get_weather", {}, raw='{"city": ')]
    s = check(events, WEATHER)
    assert s.value == 0.0
    assert "not valid JSON" in s.reason and "get_weather" in s.reason


def test_malformed_arguments_in_parallel_mode():
    events = [
        ev("get_weather", {"city": "Paris"}, idx=0),
        ev("get_weather", {}, raw="Rome please", idx=1),
    ]
    s = check(events, PAIR, match="parallel")
    assert s.value == 0.0 and "not valid JSON" in s.reason


def test_malformed_arguments_never_match_even_all_optional_call():
    events = [ev("ping", {}, raw="oops")]
    s = check(events, [{"ping": {"v": ["1", ""]}}])
    assert s.value == 0.0 and "not valid JSON" in s.reason
    assert check(events, [{"ping": {}}]).value == 0.0


def test_valid_empty_object_is_just_missing_arguments():
    s = check([ev("get_weather", {}, raw=None)], WEATHER)
    assert s.value == 0.0 and "missing" in s.reason


# --- invalid configuration / expected calls -------------------------------

def test_unknown_match_mode():
    s = check([], WEATHER, match="sometimes")
    assert s.value == 0.0 and "match" in s.reason


@pytest.mark.parametrize("bad", [
    [{"a": {}, "b": {}}],     # two functions in one call
    ["get_weather"],          # not a mapping
    [{"a": ["x"]}],           # arguments not a mapping
    "get_weather",            # not a list/mapping
])
def test_invalid_expected_calls(bad):
    s = check(log(("a", {})), bad)
    assert s.value == 0.0 and "expected_calls" in s.reason


# --- evaluator wiring -----------------------------------------------------

def run(evaluator, **context):
    return asyncio.run(evaluator.evaluate(prompt="p", response="r", **context))


def test_reads_expected_calls_from_case_metadata_and_tool_events():
    e = ToolCallMatchEvaluator()
    ok = run(e, metadata={"expected_calls": WEATHER},
             tool_events=log(("get_weather", {"city": "Paris"})))
    assert ok.value == 1.0, ok.reason
    bad = run(e, metadata={"expected_calls": WEATHER}, tool_events=[])
    assert bad.value == 0.0


def test_case_without_expected_calls_is_not_applicable():
    e = ToolCallMatchEvaluator()
    assert run(e, metadata={}, tool_events=[]) is None
    assert run(e, tool_events=[]) is None


def test_none_mode_applies_without_expected_calls():
    e = ToolCallMatchEvaluator(match="none")
    assert run(e, metadata={}, tool_events=[]).value == 1.0
    assert run(e, tool_events=log(("x", {}))).value == 0.0


def test_expected_calls_empty_list_with_default_mode_is_an_error():
    s = run(ToolCallMatchEvaluator(), metadata={"expected_calls": []}, tool_events=[])
    assert s.value == 0.0 and "match: none" in s.reason


def test_factory_builds_with_config():
    f = BUILTIN_EVALUATOR_FACTORIES["tool_call_match"]
    e = f({"match": "parallel", "case_sensitive": False, "normalize_whitespace": True}, None)
    assert (e.match, e.case_sensitive, e.normalize_whitespace) == ("parallel", False, True)
    d = f({}, None)
    assert (d.match, d.case_sensitive, d.normalize_whitespace) == ("single", True, False)


def test_registered_in_evaluator_registry():
    from core.evaluators import EVALUATOR_REGISTRY
    assert EVALUATOR_REGISTRY["tool_call_match"] is ToolCallMatchEvaluator


def test_run_without_case_scores_zero_with_reason():
    """Contract mode / gateway call run(response): no case, no tool log."""
    s = ToolCallMatchEvaluator().run("anything")
    assert s.value == 0.0
    assert "dataset" in s.reason and "tool-call log" in s.reason

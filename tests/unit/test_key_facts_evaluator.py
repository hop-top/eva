import json

import pytest

from core.dataset import Dataset
from core.evaluators.builtin import BUILTIN_EVALUATOR_FACTORIES
from core.evaluators.key_facts import KeyFactsEvaluator
from core.plugins import make_manager
from core.runner import Runner

SUMMARY = "The Eiffel Tower in Paris opened in 1889 and is 330 m tall."


def case(required=None, forbidden=None):
    kf = {}
    if required is not None:
        kf["required"] = required
    if forbidden is not None:
        kf["forbidden"] = forbidden
    return {"metadata": {"key_facts": kf}}


def score(resp, c, **kw):
    return KeyFactsEvaluator(**kw).run_case(resp, c)


def test_full_coverage():
    s = score(SUMMARY, case(["Paris", "1889", "330 m"]))
    assert s.value == 1.0 and s.reason is None


def test_partial_coverage():
    s = score(SUMMARY, case(["Paris", "1889", "London", "Rome"]))
    assert s.value == 0.5
    assert "missing 2/4" in s.reason and "'London'" in s.reason and "'Rome'" in s.reason
    assert "'Paris'" not in s.reason


def test_zero_coverage():
    s = score(SUMMARY, case(["London", "Rome"]))
    assert s.value == 0.0 and "missing 2/2" in s.reason


def test_any_variant_counts():
    c = case([["1889", "eighteen eighty-nine"], ["Paris"]])
    assert score(SUMMARY, c).value == 1.0
    assert score("Opened in eighteen eighty-nine in Paris", c).value == 1.0
    s = score("Opened in Paris", c)
    assert s.value == 0.5
    assert "'1889' | 'eighteen eighty-nine'" in s.reason


def test_forbidden_forces_zero():
    s = score(SUMMARY + " Built by Gustave Doré.", case(["Paris"], ["Doré"]))
    assert s.value == 0.0 and "forbidden present: 'Doré'" in s.reason


def test_forbidden_absent_is_fine():
    assert score(SUMMARY, case(["Paris"], ["Berlin"])).value == 1.0


def test_forbidden_only_case():
    assert score("fine", case(forbidden=["bad"])).value == 1.0
    assert score("so bad", case(forbidden=["bad"])).value == 0.0


def test_forbidden_hit_reason_also_lists_missing():
    s = score("Berlin", case(["Paris"], ["Berlin"]))
    assert s.value == 0.0
    assert "missing 1/1" in s.reason and "forbidden present: 'Berlin'" in s.reason


def test_threshold_default_requires_all():
    assert score(SUMMARY, case(["Paris", "London"])).value == 0.5


def test_score_is_always_true_coverage():
    c = case(["Paris", "1889", "London"])
    for t in (0.1, 0.6, 0.7, 1.0):
        assert score(SUMMARY, c, threshold=t).value == pytest.approx(2 / 3)


def test_threshold_does_not_override_forbidden():
    assert score("Paris Berlin", case(["Paris"], ["Berlin"]), threshold=0.1).value == 0.0


@pytest.mark.parametrize("bad", [0, -0.1, 1.5, "1", True])
def test_bad_threshold_rejected(bad):
    with pytest.raises(ValueError):
        KeyFactsEvaluator(threshold=bad)


def test_case_insensitive_by_default():
    assert score("PARIS", case(["paris"])).value == 1.0
    assert score("PARIS", case(["paris"]), case_sensitive=True).value == 0.0
    assert score("paris", case(["paris"]), case_sensitive=True).value == 1.0


def test_case_insensitive_applies_to_forbidden():
    assert score("BERLIN", case(["x"], ["berlin"])).value == 0.0


def test_whitespace_normalised_by_default():
    assert score("330\n  m\ttall", case(["330 m"])).value == 1.0
    assert score("a   b", case(["a  b"])).value == 1.0
    assert score("330\n m", case(["330 m"]), normalize_whitespace=False).value == 0.0
    assert score("330 m", case(["330 m"]), normalize_whitespace=False).value == 1.0


def test_substring_not_whole_word():
    assert score("parisian", case(["paris"])).value == 1.0


def test_reasoning_not_counted():
    assert score("<think>Paris</think>Rome", case(["Paris"])).value == 0.0
    assert score("<think>x</think>Paris", case(["Paris"])).value == 1.0


def test_field_scoping():
    resp = json.dumps({"summary": "Paris 1889", "notes": "London"})
    c = case(["Paris", "London"])
    assert score(resp, c, field="summary").value == 0.5
    assert score(resp, c, field="notes").value == 0.5
    s = score(resp, c, field="nope")
    assert s.value == 0.0 and "field 'nope' missing" in s.reason
    assert score("not json", c, field="summary").value == 0.0
    assert "not a string" in score('{"a": 1}', c, field="a").reason


def test_not_applicable_without_facts():
    assert score("x", {}) is None
    assert score("x", {"metadata": {}}) is None
    assert score("x", case([], [])) is None


def test_config_fallback_when_case_has_none():
    ev = KeyFactsEvaluator(required=["Paris"], forbidden=["Berlin"])
    assert ev.run_case(SUMMARY, {}).value == 1.0
    assert ev.run_case("Berlin", {}).value == 0.0


def test_case_facts_win_over_config():
    ev = KeyFactsEvaluator(required=["London"])
    assert ev.run_case(SUMMARY, case(["Paris"])).value == 1.0


@pytest.mark.parametrize(
    "c",
    [
        case([[]]),
        case([""]),
        case([["a", 1]]),
        case([5]),
        case("Paris"),
        case(["a"], [3]),
        {"metadata": {"key_facts": ["Paris"]}},
    ],
)
def test_malformed_case_facts_score_zero_with_reason(c):
    s = score("Paris", c)
    assert s.value == 0.0 and "invalid facts" in s.reason


# Contract mode: evaluators get run(response) with no case.
def test_contract_mode_without_facts_scores_zero():
    s = KeyFactsEvaluator().run(SUMMARY)
    assert s.value == 0.0 and "no facts" in s.reason


def test_contract_mode_with_config_facts():
    f = BUILTIN_EVALUATOR_FACTORIES["key_facts"]
    ev = f({"name": "key_facts", "required": [["Paris"], "1889"], "forbidden": ["Berlin"]}, None)
    assert ev.run(SUMMARY).value == 1.0
    assert ev.run("Paris, Berlin").value == 0.0


def test_registered():
    from core.evaluators import EVALUATOR_REGISTRY

    assert EVALUATOR_REGISTRY["key_facts"] is KeyFactsEvaluator
    ev = BUILTIN_EVALUATOR_FACTORIES["key_facts"](
        {"name": "key_facts", "threshold": 0.5, "case_sensitive": True}, None
    )
    assert ev.case_sensitive is True


@pytest.mark.asyncio
async def test_dataset_run_threshold_drives_pass_not_score():
    ds = Dataset(
        name="d",
        target="http://x",
        evaluators=[{"name": "key_facts", "threshold": 0.5}],
        tests=[
            {"id": "ok", "input": "sum", "metadata": {"key_facts": {"required": ["Paris", "London"]}}},
            {"id": "low", "input": "sum", "metadata": {"key_facts": {"required": ["Rome", "London"]}}},
            {"id": "none", "input": "sum"},
        ],
    )

    async def call(i, t):
        return SUMMARY

    run = await Runner(pm=make_manager(), call_agent=call).execute(ds)
    by = {r.test_id: r for r in run.results}
    assert by["ok"].passed and by["ok"].score.value == 0.5
    assert not by["low"].passed and by["low"].score.value == 0.0
    assert "none" not in by and any("none" in s for s in run.skipped)


@pytest.mark.asyncio
async def test_dataset_run_default_needs_all_facts():
    ds = Dataset(
        name="d",
        target="http://x",
        evaluators=[{"name": "key_facts"}],
        tests=[{"id": "t", "input": "s", "metadata": {"key_facts": {"required": ["Paris", "London"]}}}],
    )

    async def call(i, t):
        return SUMMARY

    run = await Runner(pm=make_manager(), call_agent=call).execute(ds)
    assert not run.results[0].passed and run.results[0].score.value == 0.5

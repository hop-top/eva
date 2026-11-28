"""Per-category scoring: runner, stored-run derivation, since-date, compare."""
import datetime as dt
import json

import pytest

from core.categories import (
    UNCATEGORISED,
    category_scores,
    parse_since,
    since_score,
)
from core.dataset import Dataset
from core.plugins import make_manager
from core.query import compare_runs, get_run_cases
from core.runner import Runner
from core.storage import SqliteStorage

ANSWERS = {"q-math-ok": "4", "q-math-bad": "5", "q-code-ok": "yes",
           "q-free": "4", "q-old": "4", "q-new": "9", "q-skip": "whatever"}


def case(id, expected="4", category=None, added=None):
    meta = {}
    if category is not None:
        meta["category"] = category
    if added is not None:
        meta["added"] = added
    c = {"id": id, "input": id, "metadata": meta}
    if expected is not None:
        c["expected_output"] = expected
    return c


def dataset(tests, name="mix"):
    return Dataset(
        name=name, target="http://x",
        evaluators=[{"name": "exact_match", "mode": "binary"}],
        tests=tests,
    )


async def run_ds(ds, storage=None, answers=ANSWERS):
    async def call(input, target):
        return answers[input]

    return await Runner(pm=make_manager(), call_agent=call, storage=storage).execute(ds)


def dump(cats):
    return {k: v.model_dump() for k, v in cats.items()}


MIXED = [
    case("q-math-ok", category="math"),
    case("q-math-bad", category="math"),
    case("q-code-ok", expected="yes", category="code"),
]


@pytest.mark.asyncio
async def test_two_categories_mixed_results():
    run = await run_ds(dataset(MIXED))
    assert dump(run.categories) == {
        "math": {"passed": 1, "total": 2},
        "code": {"passed": 1, "total": 1},
    }


@pytest.mark.asyncio
async def test_json_carries_passed_total_per_category():
    run = await run_ds(dataset(MIXED))
    data = json.loads(run.model_dump_json())
    assert data["categories"] == {
        "math": {"passed": 1, "total": 2},
        "code": {"passed": 1, "total": 1},
    }


@pytest.mark.asyncio
async def test_uncategorised_bucket_not_dropped():
    run = await run_ds(dataset(MIXED + [case("q-free")]))
    assert run.categories[UNCATEGORISED].model_dump() == {"passed": 1, "total": 1}
    assert run.categories["math"].model_dump() == {"passed": 1, "total": 2}


@pytest.mark.asyncio
async def test_case_skipped_by_every_evaluator_is_not_scored():
    run = await run_ds(dataset(MIXED + [case("q-skip", expected=None, category="math")]))
    # not a pass, not a fail, not in total; still listed as unscored
    assert run.categories["math"].model_dump() == {"passed": 1, "total": 2}
    skipped = [c for c in run.cases if c.test_id == "q-skip"]
    assert len(skipped) == 1 and skipped[0].scored is False and skipped[0].passed is False


@pytest.mark.asyncio
async def test_all_cases_skipped_gives_no_category_entry():
    run = await run_ds(dataset([case("q-skip", expected=None, category="math")]))
    assert dump(run.categories) == {}


@pytest.mark.asyncio
async def test_case_with_two_evaluators_passes_only_if_all_pass():
    ds = Dataset(
        name="two", target="http://x",
        evaluators=[{"name": "exact_match", "mode": "binary"},
                    {"name": "exact_match", "mode": "binary"}],
        tests=[case("q-math-ok", category="math")],
    )
    assert dump((await run_ds(ds)).categories) == {"math": {"passed": 1, "total": 1}}


@pytest.mark.asyncio
async def test_non_string_category_and_date_metadata_normalised():
    ds = dataset([
        {"id": "q-math-ok", "input": "q-math-ok", "expected_output": "4",
         "metadata": {"category": 7, "added": dt.date(2026, 3, 1)}},
    ])
    run = await run_ds(ds, SqliteStorage("sqlite:///:memory:"))
    assert dump(run.categories) == {"7": {"passed": 1, "total": 1}}
    assert run.cases[0].added == "2026-03-01"


@pytest.mark.asyncio
async def test_since_with_and_without_added():
    cases = [
        case("q-old", category="a", added="2026-01-10"),
        case("q-new", category="a", added="2026-03-01"),   # fails (answer 9)
        case("q-math-ok", category="a", added="2026-03-05"),
        case("q-free", category="a"),                       # no date
    ]
    run = await run_ds(dataset(cases))
    s = since_score(run.cases, parse_since("2026-03-01"))
    assert s.model_dump() == {
        "since": "2026-03-01", "passed": 1, "total": 2, "excluded": 1,
    }
    # boundary is inclusive; later date narrows
    s2 = since_score(run.cases, parse_since("2026-03-02"))
    assert (s2.passed, s2.total, s2.excluded) == (1, 1, 1)


@pytest.mark.asyncio
async def test_since_ignores_malformed_added_as_missing():
    run = await run_ds(dataset([case("q-math-ok", added="soon", category="a")]))
    s = since_score(run.cases, parse_since("2026-01-01"))
    assert (s.passed, s.total, s.excluded) == (0, 0, 1)


def test_parse_since_rejects_garbage():
    with pytest.raises(ValueError):
        parse_since("yesterday")


@pytest.mark.asyncio
async def test_stored_run_derives_same_figures():
    storage = SqliteStorage("sqlite:///:memory:")
    cases = MIXED + [case("q-free"), case("q-skip", expected=None, category="math")]
    run = await run_ds(dataset(cases), storage)
    storage.save_run(run)
    stored = get_run_cases(storage, run.run_id)
    assert category_scores(stored) == run.categories
    assert {c.test_id: c.scored for c in stored}["q-skip"] is False


@pytest.mark.asyncio
async def test_stored_run_since_matches_live():
    storage = SqliteStorage("sqlite:///:memory:")
    cases = [case("q-new", category="a", added="2026-03-01"),
             case("q-math-ok", category="a", added="2026-03-05"),
             case("q-free", category="a")]
    run = await run_ds(dataset(cases), storage)
    storage.save_run(run)
    since = parse_since("2026-03-01")
    assert since_score(get_run_cases(storage, run.run_id), since) == since_score(run.cases, since)


@pytest.mark.asyncio
async def test_compare_runs_reports_per_category_diff():
    storage = SqliteStorage("sqlite:///:memory:")
    left = await run_ds(dataset(MIXED, name="d"), storage)
    storage.save_run(left)
    better = {**ANSWERS, "q-math-bad": "4"}
    right = await run_ds(dataset(MIXED + [case("q-free", category="extra")], name="d"),
                         storage, answers=better)
    storage.save_run(right)
    res = compare_runs(storage, left.run_id, right.run_id)
    d = res["category_diffs"]
    assert d["math"]["left"] == {"passed": 1, "total": 2}
    assert d["math"]["right"] == {"passed": 2, "total": 2}
    assert d["math"]["pass_rate_diff"] == pytest.approx(0.5)
    assert d["extra"]["left"] is None
    assert d["extra"]["right"] == {"passed": 1, "total": 1}
    assert d["extra"]["pass_rate_diff"] is None

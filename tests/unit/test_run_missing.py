"""Selecting the cases a target has no stored result for."""
from __future__ import annotations

import pytest

from core.chat_targets import TargetError
from core.dataset import Dataset
from core.missing import select_missing
from core.plugins import make_manager
from core.runner import Runner
from core.storage import SqliteStorage


def case(i, cat=None, **extra):
    md = {"category": cat} if cat else {}
    return {"id": f"c{i}", "input": f"q{i}", "metadata": md, **extra}


def ds(cases, target_id="m1", append_only=False):
    return Dataset(
        name="d",
        target="http://x",
        target_id=target_id,
        append_only=append_only,
        evaluators=[{"name": "contains", "substring": "ok"}],
        tests=cases,
    )


@pytest.fixture
def store(tmp_path):
    return SqliteStorage(f"sqlite:///{tmp_path}/s.db")


async def run(dataset, store, fail=()):
    calls = []

    async def call(prompt, target):
        calls.append(prompt)
        if prompt in fail:
            raise TargetError("HTTP 500: boom")
        return "ok"

    await Runner(pm=make_manager(), call_agent=call, storage=store).execute(dataset)
    return calls


def ids(sel):
    return [t.id for t in sel.selected]


def test_fresh_target_has_everything_missing(store):
    sel = select_missing(ds([case(1), case(2), case(3)]), store)
    assert (sel.scored, sel.missing, ids(sel)) == (3, 3, ["c1", "c2", "c3"])


@pytest.mark.asyncio
async def test_after_a_run_nothing_is_missing(store):
    d = ds([case(1), case(2)])
    await run(d, store)
    sel = select_missing(d, store)
    assert (sel.scored, sel.missing, ids(sel)) == (2, 0, [])


@pytest.mark.asyncio
async def test_appended_cases_are_the_only_ones_missing(store):
    await run(ds([case(1), case(2)]), store)
    grown = ds([case(1), case(2), case(3), case(4), case(5)])
    assert ids(select_missing(grown, store)) == ["c3", "c4", "c5"]
    assert await run(Dataset(**{**grown.model_dump(), "tests": select_missing(grown, store).selected}), store) == ["q3", "q4", "q5"]
    assert select_missing(grown, store).missing == 0


@pytest.mark.asyncio
async def test_case_that_hit_an_upstream_error_is_retried(store):
    d = ds([case(1), case(2)])
    await run(d, store, fail={"q2"})
    assert ids(select_missing(d, store)) == ["c2"]


@pytest.mark.asyncio
async def test_result_for_an_old_hash_does_not_count(store):
    await run(ds([case(1)]), store)
    edited = ds([{**case(1), "input": "q1 reworded"}])
    assert ids(select_missing(edited, store)) == ["c1"]


@pytest.mark.asyncio
async def test_superseded_case_never_selected(store):
    old = ds([case(1), case(2)], append_only=True)
    await run(old, store)
    newer = ds([case(1), case(2), case(3, supersedes="c2")], append_only=True)
    # c2 is superseded by c3: c3 is missing, c2 (even if it had no result) is not.
    assert ids(select_missing(newer, store)) == ["c3"]
    fresh = SqliteStorage("sqlite://")
    assert ids(select_missing(newer, fresh)) == ["c1", "c3"]


@pytest.mark.asyncio
async def test_other_target_has_its_own_results(store):
    await run(ds([case(1), case(2)], target_id="m1"), store)
    assert ids(select_missing(ds([case(1), case(2)], target_id="m2"), store)) == ["c1", "c2"]


def test_category_filter(store):
    d = ds([case(1, "math"), case(2, "code"), case(3, "math"), case(4)])
    sel = select_missing(d, store, category="math")
    assert (sel.scored, sel.missing, ids(sel)) == (4, 2, ["c1", "c3"])
    assert select_missing(d, store, category="nope").missing == 0


def test_limit_keeps_first_missing_in_dataset_order(store):
    d = ds([case(i, "a") for i in range(1, 6)])
    sel = select_missing(d, store, limit=2)
    assert (sel.missing, ids(sel)) == (5, ["c1", "c2"])
    both = select_missing(ds([case(1), case(2, "a"), case(3, "a")]), store, category="a", limit=1)
    assert ids(both) == ["c2"] and both.missing == 2


def test_limit_below_one_rejected(store):
    with pytest.raises(ValueError, match="limit"):
        select_missing(ds([case(1)]), store, limit=0)


def test_storage_without_case_results_rejected():
    with pytest.raises(ValueError, match="per-case results"):
        select_missing(ds([case(1)]), object())

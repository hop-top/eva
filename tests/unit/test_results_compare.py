"""`eva results compare`: two targets on the cases both answered."""
import json

import pytest

from core.dataset import case_hash
from tests.unit.test_results_cli import eva, rec, seed

L, R = "openai:left", "openai:right"


def cmp(db, *extra, fmt="json"):
    return eva("results", "compare", "--db", db, "--dataset", "ds",
               "--left-target", L, "--right-target", R, "--format", fmt, *extra)


def data(r):
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def dataset(tmp_path, cases, extra=""):
    ds = tmp_path / "dset"
    ds.mkdir()
    (ds / "dataset.yaml").write_text(
        "name: ds\ntarget: http://x\nappend_only: true\n"
        "evaluators:\n  - {name: contains, substring: ok}\n" + extra)
    (ds / "c.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))
    return ds, {c["id"]: "sha256:" + case_hash(c) for c in cases}


def test_only_shared_cases_count(tmp_path):
    db = seed(tmp_path / "s.db", [
        rec("a", L), rec("a", R, passed=False),   # shared, left only passed
        rec("b", L, passed=False), rec("b", R),   # shared, right only passed
        rec("c", L), rec("c", R),                 # shared, both passed
        rec("d", L), rec("e", R),                 # answered by one side only
    ])
    d = data(cmp(db))
    o = d["overall"]
    assert (o["shared"], o["left_passed"], o["right_passed"]) == (3, 2, 2)
    assert o["only_left"] == ["a"] and o["only_right"] == ["b"]
    assert o["left_rate"] == o["right_rate"] == 0.6667 and o["diff"] == 0.0
    assert d["excluded"] == {"hash_mismatch": 0, "left_only": 1, "right_only": 1}


def test_different_hash_is_not_shared(tmp_path):
    db = seed(tmp_path / "s.db", [
        rec("a", L, chash="sha256:aa"), rec("a", R, passed=False, chash="sha256:bb"),
        rec("b", L), rec("b", R),
    ])
    d = data(cmp(db))
    assert d["overall"]["shared"] == 1
    assert d["overall"]["only_left"] == []
    assert d["excluded"]["hash_mismatch"] == 1


def test_without_dataset_file_single_overall_bucket(tmp_path):
    db = seed(tmp_path / "s.db", [rec("a", L), rec("a", R)])
    d = data(cmp(db))
    assert d["categorised"] is False and d["categories"] == {}
    r = cmp(db, fmt="text")
    assert r.returncode == 0 and "categories unavailable" in r.stdout


def test_categories_with_dataset_file(tmp_path):
    cases = [
        {"id": "a", "input": "1", "metadata": {"category": "code"}},
        {"id": "b", "input": "2", "metadata": {"category": "code"}},
        {"id": "c", "input": "3", "metadata": {"category": "reason"}},
        {"id": "d", "input": "4"},
        {"id": "old", "input": "5", "metadata": {"category": "code"}},
        {"id": "new", "input": "6", "supersedes": "old", "metadata": {"category": "code"}},
    ]
    ds, h = dataset(tmp_path, cases)
    db = seed(tmp_path / "s.db", [
        rec("a", L, chash=h["a"]), rec("a", R, passed=False, chash=h["a"]),
        rec("b", L, passed=False, chash=h["b"]), rec("b", R, chash=h["b"]),
        rec("c", L, chash=h["c"]), rec("c", R, chash=h["c"]),
        rec("d", L, chash=h["d"]), rec("d", R, chash=h["d"]),
        # superseded: dropped with the dataset file
        rec("old", L, chash=h["old"]), rec("old", R, passed=False, chash=h["old"]),
    ])
    d = data(cmp(db, "--dataset-file", str(ds)))
    assert d["categorised"] is True
    assert set(d["categories"]) == {"code", "reason", "uncategorised"}
    code = d["categories"]["code"]
    assert (code["shared"], code["left_passed"], code["right_passed"]) == (2, 1, 1)
    assert code["only_left"] == ["a"] and code["only_right"] == ["b"]
    assert d["categories"]["reason"]["shared"] == 1
    assert d["overall"]["shared"] == 4          # superseded "old" excluded
    assert "old" not in d["overall"]["only_left"]
    # without the file the superseded case counts
    assert data(cmp(db))["overall"]["shared"] == 5


def test_since_needs_dataset_file_and_filters(tmp_path):
    cases = [
        {"id": "a", "input": "1", "metadata": {"added": "2026-02-01"}},
        {"id": "b", "input": "2", "metadata": {"added": "2025-01-01"}},
        {"id": "c", "input": "3"},
    ]
    ds, h = dataset(tmp_path, cases)
    db = seed(tmp_path / "s.db", [
        rec(c, t, passed=(t == L or c != "a"), chash=h[c])
        for c in "abc" for t in (L, R)])
    r = cmp(db, "--since", "2026-01-01")
    assert r.returncode == 2 and "--dataset-file" in r.stderr
    d = data(cmp(db, "--since", "2026-01-01", "--dataset-file", str(ds)))
    s = d["since"]
    assert s["date"] == "2026-01-01" and s["shared"] == 1
    assert s["only_left"] == ["a"] and s["excluded_no_added"] == 1
    assert cmp(db, "--since", "nope", "--dataset-file", str(ds)).returncode == 2


def test_json_shape(tmp_path):
    db = seed(tmp_path / "s.db", [rec("a", L), rec("a", R)])
    d = data(cmp(db))
    assert set(d) == {"dataset", "left_target", "right_target", "categorised",
                      "overall", "categories", "excluded"}
    assert set(d["overall"]) == {"shared", "left_passed", "right_passed", "left_rate",
                                 "right_rate", "diff", "only_left", "only_right"}
    assert (d["dataset"], d["left_target"], d["right_target"]) == ("ds", L, R)


def test_no_shared_cases_null_rates(tmp_path):
    db = seed(tmp_path / "s.db", [rec("a", L), rec("b", R)])
    o = data(cmp(db))["overall"]
    assert o["shared"] == 0 and o["left_rate"] is None and o["diff"] is None


def test_swapping_sides_swaps_lists(tmp_path):
    db = seed(tmp_path / "s.db", [rec("a", L), rec("a", R, passed=False)])
    a = data(cmp(db))["overall"]
    b = data(eva("results", "compare", "--db", db, "--dataset", "ds",
                 "--left-target", R, "--right-target", L, "--format", "json"))["overall"]
    assert a["only_left"] == b["only_right"] == ["a"]
    assert a["only_right"] == b["only_left"] == []


@pytest.mark.parametrize("args", [
    ["--left-target", "nope", "--right-target", R],
    ["--left-target", L, "--right-target", "nope"],
    ["--left-target", L, "--right-target", L],
])
def test_unknown_or_equal_target_exit_2(tmp_path, args):
    db = seed(tmp_path / "s.db", [rec("a", L), rec("a", R)])
    r = eva("results", "compare", "--db", db, "--dataset", "ds", *args)
    assert r.returncode == 2 and r.stdout == "" and r.stderr.strip()


def test_text_output_lists_exclusions(tmp_path):
    db = seed(tmp_path / "s.db", [
        rec("a", L, chash="sha256:aa"), rec("a", R, chash="sha256:bb")])
    r = cmp(db, fmt="text")
    assert r.returncode == 0 and "1 answered under different case hashes" in r.stdout

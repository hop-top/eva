# tests/unit/test_append_only.py
import json
from pathlib import Path

import pytest
import yaml

from core import append_only as ao
from core.dataset import Dataset, EvaTestCase, case_hash, load_dataset

META = {"source": "hand", "licence": "CC0-1.0", "added": "2026-01-02", "origin": "handwritten"}


def case(cid, **kw):
    d = {"id": cid, "input": f"q {cid}", "expected_output": f"a {cid}", "metadata": dict(META)}
    d.update(kw)
    return d


def write_dir(root: Path, files: dict, manifest=None):
    root.mkdir(parents=True, exist_ok=True)
    m = {"name": "pool", "target": "http://x/chat", "append_only": True}
    m.update(manifest or {})
    (root / "dataset.yaml").write_text(yaml.safe_dump(m))
    for name, cases in files.items():
        (root / name).write_text("".join(json.dumps(c) + "\n" for c in cases))
    return root


def write_yaml(path: Path, cases, append_only=True):
    path.write_text(yaml.safe_dump({
        "name": "s", "target": "http://x/chat", "append_only": append_only, "tests": cases,
    }))
    return path


# ---- case hash ----------------------------------------------------------

def test_hash_is_sha256_hex_and_stable():
    h = case_hash(EvaTestCase(**case("a")))
    assert len(h) == 64 and h == case_hash(case("a"))


def test_hash_independent_of_other_cases():
    h1 = case_hash(case("a"))
    _ = [case_hash(case(f"x{i}")) for i in range(3)]
    assert case_hash(case("a")) == h1


@pytest.mark.parametrize("field,value", [
    ("id", "b"), ("input", "other"), ("expected_output", "other"),
    ("retrieval_context", "ctx"), ("planned_steps", ["s"]),
    ("tests", "assert 1"), ("supersedes", "z"),
])
def test_hash_covers_each_content_field(field, value):
    assert case_hash(case("a", **{field: value})) != case_hash(case("a"))


def test_hash_ignores_metadata_and_unset_fields():
    base = case_hash(case("a"))
    assert case_hash(case("a", metadata={"licence": "MIT"})) == base
    assert case_hash(case("a", retrieval_context=None)) == base


def test_hash_tests_list_equals_newline_string():
    assert case_hash(case("a", tests=["x", "y"])) == case_hash(case("a", tests="x\ny"))


# ---- check: edit / removal / collision ----------------------------------

def test_clean_dataset_passes_after_lock(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a"), case("b")]})
    res, rec = ao.lock(d)
    assert res.ok and rec == ["a", "b"]
    assert ao.check(d).ok
    assert json.loads((d / "dataset.lock.json").read_text())["cases"]["a"] == case_hash(case("a"))


def test_unlocked_case_is_a_problem(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a")]})
    assert [p.code for p in ao.check(d).problems] == ["unrecorded"]


def test_edit_refused(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a"), case("b")]})
    ao.lock(d)
    write_dir(d, {"m.jsonl": [case("a", input="edited"), case("b")]})
    res = ao.check(d)
    assert [(p.code, p.id) for p in res.problems] == [("edited", "a")]
    res, rec = ao.lock(d)
    assert [p.code for p in res.problems] == ["edited"] and rec == []


def test_removal_refused(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a"), case("b")]})
    ao.lock(d)
    write_dir(d, {"m.jsonl": [case("b")]})
    assert [(p.code, p.id) for p in ao.check(d).problems] == [("removed", "a")]


def test_id_collision_across_files(tmp_path):
    d = write_dir(tmp_path / "d", {"a.jsonl": [case("x")], "b.jsonl": [case("x", input="other")]})
    assert "collision" in [p.code for p in ao.check(d).problems]


def test_identical_duplicate_id_is_still_a_collision(tmp_path):
    d = write_dir(tmp_path / "d", {"a.jsonl": [case("x"), case("x")]})
    assert "collision" in [p.code for p in ao.check(d).problems]


def test_metadata_correction_allowed_after_lock(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a")]})
    ao.lock(d)
    write_dir(d, {"m.jsonl": [case("a", metadata={**META, "licence": "MIT"})]})
    assert ao.check(d).ok


def test_yaml_dataset_ledger_beside_file(tmp_path):
    p = write_yaml(tmp_path / "s.yaml", [case("a")])
    ao.lock(p)
    assert (tmp_path / "s.lock.json").exists() and ao.check(p).ok
    write_yaml(p, [case("a", input="edited")])
    assert [p_.code for p_ in ao.check(p).problems] == ["edited"]


def test_not_append_only_is_rejected_by_check(tmp_path):
    p = write_yaml(tmp_path / "s.yaml", [case("a")], append_only=False)
    with pytest.raises(ao.NotAppendOnly):
        ao.check(p)


# ---- provenance ---------------------------------------------------------

def test_provenance_enforced_when_append_only(tmp_path):
    bad = case("a", metadata={"source": "x"})
    d = write_dir(tmp_path / "d", {"m.jsonl": [bad]})
    msgs = [p.message for p in ao.check(d).problems if p.code == "provenance"]
    assert any("licence" in m for m in msgs) and any("added" in m for m in msgs)
    assert any("origin" in m for m in msgs)
    res, rec = ao.lock(d)
    assert not res.ok and rec == []


def test_provenance_origin_and_date_validated(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [
        case("a", metadata={**META, "origin": "scraped"}),
        case("b", metadata={**META, "added": "yesterday"}),
    ]})
    msgs = " ".join(p.message for p in ao.check(d).problems)
    assert "origin must be one of" in msgs and "ISO date" in msgs


def test_provenance_accepts_unquoted_yaml_date(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(
        "name: s\ntarget: http://x\nappend_only: true\ntests:\n"
        "  - id: a\n    input: q\n    expected_output: a\n    metadata:\n"
        "      source: s\n      licence: l\n      added: 2026-03-04\n      origin: import\n"
    )
    ao.lock(p)
    assert ao.check(p).ok


def test_provenance_not_required_without_opt_in(tmp_path):
    p = write_yaml(tmp_path / "s.yaml", [{"id": "a", "input": "q"}], append_only=False)
    ds = load_dataset(p)
    assert ds.append_only is False and len(ds.scored_tests()) == 1


# ---- supersession -------------------------------------------------------

def test_superseded_case_excluded_from_scoring_but_kept(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a"), case("a2", supersedes="a"), case("b")]})
    ao.lock(d)
    ds = load_dataset(d)
    assert [t.id for t in ds.tests] == ["a", "a2", "b"]
    assert [t.id for t in ds.scored_tests()] == ["a2", "b"]
    res = ao.check(d)
    assert res.ok and (res.cases, res.scored, res.superseded) == (3, 2, 1)


def test_supersedes_unknown_self_and_cycle(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [
        case("a", supersedes="zz"), case("b", supersedes="b"),
        case("c", supersedes="d"), case("d", supersedes="c"),
    ]})
    msgs = " | ".join(p.message for p in ao.check(d).problems if p.code == "supersedes")
    assert "unknown case zz" in msgs and "itself" in msgs and "cycle" in msgs


def test_supersedes_ignored_when_not_append_only():
    ds = Dataset(name="n", target="t", tests=[
        EvaTestCase(id="a", input="q"), EvaTestCase(id="b", input="q", supersedes="a")])
    assert [t.id for t in ds.scored_tests()] == ["a", "b"]


@pytest.mark.asyncio
async def test_runner_skips_superseded_cases():
    from core.plugins import make_manager
    from core.runner import Runner

    seen = []

    async def call(input, target):
        seen.append(input)
        return "ok"

    ds = Dataset(name="n", target="t", append_only=True, tests=[
        EvaTestCase(id="a", input="old"), EvaTestCase(id="b", input="new", supersedes="a")])
    run = await Runner(pm=make_manager(), call_agent=call).execute(ds)
    assert seen == ["new"] and {r.test_id for r in run.results} <= {"b"}


# ---- add ----------------------------------------------------------------

def test_add_appends_and_records(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a")]})
    ao.lock(d)
    added, skipped, problems = ao.add(d, [case("b"), case("c")])
    assert (added, skipped, problems) == (["b", "c"], [], [])
    assert [t.id for t in load_dataset(d).tests] == ["a", "b", "c"]
    assert ao.check(d).ok


def test_readd_identical_is_noop(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a")]})
    ao.lock(d)
    before = ((d / "m.jsonl").read_text(), (d / "dataset.lock.json").read_text())
    added, skipped, problems = ao.add(d, [case("a")])
    assert (added, skipped, problems) == ([], ["a"], [])
    assert ((d / "m.jsonl").read_text(), (d / "dataset.lock.json").read_text()) == before


def test_readd_with_different_content_refused_and_nothing_written(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a")]})
    ao.lock(d)
    before = (d / "m.jsonl").read_text()
    added, skipped, problems = ao.add(d, [case("new"), case("a", input="changed")])
    assert added == [] and [p.code for p in problems] == ["conflict"]
    assert (d / "m.jsonl").read_text() == before


def test_add_refuses_missing_provenance_and_dry_run_writes_nothing(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a")]})
    ao.lock(d)
    _, _, problems = ao.add(d, [{"id": "n", "input": "q", "expected_output": "a"}])
    assert {p.code for p in problems} == {"provenance"}
    before = (d / "m.jsonl").read_text()
    added, _, problems = ao.add(d, [case("n")], dry_run=True)
    assert added == ["n"] and not problems and (d / "m.jsonl").read_text() == before


def test_add_new_file_and_file_choice(tmp_path):
    d = write_dir(tmp_path / "d", {"a.jsonl": [case("a")], "b.jsonl": [case("b")]})
    ao.lock(d)
    with pytest.raises(ValueError):
        ao.add(d, [case("c")])
    ao.add(d, [case("c")], file="c.jsonl")
    assert (d / "c.jsonl").exists()
    with pytest.raises(ValueError):
        ao.add(d, [case("e")], file="../x.jsonl")


def test_add_validates_supersedes(tmp_path):
    d = write_dir(tmp_path / "d", {"m.jsonl": [case("a")]})
    ao.lock(d)
    _, _, problems = ao.add(d, [case("b", supersedes="nope")])
    assert [p.code for p in problems] == ["supersedes"]
    added, _, problems = ao.add(d, [case("b", supersedes="a")])
    assert added == ["b"] and not problems


# ---- directory loading --------------------------------------------------

def test_directory_loads_sorted_files_in_order(tmp_path):
    d = write_dir(tmp_path / "d", {"z.jsonl": [case("z1")], "a.jsonl": [case("a1"), case("a2")]})
    ds = load_dataset(d)
    assert [t.id for t in ds.tests] == ["a1", "a2", "z1"]
    assert ds.name == "pool" and ds.target == "http://x/chat" and ds.append_only
    assert all("category" not in t.metadata for t in ds.tests)


def test_directory_without_manifest_needs_target(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    (d / "x.jsonl").write_text(json.dumps({"id": "a", "input": "q"}) + "\n")
    with pytest.raises(ValueError, match="target"):
        load_dataset(d)
    ds = load_dataset(d, target="http://t/chat")
    assert ds.name == "d" and ds.append_only is False


def test_directory_bad_line_names_file_and_line(tmp_path):
    d = write_dir(tmp_path / "d", {})
    (d / "bad.jsonl").write_text(json.dumps(case("a")) + "\n{nope\n")
    with pytest.raises(ValueError, match=r"bad\.jsonl:2"):
        load_dataset(d)


def test_existing_yaml_datasets_unchanged():
    ds = load_dataset(Path("tests/fixtures/datasets/simple.yaml"))
    assert ds.append_only is False and ds.scored_tests() == ds.tests

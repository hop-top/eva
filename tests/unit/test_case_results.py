"""Per-case results: records, target identity, first-result-stands, JSONL."""
import json

import pytest
from pydantic import ValidationError

from core.case_results import (
    CaseResult,
    CaseResultFormatError,
    export_records,
    import_records,
    load_jsonl,
)
from core.chat_targets import TargetError
from core.dataset import Dataset, case_hash, load_dataset
from core.plugins import make_manager
from core.runner import Runner
from core.storage import SqliteStorage


def store():
    return SqliteStorage("sqlite:///:memory:")


def make_ds(tests=None, **kw):
    base = dict(
        name="d", target="http://x",
        evaluators=[{"name": "contains", "substring": "ok"}],
        tests=tests or [{"id": "a", "input": "i"}, {"id": "b", "input": "j"}],
    )
    base.update(kw)
    return Dataset(**base)


async def run_with(ds, storage, answer):
    async def call(i, t):
        out = answer(i) if callable(answer) else answer
        if isinstance(out, Exception):
            raise out
        return out

    return await Runner(pm=make_manager(), call_agent=call, storage=storage).execute(ds)


def rec(case="a", target_id="t", passed=True, at="2026-01-01T00:00:00+00:00",
        run_id="r1", chash="sha256:aa", dataset="d", reason=None):
    return CaseResult(
        dataset=dataset, target_id=target_id, case=case, case_hash=chash,
        passed=passed, score=1.0 if passed else 0.0,
        evaluators=[{"name": "contains", "passed": passed,
                     "score": 1.0 if passed else 0.0, "reason": reason, "mode": "binary"}],
        run_id=run_id, at=at,
    )


# ---- target identity ------------------------------------------------------

def chat_ds(base_url, model="m", **extra):
    return make_ds(target={"provider": "openai", "model": model,
                           "base_url": base_url, **extra})


def test_chat_target_id_ignores_base_url_and_sampling():
    a = chat_ds("http://localhost:1/v1", temperature=0.2)
    b = chat_ds("https://host.example/v1", temperature=0.9)
    assert a.target != b.target  # run label still carries the base url
    assert a.result_target_id == b.result_target_id == "openai:m"


def test_url_target_id_is_the_url():
    assert make_ds().result_target_id == "http://x"


def test_explicit_id_overrides():
    assert chat_ds("http://h/v1", id="mine").result_target_id == "mine"
    assert make_ds(target_id="u").result_target_id == "u"
    ds = make_ds()
    ds.target_id = "flag"
    assert ds.result_target_id == "flag"


def test_target_id_from_yaml_mapping_and_cli_override(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text(
        "name: d\ntarget:\n  provider: openai\n  model: m\n  id: pinned\n"
        "tests:\n  - {id: a, input: i}\n"
    )
    assert load_dataset(p).result_target_id == "pinned"
    assert load_dataset(p, target_id="x").result_target_id == "x"


def test_reserved_evaluator_name_target_is_a_config_error():
    with pytest.raises(ValidationError, match="'target' is reserved"):
        make_ds(evaluators=[{"name": "target"}])


# ---- runner records ---------------------------------------------------------

@pytest.mark.asyncio
async def test_run_records_one_result_per_case_with_hash():
    st = store()
    ds = make_ds()
    run = await run_with(ds, st, lambda i: "ok" if i == "i" else "nope")
    got = {r.case: r for r in st.get_case_results("d")}
    assert set(got) == {"a", "b"}
    a = got["a"]
    assert a.passed and a.score == 1.0
    assert a.case_hash == "sha256:" + case_hash(ds.tests[0])
    assert a.target_id == "http://x" and a.run_id == run.run_id
    assert a.at == run.started_at.isoformat()
    assert a.evaluators[0].name == "contains" and a.evaluators[0].mode == "binary"
    assert not got["b"].passed
    assert got["b"].evaluators[0].reason


@pytest.mark.asyncio
async def test_first_result_stands_across_runs():
    st = store()
    ds = make_ds()
    first = await run_with(ds, st, "ok")
    await run_with(ds, st, "nope")
    got = st.get_case_results("d")
    assert len(got) == 2
    assert all(r.passed and r.run_id == first.run_id for r in got)


@pytest.mark.asyncio
async def test_upstream_errors_not_recorded_then_recorded_later():
    st = store()
    ds = make_ds()
    await run_with(ds, st, lambda i: TargetError("down") if i == "j" else "ok")
    assert [r.case for r in st.get_case_results("d")] == ["a"]
    await run_with(ds, st, "ok")
    assert sorted(r.case for r in st.get_case_results("d")) == ["a", "b"]


@pytest.mark.asyncio
async def test_case_with_no_applicable_evaluator_not_recorded():
    st = store()
    ds = make_ds(
        evaluators=[{"name": "exact_match"}],
        tests=[{"id": "a", "input": "i", "expected_output": "ok"},
               {"id": "b", "input": "j"}],
    )
    await run_with(ds, st, "ok")
    assert [r.case for r in st.get_case_results("d")] == ["a"]


@pytest.mark.asyncio
async def test_superseded_cases_not_run_or_recorded():
    st = store()
    ds = make_ds(append_only=True, tests=[
        {"id": "a", "input": "i"},
        {"id": "a2", "input": "i2", "supersedes": "a"},
    ])
    await run_with(ds, st, "ok")
    assert [r.case for r in st.get_case_results("d")] == ["a2"]


@pytest.mark.asyncio
async def test_results_keyed_per_target_and_dataset():
    st = store()
    await run_with(make_ds(target="http://one"), st, "ok")
    await run_with(make_ds(target="http://two"), st, "nope")
    assert {r.target_id for r in st.get_case_results("d")} == {"http://one", "http://two"}
    assert len(st.get_case_results("d", target_id="http://two")) == 2
    assert [r.case for r in st.get_case_results("d", case_ids=["a"])] == ["a", "a"]
    assert st.get_case_results("other") == []


def test_put_is_insert_if_absent():
    st = store()
    assert st.put_case_results([rec(passed=True)]) == 1
    assert st.put_case_results([rec(passed=False, run_id="r2"), rec(case="b")]) == 1
    got = {r.case: r for r in st.get_case_results("d")}
    assert got["a"].passed and got["a"].run_id == "r1"


# ---- JSONL export / import --------------------------------------------------

def test_export_import_round_trip(tmp_path):
    src, dst = store(), store()
    src.put_case_results([rec("a", "openai:m", reason="é"), rec("b", "openai:m", passed=False),
                          rec("a", "http://x/y")])
    rep = export_records(src.get_case_results("d"), tmp_path)
    assert sum(f["records"] for f in rep["files"]) == 3
    files = sorted(tmp_path.rglob("*.jsonl"))
    assert len(files) == 2
    assert all(f.parent.parent == tmp_path for f in files)
    line = json.loads(files[0].read_text().splitlines()[0])
    assert line["v"] == 1 and line["case_hash"].startswith("sha256:")

    out = import_records(dst, load_jsonl([tmp_path]))
    assert out["inserted"] == 3 and out["conflicts"] == []
    assert sorted(dst.get_case_results("d"), key=lambda r: (r.target_id, r.case)) == \
        sorted(src.get_case_results("d"), key=lambda r: (r.target_id, r.case))
    # idempotent
    assert import_records(dst, load_jsonl([tmp_path]))["inserted"] == 0


def test_reexport_is_byte_identical(tmp_path):
    st = store()
    st.put_case_results([rec("b"), rec("a")])
    export_records(st.get_case_results("d"), tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.jsonl")}
    [f] = before
    assert [json.loads(l)["case"] for l in f.read_text().splitlines()] == ["a", "b"]
    export_records(st.get_case_results("d"), tmp_path)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.jsonl")} == before


def test_export_dry_run_writes_nothing(tmp_path):
    st = store()
    st.put_case_results([rec()])
    rep = export_records(st.get_case_results("d"), tmp_path / "out", dry_run=True)
    assert rep["dry_run"] and rep["files"][0]["records"] == 1
    assert not (tmp_path / "out").exists()


def test_export_keeps_foreign_records_in_existing_file(tmp_path):
    a, b = store(), store()
    a.put_case_results([rec("a")])
    b.put_case_results([rec("b")])
    export_records(a.get_case_results("d"), tmp_path)
    export_records(b.get_case_results("d"), tmp_path)
    assert len(load_jsonl([tmp_path])) == 2


def test_import_dry_run_writes_nothing(tmp_path):
    src, dst = store(), store()
    src.put_case_results([rec()])
    export_records(src.get_case_results("d"), tmp_path)
    out = import_records(dst, load_jsonl([tmp_path]), dry_run=True)
    assert out["inserted"] == 1 and out["dry_run"]
    assert dst.get_case_results("d") == []


def test_import_conflict_earlier_wins_and_is_reported():
    st = store()
    st.put_case_results([rec(passed=False, at="2026-02-01T00:00:00+00:00", run_id="late")])
    out = import_records(st, [rec(passed=True, at="2026-01-01T00:00:00+00:00", run_id="early")])
    assert len(out["conflicts"]) == 1
    c = out["conflicts"][0]
    assert c["case"] == "a" and c["kept_run_id"] == "early" and c["other_run_id"] == "late"
    [only] = st.get_case_results("d")
    assert only.run_id == "early" and only.passed


def test_import_conflict_keeps_local_when_local_is_earlier():
    st = store()
    st.put_case_results([rec(passed=True, at="2026-01-01T00:00:00+00:00", run_id="a1")])
    out = import_records(st, [rec(passed=False, at="2026-03-01T00:00:00+00:00", run_id="z")])
    assert out["conflicts"][0]["kept_run_id"] == "a1"
    assert st.get_case_results("d")[0].run_id == "a1"


def test_import_tie_on_time_smaller_run_id_wins():
    st = store()
    st.put_case_results([rec(passed=False, run_id="b")])
    import_records(st, [rec(passed=True, run_id="a")])
    assert st.get_case_results("d")[0].run_id == "a"


def test_import_identical_payload_is_noop_not_conflict():
    st = store()
    st.put_case_results([rec(run_id="r1")])
    out = import_records(st, [rec(run_id="r2", at="2027-01-01T00:00:00+00:00")])
    assert out["unchanged"] == 1 and out["conflicts"] == []
    assert st.get_case_results("d")[0].run_id == "r1"


def test_import_hash_mismatch_keeps_both_and_reports():
    st = store()
    st.put_case_results([rec(chash="sha256:aa")])
    out = import_records(st, [rec(chash="sha256:bb")])
    assert out["inserted"] == 1 and out["conflicts"] == []
    assert out["hash_mismatches"] == [{"dataset": "d", "target_id": "t", "case": "a",
                                       "hashes": ["sha256:aa", "sha256:bb"]}]
    assert len(st.get_case_results("d")) == 2


def test_load_rejects_malformed_and_unknown_version(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text("not json\n")
    with pytest.raises(CaseResultFormatError, match="x.jsonl:1"):
        load_jsonl([p])
    good = json.loads(rec().model_dump_json())
    p.write_text(json.dumps({**good, "v": 2}) + "\n")
    with pytest.raises(CaseResultFormatError, match="version"):
        load_jsonl([p])
    with pytest.raises(CaseResultFormatError, match="not found"):
        load_jsonl([tmp_path / "missing"])

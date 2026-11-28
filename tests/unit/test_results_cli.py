"""`eva results list|export|import`."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.case_results import CaseResult
from core.dataset import case_hash
from core.storage import SqliteStorage

REPO = Path(__file__).resolve().parents[2]


def eva(*args, cwd=REPO):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=env,
    )


def rec(case, target_id="openai:m", passed=True, chash="sha256:aa",
        at="2026-01-01T00:00:00+00:00", run_id="r1", dataset="ds"):
    return CaseResult(
        dataset=dataset, target_id=target_id, case=case, case_hash=chash,
        passed=passed, score=1.0 if passed else 0.0,
        evaluators=[{"name": "contains", "passed": passed, "score": 1.0,
                     "reason": None, "mode": "binary"}],
        run_id=run_id, at=at,
    )


def seed(path, records):
    SqliteStorage(db_url=f"sqlite:///{path}").put_case_results(records)
    return str(path)


@pytest.fixture
def db(tmp_path):
    return seed(tmp_path / "s.db", [
        rec("a"), rec("b", passed=False), rec("c", target_id="other:m"),
        rec("z", dataset="elsewhere"),
    ])


def test_list_json(db):
    r = eva("results", "list", "--db", db, "--dataset", "ds", "--format", "json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert [x["case"] for x in data["results"]] == ["a", "b", "c"] or \
        {x["case"] for x in data["results"]} == {"a", "b", "c"}
    first = data["results"][0]
    assert set(first) >= {"v", "dataset", "target_id", "case", "case_hash", "passed",
                          "score", "evaluators", "run_id", "at"}


def test_list_filters(db):
    r = eva("results", "list", "--db", db, "--dataset", "ds", "--target", "openai:m",
            "--status", "fail", "--format", "json")
    assert [x["case"] for x in json.loads(r.stdout)["results"]] == ["b"]
    r = eva("results", "list", "--db", db, "--dataset", "ds", "--limit", "1", "--format", "json")
    assert len(json.loads(r.stdout)["results"]) == 1


def test_list_empty_is_ok(db):
    r = eva("results", "list", "--db", db, "--dataset", "nope", "--format", "json")
    assert r.returncode == 0 and json.loads(r.stdout) == {"results": []}


def test_list_text_default(db):
    r = eva("results", "list", "--db", db, "--dataset", "ds")
    assert r.returncode == 0 and "openai:m" in r.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(r.stdout)


@pytest.mark.parametrize("args", [
    ["list", "--dataset", "ds", "--format", "xml"],
    ["list", "--dataset", "ds", "--status", "maybe"],
    ["export", "--dataset", "ds", "--dir", "x", "--format", "xml"],
    ["import", "x", "--format", "xml"],
])
def test_bad_input_exit_2(db, tmp_path, args):
    r = eva("results", *args, "--db", db)
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.strip()


def test_list_with_dataset_file_drops_superseded_and_stale(tmp_path):
    ds = tmp_path / "ds"
    ds.mkdir()
    cases = [{"id": "a", "input": "i"}, {"id": "a2", "input": "i2", "supersedes": "a"},
             {"id": "b", "input": "j"}]
    (ds / "dataset.yaml").write_text(
        "name: ds\ntarget: http://x\nappend_only: true\n"
        "evaluators:\n  - {name: contains, substring: ok}\n"
    )
    (ds / "c.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))
    h = {c["id"]: "sha256:" + case_hash(c) for c in cases}
    db = seed(tmp_path / "s.db", [
        rec("a", chash=h["a"]), rec("a2", chash=h["a2"]),
        rec("b", chash="sha256:stale"),
    ])
    r = eva("results", "list", "--db", db, "--dataset", "ds",
            "--dataset-file", str(ds), "--format", "json")
    assert r.returncode == 0, r.stderr
    assert [x["case"] for x in json.loads(r.stdout)["results"]] == ["a2"]


def test_dataset_file_duplicate_ids_refused(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("name: ds\ntarget: http://x\ntests:\n  - {id: a, input: i}\n"
                 "  - {id: a, input: j}\n")
    db = seed(tmp_path / "s.db", [rec("a")])
    for cmd in (["list"], ["export", "--dir", str(tmp_path / "o")]):
        r = eva("results", *cmd, "--db", db, "--dataset", "ds", "--dataset-file", str(p))
        assert r.returncode == 2 and "duplicate" in r.stderr.lower()


def test_export_then_import_round_trip(db, tmp_path):
    out = tmp_path / "out"
    r = eva("results", "export", "--db", db, "--dataset", "ds", "--dir", str(out),
            "--format", "json")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["dry_run"] is False and sum(f["records"] for f in rep["files"]) == 3
    assert len(list(out.rglob("*.jsonl"))) == 2

    db2 = tmp_path / "new.db"
    r = eva("results", "import", str(out), "--db", str(db2), "--format", "json")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["inserted"] == 3 and rep["conflicts"] == []
    r = eva("results", "list", "--db", str(db2), "--dataset", "ds", "--format", "json")
    assert len(json.loads(r.stdout)["results"]) == 3


def test_export_target_filter_and_dry_run(db, tmp_path):
    out = tmp_path / "o"
    r = eva("results", "export", "--db", db, "--dataset", "ds", "--target", "other:m",
            "--dir", str(out), "--dry-run", "--format", "json")
    assert r.returncode == 0
    rep = json.loads(r.stdout)
    assert rep["dry_run"] and [f["records"] for f in rep["files"]] == [1]
    assert not out.exists()


def test_import_dry_run_and_conflict_exit_1(db, tmp_path):
    out = tmp_path / "out"
    eva("results", "export", "--db", db, "--dataset", "ds", "--dir", str(out))
    other = seed(tmp_path / "o.db", [rec("a", passed=False, at="2026-06-01T00:00:00+00:00",
                                         run_id="later")])
    r = eva("results", "import", str(out), "--db", other, "--dry-run", "--format", "json")
    assert r.returncode == 1
    rep = json.loads(r.stdout)
    assert rep["dry_run"] and len(rep["conflicts"]) == 1
    # dry run changed nothing
    again = eva("results", "list", "--db", other, "--dataset", "ds", "--format", "json")
    assert [x["run_id"] for x in json.loads(again.stdout)["results"]] == ["later"]
    r = eva("results", "import", str(out), "--db", other, "--format", "json")
    assert r.returncode == 1
    again = eva("results", "list", "--db", other, "--dataset", "ds", "--target", "openai:m",
                "--format", "json")
    kept = {x["case"]: x["run_id"] for x in json.loads(again.stdout)["results"]}
    assert kept["a"] == "r1"  # earlier at wins


def test_import_malformed_exit_2_writes_nothing(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{nope\n")
    db = tmp_path / "s.db"
    r = eva("results", "import", str(bad), "--db", str(db))
    assert r.returncode == 2 and "bad.jsonl:1" in r.stderr
    r = eva("results", "import", str(tmp_path / "missing"), "--db", str(db))
    assert r.returncode == 2


def test_run_target_id_flag_and_reserved_name(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("name: d\ntarget: http://127.0.0.1:9/x\n"
                 "evaluators:\n  - {name: target}\ntests:\n  - {id: a, input: i}\n")
    r = eva("run", "--dataset", str(p), "--no-tui", cwd=tmp_path)
    assert r.returncode == 2
    assert "'target' is reserved" in (r.stdout + r.stderr)


def test_run_records_results_stable_across_base_url(tmp_path):
    from tests.fake_chat_server import FakeChatServer

    example = REPO / "docs/examples/local-openai-coding-reasoning.yaml"

    def reply(prompt):
        if "add(a, b)" in prompt:
            return {"content": "```python\ndef add(a, b):\n    return a + b\n```"}
        return {"content": "Final answer: 6"}

    for _ in range(2):  # two servers = two different base urls
        with FakeChatServer(reply) as srv:
            r = eva("run", "--dataset", str(example), "--no-tui",
                    "--base-url", f"{srv.url}/v1", "--model", "m", cwd=tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
    out = eva("results", "list", "--dataset", "local-coding-reasoning",
              "--format", "json", cwd=tmp_path)
    data = json.loads(out.stdout)["results"]
    assert {x["target_id"] for x in data} == {"openai:m"}
    assert len(data) == 2  # second run did not add or replace

    r = eva("run", "--dataset", str(example), "--no-tui", "--target-id", "pinned",
            "--base-url", "http://127.0.0.1:9/v1", "--model", "m", cwd=tmp_path)
    out = eva("results", "list", "--dataset", "local-coding-reasoning", "--target",
              "pinned", "--format", "json", cwd=tmp_path)
    # unreachable upstream: errors are not recorded
    assert json.loads(out.stdout) == {"results": []}

"""eva dataset check|lock|add and eva run on append-only datasets."""
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]
META = {"source": "hand", "licence": "CC0-1.0", "added": "2026-01-02", "origin": "handwritten"}


def eva(cwd, *args, stdin=None):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("EVA_JUDGE_MODEL", None)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=env, input=stdin,
    )


def case(cid, **kw):
    return {"id": cid, "input": f"q {cid}", "expected_output": "ok", "metadata": dict(META), **kw}


def make(tmp_path, cases, target="http://127.0.0.1:9/chat"):
    d = tmp_path / "pool"
    d.mkdir()
    ev = [{"name": "exact_match", "mode": "binary"}]
    (d / "dataset.yaml").write_text(yaml.safe_dump(
        {"name": "pool", "target": target, "append_only": True, "evaluators": ev}))
    (d / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))
    return d


def test_check_lock_flow_and_exit_codes(tmp_path):
    d = make(tmp_path, [case("a"), case("b")])
    r = eva(tmp_path, "dataset", "check", str(d))
    assert r.returncode == 3 and "not in the ledger" in r.stderr
    r = eva(tmp_path, "dataset", "lock", str(d), "--dry-run", "--format", "json")
    assert r.returncode == 0 and json.loads(r.stdout)["recorded"] == ["a", "b"]
    assert not (d / "dataset.lock.json").exists()
    assert eva(tmp_path, "dataset", "lock", str(d)).returncode == 0
    r = eva(tmp_path, "dataset", "check", str(d), "--format", "json")
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["ok"] and out["cases"] == 2 and out["problems"] == []


def test_edit_and_removal_exit_3(tmp_path):
    d = make(tmp_path, [case("a"), case("b")])
    eva(tmp_path, "dataset", "lock", str(d))
    (d / "cases.jsonl").write_text(json.dumps(case("a", input="edited")) + "\n")
    r = eva(tmp_path, "dataset", "check", str(d), "--format", "json")
    codes = sorted(p["code"] for p in json.loads(r.stdout)["problems"])
    assert r.returncode == 3 and codes == ["edited", "removed"]


def test_non_append_only_and_bad_input_exit_2(tmp_path):
    y = tmp_path / "s.yaml"
    y.write_text(yaml.safe_dump({"name": "s", "target": "http://x", "tests": [{"id": "a", "input": "q"}]}))
    assert eva(tmp_path, "dataset", "check", str(y)).returncode == 2
    assert eva(tmp_path, "dataset", "check", str(tmp_path / "nope")).returncode == 2
    d = make(tmp_path, [case("a")])
    assert eva(tmp_path, "dataset", "check", str(d), "--format", "xml").returncode == 2


def test_add_identical_noop_and_conflict(tmp_path):
    d = make(tmp_path, [case("a")])
    eva(tmp_path, "dataset", "lock", str(d))
    src = tmp_path / "new.jsonl"
    src.write_text(json.dumps(case("a")) + "\n" + json.dumps(case("b")) + "\n")
    r = eva(tmp_path, "dataset", "add", str(d), "--from", str(src), "--dry-run", "--format", "json")
    assert json.loads(r.stdout) | {} == {"ok": True, "dry_run": True, "added": ["b"],
                                         "skipped": ["a"], "problems": []}
    r = eva(tmp_path, "dataset", "add", str(d), "--from", str(src), "--format", "json")
    assert r.returncode == 0 and json.loads(r.stdout)["added"] == ["b"]
    again = eva(tmp_path, "dataset", "add", str(d), "--from", str(src), "--format", "json")
    assert again.returncode == 0 and json.loads(again.stdout)["added"] == []
    src.write_text(json.dumps(case("a", input="changed")) + "\n")
    r = eva(tmp_path, "dataset", "add", str(d), "--from", str(src))
    assert r.returncode == 3 and "different content" in r.stderr
    assert eva(tmp_path, "dataset", "check", str(d)).returncode == 0


def test_run_refuses_edited_dataset_and_skips_superseded(tmp_path):
    with FakeChatServer(lambda p: {"content": "ok"}) as srv:
        target = {"provider": "openai", "base_url": f"{srv.url}/v1", "model": "m"}
        d = make(tmp_path, [case("a"), case("a2", supersedes="a"), case("b")], target=target)
        r = eva(tmp_path, "run", "--dataset", str(d), "--no-tui")
        assert r.returncode == 3 and "not in the ledger" in r.stderr
        eva(tmp_path, "dataset", "lock", str(d))
        r = eva(tmp_path, "run", "--dataset", str(d), "--no-tui")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "a2 ·" in r.stdout and "b ·" in r.stdout and "a ·" not in r.stdout
        assert "Results: 2/2" in r.stdout and len(srv.requests) == 2
        (d / "cases.jsonl").write_text(
            (d / "cases.jsonl").read_text().replace('"q b"', '"q B"'))
        r = eva(tmp_path, "run", "--dataset", str(d), "--no-tui")
        assert r.returncode == 3 and "content changed" in r.stderr
        assert len(srv.requests) == 2

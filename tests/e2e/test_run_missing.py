"""`eva run --missing`: only the cases a target has no stored result for."""
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]


def eva(cwd, *args):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("EVA_JUDGE_MODEL", None)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=env,
    )


def dataset(tmp_path, n, cat=lambda i: None):
    lines = ["name: bench", "evaluators:", "  - {name: contains, substring: ok}", "tests:"]
    for i in range(1, n + 1):
        lines.append(f"  - id: c{i}\n    input: question {i}")
        if cat(i):
            lines.append(f"    metadata: {{category: {cat(i)}}}")
    p = tmp_path / "bench.yaml"
    p.write_text("\n".join(lines) + "\n")
    return p


def run(tmp_path, ds, srv, *extra, model="m"):
    return eva(tmp_path, "run", "--dataset", str(ds), "--no-tui", "--provider", "openai",
               "--base-url", f"{srv.url}/v1", "--model", model, *extra)


def asked(srv):
    return [r["body"]["messages"][-1]["content"] for r in srv.requests]


def ok(prompt):
    return {"content": "ok"}


def test_fresh_runs_all_second_none_then_only_appended(tmp_path):
    ds = dataset(tmp_path, 4)
    with FakeChatServer(ok) as srv:
        r1 = run(tmp_path, ds, srv, "--missing")
        assert r1.returncode == 0, r1.stdout + r1.stderr
        assert len(srv.requests) == 4
        r2 = run(tmp_path, ds, srv, "--missing")
        assert r2.returncode == 0, r2.stdout + r2.stderr
        assert len(srv.requests) == 4
        assert "Nothing to run" in r2.stdout and "bench" in r2.stdout
        dataset(tmp_path, 7)
        r3 = run(tmp_path, ds, srv, "--missing")
        assert r3.returncode == 0, r3.stdout + r3.stderr
        assert asked(srv)[4:] == ["question 5", "question 6", "question 7"]
        assert "c5" in r3.stdout and "c1 " not in r3.stdout


def test_upstream_error_case_is_retried(tmp_path):
    ds = dataset(tmp_path, 3)
    state = {"fail": True}

    def reply(prompt):
        if prompt == "question 2" and state["fail"]:
            return {"status": 500, "error": "boom"}
        return {"content": "ok"}

    with FakeChatServer(reply) as srv:
        r1 = run(tmp_path, ds, srv, "--missing")
        assert r1.returncode == 1, r1.stdout + r1.stderr
        assert len(srv.requests) == 3
        state["fail"] = False
        r2 = run(tmp_path, ds, srv, "--missing")
        assert r2.returncode == 0, r2.stdout + r2.stderr
        assert asked(srv)[3:] == ["question 2"]


def test_another_target_id_runs_everything(tmp_path):
    ds = dataset(tmp_path, 2)
    with FakeChatServer(ok) as srv:
        run(tmp_path, ds, srv, "--missing", model="a")
        assert len(srv.requests) == 2
        run(tmp_path, ds, srv, "--missing", model="b")
        assert len(srv.requests) == 4
        run(tmp_path, ds, srv, "--missing", "--target-id", "custom", model="a")
        assert len(srv.requests) == 6
        run(tmp_path, ds, srv, "--missing", "--target-id", "custom", model="a")
        assert len(srv.requests) == 6


def test_dry_run_lists_ids_and_calls_nothing(tmp_path):
    ds = dataset(tmp_path, 3)
    with FakeChatServer(ok) as srv:
        r = run(tmp_path, ds, srv, "--missing", "--dry-run")
        assert r.returncode == 0, r.stdout + r.stderr
        assert [l.strip() for l in r.stdout.splitlines() if l.startswith("  ")] == ["c1", "c2", "c3"]
        assert srv.requests == []
        j = run(tmp_path, ds, srv, "--missing", "--dry-run", "--format", "json")
        assert json.loads(j.stdout) == {
            "dataset": "bench", "target_id": "openai:m", "dry_run": True,
            "missing_only": True, "scored": 3, "missing": 3,
            "selected": ["c1", "c2", "c3"],
        }
        assert srv.requests == []
        # dry-run stored nothing: a real run still has everything to do
        run(tmp_path, ds, srv, "--missing")
        assert len(srv.requests) == 3


def test_dry_run_without_missing_lists_all_scored_cases(tmp_path):
    ds = dataset(tmp_path, 2)
    with FakeChatServer(ok) as srv:
        run(tmp_path, ds, srv)
        n = len(srv.requests)
        j = run(tmp_path, ds, srv, "--dry-run", "--format", "json")
        out = json.loads(j.stdout)
        assert out["selected"] == ["c1", "c2"] and out["missing_only"] is False
        assert "missing" not in out
        assert len(srv.requests) == n


def test_nothing_missing_json(tmp_path):
    ds = dataset(tmp_path, 2)
    with FakeChatServer(ok) as srv:
        run(tmp_path, ds, srv)
        j = run(tmp_path, ds, srv, "--missing", "--format", "json")
        assert j.returncode == 0, j.stdout + j.stderr
        assert json.loads(j.stdout) == {
            "dataset": "bench", "target_id": "openai:m", "dry_run": False,
            "missing_only": True, "scored": 2, "missing": 0, "selected": [],
        }
        assert len(srv.requests) == 2


def test_missing_run_json_is_a_run(tmp_path):
    ds = dataset(tmp_path, 2)
    with FakeChatServer(ok) as srv:
        j = run(tmp_path, ds, srv, "--missing", "--format", "json")
        assert j.returncode == 0, j.stdout + j.stderr
        body = json.loads(j.stdout)
        assert body["dataset"] == "bench" and len(body["results"]) == 2


def test_category_and_limit(tmp_path):
    ds = dataset(tmp_path, 6, cat=lambda i: "math" if i % 2 else "code")
    with FakeChatServer(ok) as srv:
        r = run(tmp_path, ds, srv, "--missing", "--category", "math", "--limit", "2")
        assert r.returncode == 0, r.stdout + r.stderr
        assert asked(srv) == ["question 1", "question 3"]
        r = run(tmp_path, ds, srv, "--missing", "--category", "math", "--dry-run", "--format", "json")
        out = json.loads(r.stdout)
        assert out["selected"] == ["c5"] and out["missing"] == 1 and out["scored"] == 6
        r = run(tmp_path, ds, srv, "--missing", "--category", "nope")
        assert r.returncode == 0 and "Nothing to run" in r.stdout
        assert len(srv.requests) == 2


def test_flag_misuse_exits_2(tmp_path):
    ds = dataset(tmp_path, 1)
    with FakeChatServer(ok) as srv:
        for extra in (["--category", "x"], ["--limit", "1"],
                      ["--missing", "--limit", "0"]):
            r = run(tmp_path, ds, srv, *extra)
            assert r.returncode == 2, (extra, r.stdout + r.stderr)
        c = eva(tmp_path, "run", "--contract", "c.yaml", "--input", "-", "--missing")
        assert c.returncode == 2
        c = eva(tmp_path, "run", "--contract", "c.yaml", "--input", "-", "--dry-run")
        assert c.returncode == 2
        assert srv.requests == []

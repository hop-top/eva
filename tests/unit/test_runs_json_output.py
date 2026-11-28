"""`eva runs list|show --format json`: machine-readable output on stdout."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.models import Invocation, Result, Run, Score, UsageRecord
from core.storage import SqliteStorage

REPO = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def eva(*args):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=REPO, env=env,
    )


def _result(test_id, evaluator, value, reason=None):
    return Result(
        test_id=test_id, evaluator=evaluator,
        score=Score(value=value, reason=reason), mode="binary", duration_ms=5,
    )


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "state.db"
    storage = SqliteStorage(db_url=f"sqlite:///{path}")
    storage.save_run(Run(
        run_id="run-a", dataset="ds", target="openai:m@http://x/v1",
        results=[
            _result("c1", "contains", 1.0),
            _result("c2", "contains", 0.0, "missing 'foo'"),
        ],
        started_at=T0, duration_ms=120, passed=False,
    ))
    storage.save_run(Run(
        run_id="run-b", dataset="other", target="http://t", results=[],
        started_at=T0.replace(hour=9), duration_ms=1, passed=True,
    ))
    storage.save_invocation(
        Invocation(
            invocation_id="inv-1", run_id="run-a", source="offline_run",
            dataset="ds", test_id="c1", target="openai:m@http://x/v1",
            provider="openai", model="m", started_at=T0, duration_ms=50,
            status="pass",
        ),
        evaluator_results=[], artifacts=[],
    )
    storage.save_usage_record(UsageRecord(
        usage_id="u1", invocation_id="inv-1", scope="agent", model="m",
        prompt_tokens=7, completion_tokens=3, latency_ms=40,
    ))
    return str(path)


def test_list_json_is_object_with_runs(db):
    r = eva("runs", "list", "--db", db, "--format", "json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert isinstance(data, dict)
    runs = {x["run_id"]: x for x in data["runs"]}
    assert set(runs) == {"run-a", "run-b"}
    a = runs["run-a"]
    assert a["dataset"] == "ds"
    assert a["target"] == "openai:m@http://x/v1"
    assert a["status"] == "fail" and a["passed"] is False
    assert a["started_at"].startswith("2026-01-02T03:04:05")
    assert a["duration_ms"] == 120
    assert a["summary"] == {"passed": 1, "total": 2}
    assert runs["run-b"]["status"] == "pass"
    assert runs["run-b"]["summary"] == {"passed": 0, "total": 0}


def test_list_json_honours_filters(db):
    r = eva("runs", "list", "--db", db, "--format", "json", "--dataset", "other")
    assert [x["run_id"] for x in json.loads(r.stdout)["runs"]] == ["run-b"]


def test_list_json_empty_is_valid_json(tmp_path):
    r = eva("runs", "list", "--db", str(tmp_path / "e.db"), "--format", "json")
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"runs": []}


def test_show_json_shape(db):
    r = eva("runs", "show", "--db", db, "--run-id", "run-a", "--format", "json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert isinstance(data, dict)
    run = data["run"]
    assert run["run_id"] == "run-a" and run["status"] == "fail"
    assert run["summary"] == {"passed": 1, "total": 2}
    assert run["duration_ms"] == 120
    [inv] = data["invocations"]
    assert inv["invocation_id"] == "inv-1"
    assert inv["test_id"] == "c1"
    assert inv["provider"] == "openai" and inv["model"] == "m"
    assert inv["status"] == "pass" and inv["duration_ms"] == 50
    assert inv["model_latency_ms"] == 40
    assert inv["prompt_tokens"] == 7 and inv["completion_tokens"] == 3
    assert inv["contract_name"] is None
    res = {(x["test_id"], x["evaluator"]): x for x in data["results"]}
    assert res[("c1", "contains")]["passed"] is True
    bad = res[("c2", "contains")]
    assert bad["passed"] is False and bad["score"] == 0.0
    assert bad["reason"] == "missing 'foo'"


def test_show_json_without_invocations(db):
    r = eva("runs", "show", "--db", db, "--run-id", "run-b", "--format", "json")
    data = json.loads(r.stdout)
    assert data["invocations"] == [] and data["results"] == []


def test_show_json_not_found_error_on_stderr(db):
    r = eva("runs", "show", "--db", db, "--run-id", "nope", "--format", "json")
    assert r.returncode == 1
    assert r.stdout == ""
    assert "nope" in r.stderr


@pytest.mark.parametrize("cmd", [["list"], ["show", "--run-id", "run-a"]])
def test_invalid_format_exits_2(db, cmd):
    r = eva("runs", *cmd, "--db", db, "--format", "xml")
    assert r.returncode == 2
    assert r.stdout == ""
    assert "--format" in r.stderr and "xml" in r.stderr


@pytest.mark.parametrize("cmd", [["list"], ["show", "--run-id", "run-a"]])
def test_text_format_is_default_and_explicit(db, cmd):
    default = eva("runs", *cmd, "--db", db)
    text = eva("runs", *cmd, "--db", db, "--format", "text")
    assert default.returncode == text.returncode == 0
    assert default.stdout == text.stdout
    assert "run-a" in default.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(default.stdout)


def test_show_json_carries_per_category_figures(db):
    r = eva("runs", "show", "--db", db, "--run-id", "run-a", "--format", "json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert isinstance(data["categories"], dict)
    assert data["since"] is None
    [case] = data["cases"]
    assert case["test_id"] == "c1" and case["scored"] is False

    r = eva("runs", "show", "--db", db, "--run-id", "run-a", "--format", "json",
            "--since", "2026-01-01")
    assert r.returncode == 0, r.stderr
    since = json.loads(r.stdout)["since"]
    assert since == {"since": "2026-01-01", "passed": 0, "total": 0, "excluded": 0}


def test_show_json_bad_since_exits_2(db):
    r = eva("runs", "show", "--db", db, "--run-id", "run-a", "--format", "json",
            "--since", "not-a-date")
    assert r.returncode == 2

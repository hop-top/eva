# tests/e2e/test_compare_command.py
"""E2E tests for `eva compare`: model, cost, invocation and per-evaluator diffs."""
import os
import subprocess
import sys
import uuid
import pytest

pytestmark = pytest.mark.e2e


def run_eva(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.main"] + list(args),
        capture_output=True,
        text=True,
        env={**os.environ, "COLUMNS": "200", "NO_COLOR": "1"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_run(
    db_path: str,
    *,
    run_id: str,
    dataset: str = "ds",
    target: str = "http://localhost:9999",
    passed: bool = True,
    model: str = "gpt-4",
    evaluators: list[dict] | None = None,
    cost: float = 0.001,
) -> None:
    """Insert a Run + one Invocation + UsageRecord + optional EvaluatorResults."""
    from core.storage import SqliteStorage
    from core.models import EvaluatorResult, Invocation, Run, UsageRecord
    from datetime import datetime, timezone

    storage = SqliteStorage(db_url=f"sqlite:///{db_path}")

    # Save Run record
    run = Run(
        run_id=run_id,
        dataset=dataset,
        target=target,
        started_at=datetime.now(tz=timezone.utc),
        passed=passed,
    )
    storage.save_run(run)

    # Save Invocation
    inv_id = str(uuid.uuid4())
    invocation = Invocation(
        invocation_id=inv_id,
        run_id=run_id,
        source="offline_run",
        dataset=dataset,
        target=target,
        model=model,
        status="pass" if passed else "fail",
        started_at=datetime.now(tz=timezone.utc),
    )
    ers = []
    if evaluators:
        for ev in evaluators:
            ers.append(
                EvaluatorResult(
                    evaluator_result_id=str(uuid.uuid4()),
                    invocation_id=inv_id,
                    evaluator=ev["name"],
                    score_value=ev.get("score", 1.0),
                    passed=ev.get("passed", True),
                )
            )
    storage.save_invocation(invocation, ers, [])

    # Save UsageRecord
    usage = UsageRecord(
        usage_id=str(uuid.uuid4()),
        invocation_id=inv_id,
        scope="agent",
        model=model,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=cost,
    )
    storage.save_usage_record(usage)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _row(out: str, label: str) -> list[str]:
    """Cells of the first table row starting with *label*."""
    for line in out.splitlines():
        cells = [c.strip() for c in line.split("\u2502") if c.strip()]
        if cells and cells[0] == label:
            return cells
    raise AssertionError(f"no row {label!r} in:\n{out}")


def _compare(tmp_path, left: dict, right: dict):
    db = str(tmp_path / "eva.db")
    _seed_run(db, run_id="left", **left)
    _seed_run(db, run_id="right", **right)
    return run_eva("compare", "--left", "left", "--right", "right", "--db", db)


def test_compare_summary_rows_model_invocations_cost(tmp_path):
    r = _compare(tmp_path, dict(model="gpt-4", cost=0.010), dict(model="gpt-4o", cost=0.005))
    assert r.returncode == 0, r.stderr
    assert _row(r.stdout, "Model(s)")[1:3] == ["gpt-4", "gpt-4o"]
    assert _row(r.stdout, "Invocations")[1:] == ["1", "1", "+0"]
    assert _row(r.stdout, "Total cost (USD)")[1:] == [
        "$0.010000", "$0.005000", "$-0.005000"]


def test_compare_pass_rate_diff_per_evaluator(tmp_path):
    r = _compare(
        tmp_path,
        dict(model="gpt-4", evaluators=[{"name": "tone_check", "score": 0.0, "passed": False}]),
        dict(model="gpt-4o", evaluators=[{"name": "tone_check", "score": 1.0, "passed": True}]),
    )
    assert r.returncode == 0, r.stderr
    assert "Per-Evaluator Pass Rate" in r.stdout
    assert _row(r.stdout, "tone_check")[1:] == ["0.0%", "100.0%", "+100.0%"]


def test_compare_run_against_itself_has_zero_diffs(tmp_path):
    db = str(tmp_path / "eva.db")
    _seed_run(db, run_id="same", model="gpt-4", cost=0.005)
    r = run_eva("compare", "--left", "same", "--right", "same", "--db", db)
    assert r.returncode == 0, r.stderr
    assert _row(r.stdout, "Total cost (USD)")[1:] == [
        "$0.005000", "$0.005000", "$+0.000000"]


@pytest.mark.parametrize("missing", ["left", "right"])
def test_compare_unknown_run_id_exits_1_naming_it(tmp_path, missing):
    db = str(tmp_path / "eva.db")
    _seed_run(db, run_id="known", model="gpt-4")
    pair = ("nope-123", "known") if missing == "left" else ("known", "nope-123")
    r = run_eva("compare", "--left", pair[0], "--right", pair[1], "--db", db)
    assert r.returncode == 1
    assert "not found" in r.stdout and "nope-123" in r.stdout

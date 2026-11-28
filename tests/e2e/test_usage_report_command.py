# tests/e2e/test_usage_report_command.py
"""E2E tests for `eva usage report`: token totals, cost by model, filters."""
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone

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

def _seed_invocation_with_usage(
    db_path: str,
    *,
    dataset: str = "ds",
    target: str = "http://localhost:9999",
    model: str = "gpt-4",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    total_tokens: int = 150,
    cost: float = 0.001,
) -> str:
    """Insert Invocation + UsageRecord; return invocation_id."""
    from core.storage import SqliteStorage
    from core.models import Invocation, UsageRecord

    storage = SqliteStorage(db_url=f"sqlite:///{db_path}")
    inv_id = str(uuid.uuid4())

    invocation = Invocation(
        invocation_id=inv_id,
        source="offline_run",
        dataset=dataset,
        target=target,
        model=model,
        status="pass",
        started_at=datetime.now(tz=timezone.utc),
    )
    storage.save_invocation(invocation, [], [])

    usage = UsageRecord(
        usage_id=str(uuid.uuid4()),
        invocation_id=inv_id,
        scope="agent",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
    )
    storage.save_usage_record(usage)
    return inv_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _figures(out: str) -> dict[str, str]:
    """Totals block as {label: value}, e.g. {"Total tokens": "450"}."""
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r"^  ([A-Za-z. ()]+?):\s+\$?\s*([\d,.]+)$", out, re.M)
    }


def _model_row(out: str, model: str) -> list[str]:
    for line in out.splitlines():
        cells = [c.strip() for c in line.split("\u2502") if c.strip()]
        if cells and cells[0] == model:
            return cells[1:]
    raise AssertionError(f"no row for {model!r} in:\n{out}")


def test_usage_report_totals_sum_across_invocations(tmp_path):
    db = str(tmp_path / "eva.db")
    _seed_invocation_with_usage(
        db, prompt_tokens=100, completion_tokens=50, total_tokens=150, cost=0.001)
    _seed_invocation_with_usage(
        db, prompt_tokens=200, completion_tokens=100, total_tokens=300, cost=0.002)

    r = run_eva("usage", "report", "--db", db)
    assert r.returncode == 0, r.stderr
    assert "(2 invocations)" in r.stdout
    assert _figures(r.stdout) == {
        "Prompt tokens": "300", "Completion tokens": "150",
        "Total tokens": "450", "Est. cost (USD)": "0.003000"}


def test_usage_report_breaks_down_cost_by_model(tmp_path):
    db = str(tmp_path / "eva.db")
    _seed_invocation_with_usage(db, model="gpt-4", prompt_tokens=10, completion_tokens=5,
                                total_tokens=15, cost=0.005)
    _seed_invocation_with_usage(db, model="model-b", prompt_tokens=20,
                                completion_tokens=7, total_tokens=27, cost=0.001)

    r = run_eva("usage", "report", "--db", db)
    assert r.returncode == 0, r.stderr
    assert _model_row(r.stdout, "gpt-4") == ["10", "5", "15", "$0.005000"]
    assert _model_row(r.stdout, "model-b") == ["20", "7", "27", "$0.001000"]


def test_usage_report_dataset_filter_scopes_totals(tmp_path):
    db = str(tmp_path / "eva.db")
    _seed_invocation_with_usage(db, dataset="suite_a", cost=0.010)
    _seed_invocation_with_usage(db, dataset="suite_b", cost=0.002)

    r = run_eva("usage", "report", "--dataset", "suite_a", "--db", db)
    assert r.returncode == 0, r.stderr
    assert "(1 invocations)" in r.stdout and "Dataset: suite_a" in r.stdout
    assert _figures(r.stdout)["Est. cost (USD)"] == "0.010000"


def test_usage_report_target_filter_scopes_totals(tmp_path):
    db = str(tmp_path / "eva.db")
    _seed_invocation_with_usage(db, target="http://api-a.example.com", cost=0.007)
    _seed_invocation_with_usage(db, target="http://api-b.example.com", cost=0.003)

    r = run_eva("usage", "report", "--target", "http://api-a.example.com", "--db", db)
    assert r.returncode == 0, r.stderr
    assert "(1 invocations)" in r.stdout
    assert _figures(r.stdout)["Est. cost (USD)"] == "0.007000"


def test_usage_report_empty_db_and_empty_filter_report_zeros(tmp_path):
    from core.storage import SqliteStorage

    empty = str(tmp_path / "empty.db")
    SqliteStorage(db_url=f"sqlite:///{empty}")
    r = run_eva("usage", "report", "--db", empty)
    assert r.returncode == 0, r.stderr
    assert "(0 invocations)" in r.stdout
    assert _figures(r.stdout)["Total tokens"] == "0"

    db = str(tmp_path / "eva.db")
    _seed_invocation_with_usage(db, dataset="real_suite", cost=0.005)
    r = run_eva("usage", "report", "--dataset", "nonexistent_suite", "--db", db)
    assert r.returncode == 0, r.stderr
    assert "(0 invocations)" in r.stdout
    assert _figures(r.stdout)["Est. cost (USD)"] == "0.000000"

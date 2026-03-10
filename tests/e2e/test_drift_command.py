# tests/e2e/test_drift_command.py
"""E2E tests for `eva drift report` CLI command — T-0056."""
import subprocess
import sys

import pytest

pytestmark = pytest.mark.e2e


def run_eva(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.main"] + list(args),
        capture_output=True,
        text=True,
        cwd=None,  # relies on PYTHONPATH / installed package
    )


def test_drift_report_help_exits_zero():
    # US-011: As Jordan, I want to generate a drift report with `eva drift report` so that I
    # can document when model behaviour deviates from the approved baseline.
    result = run_eva("drift", "report", "--help")
    assert result.returncode == 0
    assert "dataset" in result.stdout.lower() or "help" in result.stdout.lower()


def test_drift_report_missing_dataset_exits_nonzero():
    # US-015: As Jordan, I want `eva drift report` to exit non-zero when no baseline runs exist
    # so that missing-data gaps are surfaced rather than silently ignored.
    result = run_eva("drift", "report")
    assert result.returncode != 0


def test_drift_report_empty_db_shows_no_runs_message(tmp_path):
    # US-012: As Jordan, I want drift reports to be stored in a persistent DB so that I have a
    # historical record for audits.
    """Empty SQLite DB → exit 0 with 'No runs found' message."""
    result = run_eva(
        "drift",
        "report",
        "--dataset",
        "test_ds",
        "--target",
        "http://example.com",
        "--db",
        str(tmp_path / "eva.db"),
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "test_ds" in combined or "No runs found" in combined

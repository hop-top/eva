# tests/e2e/test_contract_diff.py
import subprocess
import sys
from pathlib import Path

CONTRACTS = Path("tests/fixtures/contracts")


def run_eva(*args):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
    )


def test_no_regression_exits_zero():
    result = run_eva(
        "contract", "diff",
        str(CONTRACTS / "v1.yaml"),
        str(CONTRACTS / "v2_no_regression.yaml"),
    )
    assert result.returncode == 0


def test_regression_exits_one():
    result = run_eva(
        "contract", "diff",
        str(CONTRACTS / "v1.yaml"),
        str(CONTRACTS / "v2_regression.yaml"),
    )
    assert result.returncode == 1
    out = result.stdout.lower()
    assert "regression" in out


def test_identical_contracts_exit_zero():
    result = run_eva(
        "contract", "diff",
        str(CONTRACTS / "v1.yaml"),
        str(CONTRACTS / "v1.yaml"),
    )
    assert result.returncode == 0
    assert "no changes" in result.stdout.lower()


def test_missing_file_exits_one():
    result = run_eva(
        "contract", "diff",
        str(CONTRACTS / "v1.yaml"),
        str(CONTRACTS / "nonexistent.yaml"),
    )
    assert result.returncode == 1

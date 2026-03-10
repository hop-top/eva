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
    # US-005: As Alex, I want to diff two contract versions with `eva contract diff` so that I
    # can see breaking changes introduced by a prompt update.
    # US-014: As Jordan, I want contract YAML files to be version-controlled and diffable so
    # that every change to an approved output contract is trackable.
    result = run_eva(
        "contract", "diff",
        str(CONTRACTS / "v1.yaml"),
        str(CONTRACTS / "v2_no_regression.yaml"),
    )
    assert result.returncode == 0


def test_regression_exits_one():
    # US-005: As Alex, I want to diff two contract versions with `eva contract diff` so that I
    # can see breaking changes introduced by a prompt update.
    # US-014: As Jordan, I want contract YAML files to be version-controlled and diffable so
    # that every change to an approved output contract is trackable.
    result = run_eva(
        "contract", "diff",
        str(CONTRACTS / "v1.yaml"),
        str(CONTRACTS / "v2_regression.yaml"),
    )
    assert result.returncode == 1
    out = result.stdout.lower()
    assert "regression" in out


def test_identical_contracts_exit_zero():
    # US-005: As Alex, I want to diff two contract versions with `eva contract diff` so that I
    # can see breaking changes introduced by a prompt update.
    result = run_eva(
        "contract", "diff",
        str(CONTRACTS / "v1.yaml"),
        str(CONTRACTS / "v1.yaml"),
    )
    assert result.returncode == 0
    assert "no changes" in result.stdout.lower()


def test_missing_file_exits_one():
    # US-005: As Alex, I want to diff two contract versions with `eva contract diff` so that I
    # can see breaking changes introduced by a prompt update.
    result = run_eva(
        "contract", "diff",
        str(CONTRACTS / "v1.yaml"),
        str(CONTRACTS / "nonexistent.yaml"),
    )
    assert result.returncode == 1

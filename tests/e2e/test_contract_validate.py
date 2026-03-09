# tests/e2e/test_contract_validate.py
import subprocess
import sys
from pathlib import Path

FIXTURES = Path("tests/fixtures/contracts")


def run_eva(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_validate_valid_contract():
    result = run_eva("contract", "validate", str(FIXTURES / "valid.yaml"))
    assert result.returncode == 0
    assert "valid" in result.stdout.lower()


def test_validate_invalid_contract():
    result = run_eva("contract", "validate", str(FIXTURES / "invalid_missing_name.yaml"))
    assert result.returncode == 1
    assert "error" in result.stdout.lower() or "error" in result.stderr.lower()


def test_validate_missing_file():
    result = run_eva("contract", "validate", "nonexistent.yaml")
    assert result.returncode == 1

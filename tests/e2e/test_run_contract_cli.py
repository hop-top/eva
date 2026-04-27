# tests/e2e/test_run_contract_cli.py
"""End-to-end: `eva run --contract --input` via subprocess."""
import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def run_eva(*args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        input=stdin,
    )


def _write(path: Path, body: str) -> Path:
    path.write_text(dedent(body).lstrip())
    return path


def test_cli_run_contract_pass(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: greet
        provider: noop
        evaluators:
          - name: contains
            substring: hi
        """,
    )
    inp = _write(tmp_path / "in.txt", "hi mom")

    result = run_eva(
        "run", "--contract", str(contract), "--input", str(inp), "--format", "json"
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["evaluators"][0]["name"] == "contains"


def test_cli_run_contract_fail_emits_json_on_stderr(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: greet
        provider: noop
        evaluators:
          - name: contains
            substring: ABSENT
        """,
    )
    inp = _write(tmp_path / "in.txt", "nothing")

    result = run_eva(
        "run", "--contract", str(contract), "--input", str(inp), "--format", "json"
    )
    assert result.returncode == 1
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["passed"] is False
    assert payload["evaluators"][0]["passed"] is False


def test_cli_run_contract_text_mode(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: greet
        provider: noop
        evaluators:
          - name: regex
            pattern: 'hello'
        """,
    )
    inp = _write(tmp_path / "in.txt", "well, hello!")

    result = run_eva(
        "run", "--contract", str(contract), "--input", str(inp), "--format", "text"
    )
    assert result.returncode == 0
    assert "PASSED" in result.stdout
    assert "regex" in result.stdout


def test_cli_run_contract_stdin_input(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: greet
        provider: noop
        evaluators:
          - name: contains
            substring: piped
        """,
    )
    result = run_eva(
        "run",
        "--contract",
        str(contract),
        "--input",
        "-",
        "--format",
        "json",
        stdin="this is piped",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_cli_run_contract_malformed_yaml_returns_two(tmp_path):
    contract = tmp_path / "broken.yaml"
    contract.write_text("name: x\n  evaluators: [bad indent\n")
    inp = _write(tmp_path / "in.txt", "x")

    result = run_eva(
        "run", "--contract", str(contract), "--input", str(inp), "--format", "json"
    )
    assert result.returncode == 2
    assert "error" in result.stderr.lower()


def test_cli_run_contract_missing_input_returns_two(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: x
        provider: noop
        evaluators: []
        """,
    )
    result = run_eva(
        "run",
        "--contract",
        str(contract),
        "--input",
        str(tmp_path / "absent.txt"),
        "--format",
        "json",
    )
    assert result.returncode == 2


def test_cli_run_contract_requires_input_with_contract(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: x
        provider: noop
        evaluators: []
        """,
    )
    # Missing --input
    result = run_eva("run", "--contract", str(contract))
    assert result.returncode == 2
    assert "--input" in result.stdout or "--input" in result.stderr


def test_cli_run_contract_mutex_with_dataset(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: x
        provider: noop
        evaluators: []
        """,
    )
    inp = _write(tmp_path / "in.txt", "x")
    # Combining the two modes is rejected
    result = run_eva(
        "run",
        "--contract",
        str(contract),
        "--input",
        str(inp),
        "--dataset",
        "some.yaml",
    )
    assert result.returncode == 2


def test_cli_run_dataset_mode_still_requires_dataset():
    """Regression: `eva run` with no flags must error cleanly, not crash."""
    result = run_eva("run")
    assert result.returncode == 2
    assert "--dataset" in result.stdout or "--dataset" in result.stderr

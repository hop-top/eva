# tests/unit/test_run_contract.py
"""Unit tests for the standalone `eva run --contract --input` runner."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from cli.run_contract import (
    EXIT_BAD_INPUT,
    EXIT_EVAL_FAIL,
    EXIT_PASS,
    evaluate_contract,
    run_contract_cli,
)


def _write(path: Path, body: str) -> Path:
    path.write_text(dedent(body).lstrip())
    return path


def test_happy_path_single_passing_evaluator(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: greet
        provider: noop
        evaluators:
          - name: contains
            substring: hello
            mode: binary
        """,
    )
    report = evaluate_contract(contract, "well, hello there")
    assert report.passed is True
    assert len(report.outcomes) == 1
    assert report.outcomes[0].name == "contains"
    assert report.outcomes[0].score == 1.0


def test_failure_reports_violation(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: greet
        provider: noop
        evaluators:
          - name: contains
            substring: REQUIRED
            mode: binary
        """,
    )
    report = evaluate_contract(contract, "no match")
    assert report.passed is False
    assert report.outcomes[0].passed is False
    assert "REQUIRED" in (report.outcomes[0].reason or "")


def test_multiple_evaluators_all_pass_then_one_fails(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: multi
        provider: noop
        evaluators:
          - name: contains
            substring: ok
          - name: regex
            pattern: '[0-9]+'
          - name: contains
            substring: NOPE
        """,
    )
    report = evaluate_contract(contract, "ok 123")
    assert report.passed is False
    # 3 outcomes — last one fails
    assert [o.passed for o in report.outcomes] == [True, True, False]


def test_warn_mode_never_fails(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: warn
        provider: noop
        evaluators:
          - name: contains
            substring: NOPE
            mode: warn
        """,
    )
    report = evaluate_contract(contract, "no match")
    assert report.passed is True
    assert report.outcomes[0].passed is True
    assert report.outcomes[0].score == 0.0


def test_unknown_evaluator_is_skipped(tmp_path):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: skip
        provider: noop
        evaluators:
          - name: not_a_real_evaluator
          - name: contains
            substring: ok
        """,
    )
    report = evaluate_contract(contract, "ok")
    assert report.passed is True
    assert report.skipped == ["not_a_real_evaluator"]
    assert len(report.outcomes) == 1


def test_malformed_yaml_raises(tmp_path):
    contract = tmp_path / "broken.yaml"
    contract.write_text("name: x\n  evaluators: [bad indent\n")
    with pytest.raises(ValueError, match="Malformed contract YAML"):
        evaluate_contract(contract, "anything")


def test_missing_name_raises(tmp_path):
    contract = _write(tmp_path / "c.yaml", "provider: noop\nevaluators: []\n")
    with pytest.raises(ValueError, match="must have a 'name'"):
        evaluate_contract(contract, "anything")


def test_missing_contract_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        evaluate_contract(tmp_path / "absent.yaml", "x")


def test_cli_happy_path_returns_zero(tmp_path, capsys):
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
    inp = tmp_path / "in.txt"
    inp.write_text("hi there")

    code = run_contract_cli(
        contract=contract, input_path=str(inp), fmt="json", quiet=False
    )
    assert code == EXIT_PASS
    captured = capsys.readouterr()
    # JSON on success goes to stdout
    assert '"passed": true' in captured.out


def test_cli_failure_returns_one_with_json_on_stderr(tmp_path, capsys):
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
    inp = tmp_path / "in.txt"
    inp.write_text("nothing here")

    code = run_contract_cli(
        contract=contract, input_path=str(inp), fmt="json", quiet=False
    )
    assert code == EXIT_EVAL_FAIL
    captured = capsys.readouterr()
    assert '"passed": false' in captured.err
    assert '"name": "contains"' in captured.err
    # On failure, stdout stays clean for CI piping
    assert captured.out == ""


def test_cli_text_mode_human_output(tmp_path, capsys):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: greet
        provider: noop
        evaluators:
          - name: contains
            substring: ok
        """,
    )
    inp = tmp_path / "in.txt"
    inp.write_text("ok cool")

    code = run_contract_cli(
        contract=contract, input_path=str(inp), fmt="text", quiet=False
    )
    assert code == EXIT_PASS
    captured = capsys.readouterr()
    assert "PASSED" in captured.out
    assert "contains" in captured.out


def test_cli_quiet_suppresses_passing_evaluators(tmp_path, capsys):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: mix
        provider: noop
        evaluators:
          - name: contains
            substring: ok
          - name: contains
            substring: MISSING
        """,
    )
    inp = tmp_path / "in.txt"
    inp.write_text("ok")

    code = run_contract_cli(
        contract=contract, input_path=str(inp), fmt="text", quiet=True
    )
    assert code == EXIT_EVAL_FAIL
    captured = capsys.readouterr()
    # Failing evaluator must still appear (on stderr because overall failed)
    assert "MISSING" in captured.err
    # Passing eval line should NOT include the per-eval passing detail row
    assert "[PASS] contains" not in captured.err


def test_cli_input_from_stdin(tmp_path, monkeypatch, capsys):
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
    monkeypatch.setattr("sys.stdin", io.StringIO("piped data"))
    code = run_contract_cli(
        contract=contract, input_path="-", fmt="json", quiet=False
    )
    assert code == EXIT_PASS


def test_cli_missing_input_file_returns_two(tmp_path, capsys):
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: x
        provider: noop
        evaluators: []
        """,
    )
    code = run_contract_cli(
        contract=contract,
        input_path=str(tmp_path / "absent.txt"),
        fmt="json",
        quiet=False,
    )
    assert code == EXIT_BAD_INPUT


def test_cli_malformed_contract_returns_two(tmp_path, capsys):
    contract = tmp_path / "broken.yaml"
    contract.write_text("name: x\n  evaluators: [bad indent\n")
    inp = tmp_path / "in.txt"
    inp.write_text("anything")
    code = run_contract_cli(
        contract=contract, input_path=str(inp), fmt="json", quiet=False
    )
    assert code == EXIT_BAD_INPUT


def test_cli_missing_contract_file_returns_two(tmp_path, capsys):
    inp = tmp_path / "in.txt"
    inp.write_text("x")
    code = run_contract_cli(
        contract=tmp_path / "absent.yaml",
        input_path=str(inp),
        fmt="json",
        quiet=False,
    )
    assert code == EXIT_BAD_INPUT


def test_cli_binary_input_file_returns_two(tmp_path, capsys):
    """Binary --input file must exit EXIT_BAD_INPUT, not crash with traceback."""
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: x
        provider: noop
        evaluators: []
        """,
    )
    binary = tmp_path / "binary.bin"
    # Bytes that are not valid UTF-8 (lone continuation byte, PNG-ish header).
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\xfd\x00\x80\x81\x82")

    code = run_contract_cli(
        contract=contract, input_path=str(binary), fmt="json", quiet=False
    )
    assert code == EXIT_BAD_INPUT
    captured = capsys.readouterr()
    # Error must mention the offending file path so users can find it.
    assert str(binary) in captured.err
    assert "UTF-8" in captured.err


def test_cli_binary_stdin_returns_two(tmp_path, monkeypatch, capsys):
    """Binary input on stdin must exit EXIT_BAD_INPUT, not crash."""
    contract = _write(
        tmp_path / "c.yaml",
        """
        name: x
        provider: noop
        evaluators: []
        """,
    )

    class _BinaryStdin:
        def read(self):
            # Simulate the OS-level decode failure that real binary stdin
            # produces when the parent process pipes non-UTF-8 bytes.
            raise UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")

    monkeypatch.setattr("sys.stdin", _BinaryStdin())
    code = run_contract_cli(
        contract=contract, input_path="-", fmt="json", quiet=False
    )
    assert code == EXIT_BAD_INPUT
    captured = capsys.readouterr()
    assert "stdin" in captured.err
    assert "UTF-8" in captured.err


def test_load_input_binary_raises_valueerror(tmp_path):
    """Unit-level: _load_input wraps UnicodeDecodeError in ValueError."""
    from cli.run_contract import _load_input

    binary = tmp_path / "binary.bin"
    binary.write_bytes(b"\xff\xfe\xfd\x00\x80")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        _load_input(str(binary))

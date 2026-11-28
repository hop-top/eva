"""`eva run --contract` exits 2 and `eva contract validate` reports a bad evaluator config."""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def eva(cwd, *args):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("EVA_JUDGE_MODEL", None)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=env,
    )


def _contract(tmp_path, evaluator):
    c = tmp_path / "c.yaml"
    c.write_text(
        "name: bad\nprovider: noop\nevaluators:\n"
        "  - {name: contains, substring: hi}\n"
        f"  - {evaluator}\n"
    )
    (tmp_path / "in.txt").write_text("hi")
    return c


def test_run_contract_exits_2_with_real_message(tmp_path):
    c = _contract(tmp_path, "{name: mood, expected: grumpy}")
    r = eva(tmp_path, "run", "--contract", str(c), "--input", str(tmp_path / "in.txt"))
    out = r.stdout + r.stderr
    assert r.returncode == 2, out
    assert "evaluator 'mood':" in out and "grumpy" in out
    assert "no judge model" not in out and "Traceback" not in out


def test_contract_validate_reports_it(tmp_path):
    c = _contract(tmp_path, "{name: mood, expected: grumpy}")
    r = eva(tmp_path, "contract", "validate", str(c))
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "evaluator 'mood':" in out and "grumpy" in out
    assert "Valid" not in out


def test_judge_without_adapter_is_not_invalid(tmp_path):
    c = _contract(tmp_path, "{name: relevance}")
    assert eva(tmp_path, "contract", "validate", str(c)).returncode == 0
    r = eva(tmp_path, "run", "--contract", str(c), "--input", str(tmp_path / "in.txt"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no judge model configured" in r.stdout + r.stderr

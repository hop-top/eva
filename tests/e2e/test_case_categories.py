"""eva run / runs show / compare: per-category figures and --since."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]

DATASET = """\
name: cats
target: {provider: openai, base_url: "http://unused/v1", model: placeholder}
evaluators:
  - name: exact_match
    mode: binary
tests:
  - {id: m1, input: m1, expected_output: "4", metadata: {category: math, added: 2026-01-10}}
  - {id: m2, input: m2, expected_output: "4", metadata: {category: math, added: 2026-03-05}}
  - {id: c1, input: c1, expected_output: "yes", metadata: {category: code, added: 2026-03-06}}
  - {id: u1, input: u1, expected_output: "4"}
  - {id: s1, input: s1, metadata: {category: math, added: 2026-03-07}}
"""


def eva(cwd, *args):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("EVA_JUDGE_MODEL", None)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=env,
    )


def reply_ok(prompt):
    return {"content": {"m1": "4", "m2": "5", "c1": "yes", "u1": "4"}.get(prompt, "x")}


def reply_better(prompt):
    return {"content": {"m1": "4", "m2": "4", "c1": "yes", "u1": "4"}.get(prompt, "x")}


def run(tmp_path, srv, *extra):
    ds = tmp_path / "ds.yaml"
    ds.write_text(DATASET)
    return eva(tmp_path, "run", "--dataset", str(ds), "--base-url", f"{srv.url}/v1",
               "--model", "m", *extra)


def test_run_json_has_categories_and_uncategorised(tmp_path):
    with FakeChatServer(reply_ok) as srv:
        r = run(tmp_path, srv, "--format", "json")
    data = json.loads(r.stdout)
    assert data["categories"] == {
        "math": {"passed": 1, "total": 2},
        "code": {"passed": 1, "total": 1},
        "uncategorised": {"passed": 1, "total": 1},
    }
    assert "since" not in data or data["since"] is None


def test_run_json_since(tmp_path):
    with FakeChatServer(reply_ok) as srv:
        r = run(tmp_path, srv, "--format", "json", "--since", "2026-03-01")
    data = json.loads(r.stdout)
    # m2 (fail), c1 (pass) counted; m1 too old; u1 undated; s1 unscored
    assert data["since"] == {"since": "2026-03-01", "passed": 1, "total": 2, "excluded": 1}


def test_run_text_prints_categories_and_since(tmp_path):
    with FakeChatServer(reply_ok) as srv:
        r = run(tmp_path, srv, "--no-tui", "--since", "2026-03-01")
    assert "math: 1/2" in r.stdout
    assert "code: 1/1" in r.stdout
    assert "uncategorised: 1/1" in r.stdout
    assert "Since 2026-03-01: 1/2" in r.stdout and "1 without added date" in r.stdout
    assert "1 not scored" in r.stdout


def test_runs_show_and_compare(tmp_path):
    with FakeChatServer(reply_ok) as srv:
        a = re.search(r"Run: ([0-9a-f]{8})", run(tmp_path, srv, "--no-tui").stdout).group(1)
    with FakeChatServer(reply_better) as srv:
        b = re.search(r"Run: ([0-9a-f]{8})", run(tmp_path, srv, "--no-tui").stdout).group(1)
    show = eva(tmp_path, "runs", "show", "--run-id", a, "--since", "2026-03-01")
    assert show.returncode == 0, show.stderr
    assert "math: 1/2" in show.stdout and "uncategorised: 1/1" in show.stdout
    assert "Since 2026-03-01: 1/2" in show.stdout
    cmp_ = eva(tmp_path, "compare", "--left", a, "--right", b, "--since", "2026-03-01")
    assert cmp_.returncode == 0, cmp_.stdout + cmp_.stderr
    assert "Per-Category" in cmp_.stdout
    assert "1/2" in cmp_.stdout and "2/2" in cmp_.stdout
    assert "Since 2026-03-01: left 1/2" in cmp_.stdout


def test_bad_since_exit_2(tmp_path):
    with FakeChatServer(reply_ok) as srv:
        r = run(tmp_path, srv, "--since", "nope")
    assert r.returncode == 2 and "--since" in r.stdout
    assert eva(tmp_path, "runs", "show", "--run-id", "x", "--since", "nope").returncode == 2
    assert eva(tmp_path, "compare", "--left", "a", "--right", "b",
               "--since", "nope").returncode == 2

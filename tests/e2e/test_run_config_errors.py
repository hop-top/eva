"""`eva run` exits 2 on invalid evaluator config, before calling the target."""
import os
import subprocess
import sys
from pathlib import Path

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]


def eva(cwd, *args):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("EVA_JUDGE_MODEL", None)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=env,
    )


def write(tmp_path, evaluator_line):
    p = tmp_path / "d.yaml"
    p.write_text(
        "name: cfg\n"
        "evaluators:\n"
        f"  - {evaluator_line}\n"
        "  - {name: contains, substring: hi}\n"
        "tests:\n"
        "  - {id: a, input: say hi}\n"
    )
    return p


def test_bad_config_exits_2_naming_evaluator_and_value(tmp_path):
    ds = write(tmp_path, "{name: refusal, mode: sideways}")
    with FakeChatServer(lambda p: {"content": "hi there"}) as srv:
        for extra in ([], ["--no-tui"], ["--format", "json"]):
            r = eva(tmp_path, "run", "--dataset", str(ds), *extra,
                    "--provider", "openai", "--base-url", f"{srv.url}/v1", "--model", "m")
            assert r.returncode == 2, r.stdout + r.stderr
            out = r.stdout + r.stderr
            assert "refusal" in out and "sideways" in out
            assert "Traceback" not in out
        assert srv.requests == []


def test_bad_key_facts_threshold_exits_2(tmp_path):
    ds = write(tmp_path, "{name: key_facts, threshold: 5}")
    with FakeChatServer(lambda p: {"content": "hi"}) as srv:
        r = eva(tmp_path, "run", "--dataset", str(ds), "--no-tui",
                "--provider", "openai", "--base-url", f"{srv.url}/v1", "--model", "m")
        assert r.returncode == 2, r.stdout + r.stderr
        assert "key_facts" in r.stdout + r.stderr and "threshold" in r.stdout + r.stderr
        assert srv.requests == []


def test_key_facts_conflict_exits_2(tmp_path):
    ds = write(tmp_path, "{name: key_facts, mode: binary, threshold: 0.5}")
    with FakeChatServer(lambda p: {"content": "hi"}) as srv:
        r = eva(tmp_path, "run", "--dataset", str(ds), "--no-tui",
                "--provider", "openai", "--base-url", f"{srv.url}/v1", "--model", "m")
        assert r.returncode == 2, r.stdout + r.stderr
        assert "Traceback" not in r.stdout + r.stderr
        assert srv.requests == []


def test_valid_config_still_runs(tmp_path):
    ds = write(tmp_path, "{name: word_count, max: 10}")
    with FakeChatServer(lambda p: {"content": "hi there"}) as srv:
        r = eva(tmp_path, "run", "--dataset", str(ds), "--no-tui",
                "--provider", "openai", "--base-url", f"{srv.url}/v1", "--model", "m")
        assert r.returncode == 0, r.stdout + r.stderr
        assert len(srv.requests) == 1

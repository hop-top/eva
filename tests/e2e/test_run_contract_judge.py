"""`eva run --contract --input --prompt`: judge evaluators against a local fake server."""
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]
JUDGE_MARK = "Rate the relevance"


def eva(cwd, *args, env=None, stdin=None):
    base = {**os.environ, "PYTHONPATH": str(REPO)}
    for k in ("EVA_JUDGE_MODEL", "EVA_JUDGE_BASE_URL", "OPENAI_API_KEY", "OPENAI_API_BASE"):
        base.pop(k, None)
    base.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=base, input=stdin,
    )


def judge_env(srv):
    return {"EVA_JUDGE_MODEL": "openai/judge-model", "EVA_JUDGE_BASE_URL": f"{srv.url}/v1"}


def scoring(value):
    return lambda prompt: {"content": f"{value}\nreason-{value}"}


def setup(tmp_path):
    c = tmp_path / "c.yaml"
    c.write_text(dedent("""
        name: c
        provider: noop
        evaluators:
          - name: relevance
            mode: threshold
            min_score: 0.5
          - name: contains
            substring: hi
        """))
    i = tmp_path / "in.txt"
    i.write_text("hi RESPONSE-A1")
    return c, i


def test_prompt_flag_runs_judge_with_prompt_and_response(tmp_path):
    c, i = setup(tmp_path)
    with FakeChatServer(scoring(0.9)) as srv:
        r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
                "--prompt", "PROMPT-B2", "--format", "json", env=judge_env(srv))
    assert r.returncode == 0, r.stdout + r.stderr
    p = json.loads(r.stdout)
    assert [e["name"] for e in p["evaluators"]] == ["relevance", "contains"]
    assert p["evaluators"][0]["score"] == 0.9 and p["skipped_judge"] == []
    (req,) = srv.requests
    sent = req["body"]["messages"][-1]["content"]
    assert JUDGE_MARK in sent and "PROMPT-B2" in sent and "RESPONSE-A1" in sent


def test_prompt_file_flag(tmp_path):
    c, i = setup(tmp_path)
    pf = tmp_path / "p.txt"
    pf.write_text("PROMPT-FROM-FILE")
    with FakeChatServer(scoring(0.9)) as srv:
        r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
                "--prompt-file", str(pf), "--format", "json", env=judge_env(srv))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PROMPT-FROM-FILE" in srv.requests[0]["body"]["messages"][-1]["content"]


def test_prompt_file_stdin(tmp_path):
    c, i = setup(tmp_path)
    with FakeChatServer(scoring(0.9)) as srv:
        r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
                "--prompt-file", "-", "--format", "json", env=judge_env(srv),
                stdin="PROMPT-FROM-STDIN\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PROMPT-FROM-STDIN" in srv.requests[0]["body"]["messages"][-1]["content"]


def test_failing_judge_verdict_exits_1(tmp_path):
    c, i = setup(tmp_path)
    with FakeChatServer(scoring(0.1)) as srv:
        r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
                "--prompt", "p", "--format", "text", env=judge_env(srv))
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout == ""
    assert "FAIL" in r.stderr and "relevance" in r.stderr and "FAILED" in r.stderr


def test_judge_configured_no_prompt_skips_with_flag_hint(tmp_path):
    c, i = setup(tmp_path)
    with FakeChatServer(scoring(0.9)) as srv:
        r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
                "--format", "json", env=judge_env(srv))
        assert srv.requests == []
    assert r.returncode == 0, r.stdout + r.stderr
    (entry,) = json.loads(r.stdout)["skipped_judge"]
    assert entry.startswith("relevance: ") and "--prompt" in entry and "--prompt-file" in entry


def test_no_judge_with_prompt_still_skips(tmp_path):
    c, i = setup(tmp_path)
    r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
            "--prompt", "p", "--format", "json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)["skipped_judge"] == ["relevance: no judge model configured"]


def test_judge_endpoint_error_is_a_failed_evaluator_not_a_crash(tmp_path):
    c, i = setup(tmp_path)
    (tmp_path / "eva.yaml").write_text("judge:\n  timeout_s: 10\n")
    with FakeChatServer(lambda p: {"status": 500, "error": "boom"}) as srv:
        r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
                "--prompt", "p", "--format", "json", env=judge_env(srv))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "Traceback" not in r.stderr
    p = json.loads(r.stderr)
    rel = p["evaluators"][0]
    assert rel["name"] == "relevance" and rel["passed"] is False and rel["score"] == 0.0
    assert rel["reason"].startswith("judge error")


def test_prompt_and_prompt_file_are_exclusive(tmp_path):
    c, i = setup(tmp_path)
    pf = tmp_path / "p.txt"
    pf.write_text("x")
    r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
            "--prompt", "a", "--prompt-file", str(pf))
    assert r.returncode == 2
    assert "--prompt" in r.stdout + r.stderr and "--prompt-file" in r.stdout + r.stderr


def test_prompt_file_stdin_with_input_stdin_is_an_error(tmp_path):
    c, _ = setup(tmp_path)
    r = eva(tmp_path, "run", "--contract", str(c), "--input", "-",
            "--prompt-file", "-", stdin="x")
    assert r.returncode == 2
    assert "stdin" in (r.stdout + r.stderr).lower()


def test_prompt_flags_require_contract(tmp_path):
    for flag in (["--prompt", "x"], ["--prompt-file", "-"]):
        r = eva(tmp_path, "run", *flag)
        assert r.returncode == 2, flag
        assert "--contract" in r.stdout + r.stderr


def test_prompt_file_missing_exits_2(tmp_path):
    c, i = setup(tmp_path)
    r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
            "--prompt-file", str(tmp_path / "nope.txt"))
    assert r.returncode == 2
    assert "nope.txt" in r.stdout + r.stderr

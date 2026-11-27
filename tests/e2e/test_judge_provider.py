"""Judge evaluators through the CLI: self-hosted endpoint + no-judge skip."""
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]
JUDGE_MARK = "Rate the relevance"


def eva(cwd, *args, env=None):
    base = {**os.environ, "PYTHONPATH": str(REPO)}
    for k in ("EVA_JUDGE_MODEL", "EVA_JUDGE_BASE_URL", "OPENAI_API_KEY",
              "OPENAI_API_BASE", "JUDGE_KEY_T"):
        base.pop(k, None)
    base.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=base,
    )


def reply(prompt):
    if JUDGE_MARK in prompt:
        return {"content": "0.9\nfits"}
    return {"content": "an answer"}


def _dataset(tmp_path, base):
    p = tmp_path / "ds.yaml"
    p.write_text(dedent(f"""
        name: judged
        target:
          provider: openai
          base_url: {base}
          model: agent-model
        evaluators:
          - name: relevance
            mode: threshold
            min_score: 0.5
        tests:
          - id: t1
            input: hello
        """))
    return p


def _judge_requests(srv):
    return [r for r in srv.requests if JUDGE_MARK in r["body"]["messages"][-1]["content"]]


def test_dataset_no_tui_yaml_self_hosted_endpoint(tmp_path):
    with FakeChatServer(reply) as srv:
        base = f"{srv.url}/v1"
        (tmp_path / "eva.yaml").write_text(dedent(f"""
            judge:
              model: openai/judge-model
              base_url: {base}
              api_key_env: JUDGE_KEY_T
              timeout_s: 30
            """))
        r = eva(tmp_path, "run", "--dataset", str(_dataset(tmp_path, base)),
                "--no-tui", env={"JUDGE_KEY_T": "tok-1"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "relevance" in r.stdout and "skipped" not in r.stderr
    j = _judge_requests(srv)
    assert len(j) == 1
    assert j[0]["path"] == "/v1/chat/completions"
    assert j[0]["body"]["model"] == "judge-model"
    hdrs = {k.lower(): v for k, v in j[0]["headers"].items()}
    assert hdrs.get("authorization") == "Bearer tok-1"


def test_dataset_default_tui_env_self_hosted_endpoint(tmp_path):
    with FakeChatServer(reply) as srv:
        base = f"{srv.url}/v1"
        r = eva(tmp_path, "run", "--dataset", str(_dataset(tmp_path, base)),
                env={"EVA_JUDGE_MODEL": "openai/judge-model",
                     "EVA_JUDGE_BASE_URL": base,
                     "OPENAI_API_KEY": "ambient-must-not-leak"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "relevance" in r.stdout
    j = _judge_requests(srv)
    assert len(j) == 1
    hdrs = {k.lower(): v for k, v in j[0]["headers"].items()}
    # ambient OPENAI_API_KEY must not reach a custom endpoint
    assert hdrs.get("authorization") == "Bearer none"


def test_dataset_missing_key_env_exits_2(tmp_path):
    with FakeChatServer(reply) as srv:
        base = f"{srv.url}/v1"
        (tmp_path / "eva.yaml").write_text(
            f"judge:\n  model: openai/m\n  base_url: {base}\n  api_key_env: JUDGE_KEY_T\n"
        )
        r = eva(tmp_path, "run", "--dataset", str(_dataset(tmp_path, base)), "--no-tui")
    assert r.returncode == 2
    assert "JUDGE_KEY_T" in r.stdout + r.stderr


def test_dataset_no_judge_skips_with_reason(tmp_path):
    with FakeChatServer(reply) as srv:
        r = eva(tmp_path, "run", "--dataset",
                str(_dataset(tmp_path, f"{srv.url}/v1")), "--no-tui")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipped: relevance" in r.stderr
    assert not _judge_requests(srv)


def _contract(tmp_path):
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
    i.write_text("hi there")
    return c, i


def test_contract_no_judge_skips_not_exit_2(tmp_path):
    c, i = _contract(tmp_path)
    r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
            "--format", "json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["passed"] is True
    assert [e["name"] for e in payload["evaluators"]] == ["contains"]
    assert payload["skipped_judge"] == ["relevance: no judge model configured"]


def test_contract_no_judge_text_output(tmp_path):
    c, i = _contract(tmp_path)
    r = eva(tmp_path, "run", "--contract", str(c), "--input", str(i),
            "--format", "text")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipped: relevance (no judge model configured)" in r.stdout

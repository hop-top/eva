"""Sample tool_call_match dataset through `eva run` against a fake server."""
import os
import subprocess
import sys
from pathlib import Path

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "docs/examples/tool-call-match.yaml"


def eva(cwd, *args):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("EVA_JUDGE_MODEL", None)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=env,
    )


def reply(prompt):
    if "Paris and in Rome" in prompt:   # parallel, reversed order
        return {"tool_calls": [
            {"name": "get_weather", "arguments": {"city": "rome"}},
            {"name": "get_weather", "arguments": {"city": " Paris "}},
        ]}
    if "weather in Paris" in prompt:
        return {"tool_calls": [{"name": "get_weather", "arguments": {"city": "Paris"}}]}
    if "Add 2 and 3" in prompt:
        return {"tool_calls": [{"name": "add", "arguments": {"a": 2.0, "b": 3}}]}
    # set-timer: malformed arguments, required `minutes` cannot match
    return {"tool_calls": [{"name": "set_timer", "arguments": '{"minutes": '}]}


def test_example_dataset_end_to_end(tmp_path):
    with FakeChatServer(reply) as srv:
        r = eva(tmp_path, "run", "--dataset", str(EXAMPLE), "--no-tui",
                "--base-url", f"{srv.url}/v1", "--model", "m")
    out = r.stdout + r.stderr
    assert len(srv.requests) == 4
    assert "✓ weather-paris · tool_call_match" in out
    assert "✓ weather-two-cities · tool_call_match" in out
    assert "✓ add-numbers · tool_call_match" in out
    assert "✗ set-timer · tool_call_match" in out
    assert "arguments were not valid JSON" in out
    assert r.returncode != 0, out  # set-timer fails


def test_none_mode_through_run(tmp_path):
    ds = tmp_path / "none.yaml"
    ds.write_text(
        "name: none\n"
        "target: {provider: openai, model: m}\n"
        "evaluators:\n  - {name: tool_call_match, mode: binary, match: none}\n"
        "tests:\n"
        "  - {id: chatty, input: 'say hi'}\n"
        "  - {id: eager, input: 'call it'}\n"
    )

    def rep(prompt):
        if "call it" in prompt:
            return {"tool_calls": [{"name": "get_weather", "arguments": {}}]}
        return {"content": "hi"}

    with FakeChatServer(rep) as srv:
        r = eva(tmp_path, "run", "--dataset", str(ds), "--no-tui",
                "--base-url", f"{srv.url}/v1", "--model", "m")
    out = r.stdout + r.stderr
    assert "✓ chatty · tool_call_match" in out
    assert "✗ eager · tool_call_match" in out
    assert "expected no tool call" in out


def test_contract_mode_scores_zero_with_reason(tmp_path):
    contract = tmp_path / "c.yaml"
    contract.write_text(
        "name: calls\nprovider: noop\n"
        "evaluators:\n  - name: tool_call_match\n    match: none\n"
    )
    inp = tmp_path / "in.txt"
    inp.write_text("hi")
    r = eva(tmp_path, "run", "--contract", str(contract), "--input", str(inp),
            "--format", "json")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "tool-call log" in r.stderr

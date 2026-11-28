"""`eva run` against a fake OpenAI-compatible server; then runs show / compare."""
import os
import re
import subprocess
import sys
from pathlib import Path

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "docs/examples/local-openai-coding-reasoning.yaml"


def eva(cwd, *args):
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    env.pop("EVA_JUDGE_MODEL", None)
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        check=False, capture_output=True, text=True, cwd=cwd, env=env,
    )


def reply(prompt):
    if "add(a, b)" in prompt:
        return {"content": "```python\ndef add(a, b):\n    return a + b\n```",
                "reasoning_content": "sum them"}
    return {"content": "<think>3+5-2</think>Final answer: 6"}


def run_id(out):
    return re.search(r"Run: ([0-9a-f]{8})", out).group(1)


def test_example_dataset_end_to_end(tmp_path):
    with FakeChatServer(reply) as srv:
        base = f"{srv.url}/v1"
        r1 = eva(tmp_path, "run", "--dataset", str(EXAMPLE), "--no-tui",
                 "--base-url", base, "--model", "model-a")
        r2 = eva(tmp_path, "run", "--dataset", str(EXAMPLE), "--no-tui",
                 "--base-url", base, "--model", "model-b")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert "code-add · code_tests" in r1.stdout
    assert srv.requests[0]["body"]["model"] == "model-a"
    assert srv.requests[0]["path"] == "/v1/chat/completions"
    a, b = run_id(r1.stdout), run_id(r2.stdout)

    show = eva(tmp_path, "runs", "show", "--run-id", a)
    assert show.returncode == 0, show.stderr
    assert "model-a" in show.stdout and "openai" in show.stdout

    cmp_ = eva(tmp_path, "compare", "--left", a, "--right", b)
    assert cmp_.returncode == 0, cmp_.stdout + cmp_.stderr
    assert "model-a" in cmp_.stdout and "model-b" in cmp_.stdout
    assert "latency" in cmp_.stdout.lower() and "Prompt tokens" in cmp_.stdout


def test_failing_model_exit_code_and_reason(tmp_path):
    with FakeChatServer(lambda p: {"content": "no idea"}) as srv:
        r = eva(tmp_path, "run", "--dataset", str(EXAMPLE), "--no-tui",
                "--base-url", f"{srv.url}/v1", "--model", "m")
    assert r.returncode == 1
    assert "no python code block" in r.stdout


def test_default_tui_path_scores_builtins(tmp_path):
    with FakeChatServer(reply) as srv:
        r = eva(tmp_path, "run", "--dataset", str(EXAMPLE),
                "--base-url", f"{srv.url}/v1", "--model", "m")
    assert "code_tests" in r.stdout and "final_answer" in r.stdout


def test_url_and_chat_flags_conflict(tmp_path):
    r = eva(tmp_path, "run", "--dataset", str(EXAMPLE), "--target", "http://x", "--model", "m")
    assert r.returncode == 2


def test_json_format_has_run(tmp_path):
    with FakeChatServer(reply) as srv:
        r = eva(tmp_path, "run", "--dataset", str(EXAMPLE), "--format", "json",
                "--base-url", f"{srv.url}/v1", "--model", "m")
    assert '"results"' in r.stdout


def test_case_tools_sent_through_cli(tmp_path):
    ds = tmp_path / "tools.yaml"
    ds.write_text(
        "name: tools\n"
        "target: {provider: openai, model: m}\n"
        "evaluators:\n  - {name: final_answer, mode: binary}\n"
        "tests:\n"
        "  - id: weather\n    input: 'Weather in Paris? Final answer: 6'\n"
        "    expected_output: '6'\n    tool_choice: required\n"
        "    tools:\n"
        "      - type: function\n"
        "        function: {name: get_weather, parameters: {type: object}}\n"
    )
    calls = {"content": "Final answer: 6",
             "tool_calls": [{"name": "get_weather", "arguments": '{"city": '}]}
    with FakeChatServer(lambda p: calls) as srv:
        r = eva(tmp_path, "run", "--dataset", str(ds), "--no-tui",
                "--base-url", f"{srv.url}/v1", "--model", "m")
    assert r.returncode == 0, r.stdout + r.stderr
    body = srv.requests[0]["body"]
    assert body["tools"][0]["function"]["name"] == "get_weather"
    assert body["tool_choice"] == "required"
    assert len(srv.requests) == 1

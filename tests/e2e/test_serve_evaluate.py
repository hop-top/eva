"""`eva serve --no-auth` evaluate-only route, against a local fake judge server.

The contract's provider is unreachable: the route must never call it.
"""
from __future__ import annotations

import httpx
import pytest

from tests.e2e.test_serve_judge import (
    JUDGE_MARK,
    _free_port,
    _project,
    _spawn,
    _stop,
    _wait_healthy,
)
from tests.fake_chat_server import FakeChatServer

OUTPUT = {"exit_code": 0, "stdout": "ANSWER-TEXT-4\n", "stderr": ""}


def _evaluate(port: int, payload: dict) -> httpx.Response:
    return httpx.post(
        f"http://127.0.0.1:{port}/v1/contract/evaluate", json=payload, timeout=15
    )


@pytest.mark.e2e
def test_serve_evaluates_supplied_output_without_a_provider(tmp_path):
    def reply(prompt: str) -> dict:
        return {"content": "0.9\nverdict"}

    with FakeChatServer(reply) as judge:
        proj = _project(tmp_path)  # provider http://127.0.0.1:1/x: nothing listens
        port = _free_port()
        proc = _spawn(proj, port, env={
            "EVA_JUDGE_MODEL": "openai/judge-model",
            "EVA_JUDGE_BASE_URL": f"{judge.url}/v1",
        })
        try:
            _wait_healthy(proc, port)
            ok = _evaluate(port, {"contract": "judged", "output": "ANSWER-TEXT-4", "prompt": "PROMPT-Q-9"})
            obj = _evaluate(port, {"contract": "judged", "output": OUTPUT, "prompt": "PROMPT-Q-9"})
            bad = _evaluate(port, {"contract": "judged", "output": "no match", "prompt": "PROMPT-Q-9"})
            noprompt = _evaluate(port, {"contract": "judged", "output": "ANSWER-TEXT-4"})
            missing = _evaluate(port, {"contract": "nope", "output": "x"})
            malformed = _evaluate(port, {"contract": "judged", "output": [1]})
        finally:
            _stop(proc)

    assert ok.status_code == 200, ok.text
    assert list(ok.json()) == ["eva_status", "request_id", "trace_id"]
    sent = judge.requests[0]["body"]["messages"][-1]["content"]
    assert JUDGE_MARK in sent and "PROMPT-Q-9" in sent and "ANSWER-TEXT-4" in sent

    assert obj.status_code == 200, obj.text  # JSON text of the object contains ANSWER

    assert bad.status_code == 422, bad.text
    assert [v["evaluator"] for v in bad.json()["violations"]] == ["contains"]

    assert noprompt.status_code == 200, noprompt.text
    assert noprompt.json()["skipped"] == [
        {"evaluator": "relevance",
         "reason": "judge evaluators need the request prompt: send prompt"}
    ]
    assert missing.status_code == 404
    assert malformed.status_code == 422 and "eva_status" not in malformed.json()
    # judged: ok, obj, bad (relevance runs); noprompt skipped it
    assert len(judge.requests) == 3

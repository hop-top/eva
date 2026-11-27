"""`eva serve --no-auth` with judge evaluators, against a local fake judge server.

Every process here is local: the judge is tests/fake_chat_server.py and the
agent is a tiny in-test HTTP server. No hosted model is reached.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from textwrap import dedent

import httpx
import pytest

from tests.fake_chat_server import FakeChatServer

REPO = Path(__file__).resolve().parents[2]
EXIT_BAD_INPUT = 2
JUDGE_MARK = "Rate the relevance"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(extra: dict | None = None) -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "EVA_REDIS_URL", "EVA_NO_AUTH", "EVA_JUDGE_MODEL", "EVA_JUDGE_BASE_URL",
            "OPENAI_API_KEY", "OPENAI_API_BASE", "UNSET_JUDGE_KEY",
        )
    }
    env["PYTHONPATH"] = str(REPO)
    env.update(extra or {})
    return env


def _spawn(cwd: Path, port: int, *extra: str, env: dict | None = None):
    return subprocess.Popen(
        [sys.executable, "-m", "cli.main", "serve", "--no-auth",
         "--host", "127.0.0.1", "--port", str(port),
         "--contracts-dir", str(cwd / "contracts"), *extra],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=cwd, env=_env(env),
    )


def _wait_healthy(proc, port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"serve exited early rc={proc.returncode}: {proc.stderr.read()}")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5).status_code == 200:
                return
        except Exception:
            time.sleep(0.1)
    proc.terminate()
    raise AssertionError(f"Server did not start within {timeout}s")


def _stop(proc) -> str:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    return proc.stderr.read()


class _Agent:
    """Local upstream agent answering every POST with a fixed text."""

    def __init__(self, text: str):
        data = text.encode()

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/respond"
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def _project(tmp_path: Path, agent_url: str = "http://127.0.0.1:1/x") -> Path:
    cdir = tmp_path / "contracts"
    cdir.mkdir()
    (cdir / "judged.yaml").write_text(dedent(f"""
        name: judged
        provider: {agent_url}
        prompt_field: question
        evaluators:
          - name: relevance
            mode: threshold
            min_score: 0.5
          - name: contains
            substring: ANSWER
        """))
    return tmp_path


# --- configuration errors fail at start --------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("mode", [[], ["--workers", "2"], ["--reload"]])
def test_bad_judge_config_stops_serve_at_start(tmp_path, mode):
    proj = _project(tmp_path)
    (proj / "eva.yaml").write_text(dedent("""
        judge:
          model: openai/judge-model
          base_url: http://127.0.0.1:1/v1
          api_key_env: UNSET_JUDGE_KEY
        """))
    port = _free_port()
    proc = _spawn(proj, port, *mode)
    try:
        rc = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("serve kept running with an unbuildable judge")
    err = proc.stderr.read()
    assert rc == EXIT_BAD_INPUT, err
    assert "judge.api_key_env 'UNSET_JUDGE_KEY' is not set in the environment" in err
    assert "Traceback" not in err
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", port)) != 0  # nothing bound


# --- real process, fake judge -------------------------------------------------


def _invoke(port: int, question: str | None = "PROMPT-Q-9") -> httpx.Response:
    body = {} if question is None else {"question": question}
    return httpx.post(
        f"http://127.0.0.1:{port}/v1/contract/invoke",
        json={"contract": "judged", "body": body},
        timeout=15,
    )


@pytest.mark.e2e
def test_serve_runs_judge_evaluator_against_fake_judge(tmp_path):
    def reply(prompt: str) -> dict:
        score = "0.1" if "PROMPT-BAD" in prompt else "0.9"
        return {"content": f"{score}\nverdict"}

    with FakeChatServer(reply) as judge, \
            _Agent("ANSWER-TEXT-4") as agent:
        proj = _project(tmp_path, agent.url)
        port = _free_port()
        proc = _spawn(proj, port, env={
            "EVA_JUDGE_MODEL": "openai/judge-model",
            "EVA_JUDGE_BASE_URL": f"{judge.url}/v1",
        })
        try:
            _wait_healthy(proc, port)
            ok = _invoke(port)
            bad = _invoke(port, question="PROMPT-BAD")
            skipped = _invoke(port, question=None)
        finally:
            _stop(proc)

    assert ok.status_code == 200, ok.text
    assert ok.json()["eva_status"] == "pass" and "skipped" not in ok.json()
    first, second = judge.requests[0], judge.requests[1]
    sent = first["body"]["messages"][-1]["content"]
    assert JUDGE_MARK in sent and "PROMPT-Q-9" in sent and "ANSWER-TEXT-4" in sent
    assert first["body"]["model"] == "judge-model"

    assert bad.status_code == 422, bad.text
    (v,) = bad.json()["violations"]
    assert v["evaluator"] == "relevance" and v["score"] == 0.1
    assert "PROMPT-BAD" in second["body"]["messages"][-1]["content"]

    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["skipped"] == [
        {"evaluator": "relevance", "reason": "request body has no field 'question'"}
    ]
    # 1 call for `ok`; `bad` is judged on each of its 3 attempts (default
    # retry policy: 2 retries); the skipped request made no judge call.
    assert bad.json()["attempts"] == 3
    assert len(judge.requests) == 4


@pytest.mark.e2e
def test_serve_without_judge_skips_judge_evaluators(tmp_path):
    with _Agent("ANSWER-TEXT-4") as agent:
        proj = _project(tmp_path, agent.url)
        port = _free_port()
        proc = _spawn(proj, port)
        try:
            _wait_healthy(proc, port)
            resp = _invoke(port)
        finally:
            _stop(proc)
    assert resp.status_code == 200, resp.text
    assert resp.json()["skipped"] == [
        {"evaluator": "relevance", "reason": "no judge model configured"}
    ]
    json.dumps(resp.json())

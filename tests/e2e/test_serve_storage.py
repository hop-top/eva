"""`eva serve --no-auth` records gateway traffic in the state db.

Real serve subprocess; the upstream agent is a tiny in-test HTTP server on
loopback. Each serve runs in its own temp cwd, so `.eva/state.db` stays local.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from textwrap import dedent

import httpx
import pytest

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parents[2]
REPLY = json.dumps(
    {
        "answer": "hello",
        "model": "prov/m1",
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    }
).encode()


class _Agent:
    def __init__(self):
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                time.sleep(0.02)  # keep both workers busy under concurrent load
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(REPLY)))
                self.end_headers()
                self.wfile.write(REPLY)

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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(home: Path) -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("EVA_REDIS_URL", "EVA_NO_AUTH", "EVA_SERVE_DB")
    }
    env["PYTHONPATH"] = str(REPO)
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / "cfg")
    env["XDG_DATA_HOME"] = str(home / "data")
    return env


def _project(tmp_path: Path, agent_url: str) -> Path:
    cdir = tmp_path / "contracts"
    cdir.mkdir()
    (cdir / "good.yaml").write_text(dedent(f"""
        name: good
        provider: {agent_url}
        prompt_field: q
        evaluators:
          - name: contains
            substring: hello
        """))
    (cdir / "bad.yaml").write_text(dedent(f"""
        name: bad
        provider: {agent_url}
        prompt_field: q
        retry_policy:
          max_retries: 0
        evaluators:
          - name: contains
            substring: NOPE-ZZZ
        """))
    (tmp_path / "home").mkdir()
    return tmp_path


def _spawn(proj: Path, port: int, *extra: str):
    return subprocess.Popen(
        [sys.executable, "-m", "cli.main", "serve", "--no-auth",
         "--host", "127.0.0.1", "--port", str(port), *extra],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=proj, env=_env(proj / "home"),
    )


def _wait_healthy(proc, port: int, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"serve exited early: {proc.stderr.read()}")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5).status_code == 200:
                return
        except Exception:
            time.sleep(0.1)
    proc.terminate()
    raise AssertionError("serve did not start")


def _stop(proc) -> str:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    return proc.stderr.read()


def _eva(proj: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True, text=True, cwd=proj, env=_env(proj / "home"),
    )


def _query(db: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _traffic(port: int, agent_url: str) -> dict:
    u = f"http://127.0.0.1:{port}/v1"
    return {
        "proxy": httpx.post(u + "/proxy", json={
            "target": agent_url, "body": {"q": "hi"}, "evaluators": []}, timeout=15),
        "invoke": httpx.post(u + "/contract/invoke",
                             json={"contract": "good", "body": {"q": "hi"}}, timeout=15),
        "bad": httpx.post(u + "/contract/invoke",
                          json={"contract": "bad", "body": {"q": "hi"}}, timeout=15),
        "evaluate": httpx.post(u + "/contract/evaluate",
                               json={"contract": "good", "output": "hello"}, timeout=15),
    }


def _run_serve(tmp_path, *extra):
    with _Agent() as agent:
        proj = _project(tmp_path, agent.url)
        port = _free_port()
        proc = _spawn(proj, port, *extra)
        try:
            _wait_healthy(proc, port)
            out = _traffic(port, agent.url)
        finally:
            _stop(proc)
    return proj, out


def test_serve_records_gateway_traffic_in_default_db(tmp_path):
    proj, out = _run_serve(tmp_path)
    assert out["proxy"].status_code == 200
    assert out["invoke"].status_code == 200
    assert out["bad"].status_code == 422
    assert out["evaluate"].status_code == 200

    db = proj / ".eva" / "state.db"
    assert db.exists()
    rows = _query(db, "select source, contract_name, status, request_id, invocation_id "
                      "from invocationrecord order by started_at")
    assert sorted((r[0], r[1], r[2]) for r in rows) == [
        ("contract_invoke", "bad", "fail"),
        ("contract_invoke", "good", "pass"),
        ("gateway_proxy", "inline", "pass"),
    ]  # evaluate wrote nothing

    good = next(r for r in rows if r[1] == "good")
    assert good[3] == out["invoke"].json()["request_id"]
    usage = _query(db, "select invocation_id, total_tokens from usagerecordrecord")
    assert usage == [(good[4], 7)]

    shown = _eva(proj, "invocations", "show", "--id", good[4])
    assert shown.returncode == 0, shown.stderr
    assert "contract_invoke" in shown.stdout
    failures = _eva(proj, "failures", "list", "--contract", "bad")
    assert failures.returncode == 0, failures.stderr
    assert "Failures (1)" in failures.stdout
    passing = _eva(proj, "failures", "list", "--contract", "good")
    assert "No failures found" in passing.stdout


def test_serve_db_flag_redirects_storage(tmp_path):
    other = tmp_path / "elsewhere" / "gw.db"
    proj, out = _run_serve(tmp_path, "--db", str(other))
    assert out["invoke"].status_code == 200
    assert other.exists()
    assert not (proj / ".eva" / "state.db").exists()
    assert len(_query(other, "select * from invocationrecord")) == 3
    failures = _eva(proj, "failures", "list", "--db", str(other), "--contract", "bad")
    assert failures.returncode == 0, failures.stderr
    assert "Failures (1)" in failures.stdout


def test_serve_workers_2_both_write_one_db(tmp_path):
    with _Agent() as agent:
        proj = _project(tmp_path, agent.url)
        port = _free_port()
        proc = _spawn(proj, port, "--workers", "2")
        try:
            _wait_healthy(proc, port)
            u = f"http://127.0.0.1:{port}/v1/contract/invoke"
            errors: list[str] = []

            def hit():
                for _ in range(15):
                    r = httpx.post(u, json={"contract": "good", "body": {"q": "hi"}},
                                   timeout=30)
                    if r.status_code != 200:
                        errors.append(r.text)

            ts = [threading.Thread(target=hit) for _ in range(8)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        finally:
            err = _stop(proc)
    assert errors == []
    db = proj / ".eva" / "state.db"
    assert _query(db, "select count(*) from invocationrecord") == [(120,)]
    assert _query(db, "select count(*) from usagerecordrecord") == [(120,)]
    assert "database is locked" not in err
    pids = set(re.findall(r"Started server process \[(\d+)\]", err))
    assert len(pids) == 2

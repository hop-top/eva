# tests/e2e/test_serve_command.py
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

KEY_STORE_URL = "redis://127.0.0.1:1/0"  # never reached: requests lack a key
NO_AUTH_WARNING = "gateway is UNAUTHENTICATED"
REFUSAL_REMEDIES = ("EVA_REDIS_URL", "--no-auth")
EXIT_BAD_INPUT = 2


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(redis_url: str | None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("EVA_REDIS_URL", "EVA_NO_AUTH")}
    if redis_url:
        env["EVA_REDIS_URL"] = redis_url
    return env


def _spawn(port: int, *extra: str, redis_url: str | None = None):
    return subprocess.Popen(
        [sys.executable, "-m", "cli.main", "serve",
         "--host", "127.0.0.1", "--port", str(port), *extra],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_env(redis_url),
    )


def _wait_healthy(proc, port: int, timeout: float = 15.0) -> None:
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


def _invoke(port: int) -> httpx.Response:
    return httpx.post(
        f"http://127.0.0.1:{port}/v1/contract/invoke",
        json={"contract": "none", "body": {}},
        timeout=5,
    )


@pytest.mark.e2e
def test_eva_serve_starts_and_responds():
    # US-006: As Sam, I want to start an Eva gateway with `eva serve` so that all LLM traffic
    # passes through a validated proxy layer.
    # US-007: As Sam, I want Eva to expose a `/health` endpoint so that my load-balancer can
    # detect outages and route around them.
    """Start eva serve --no-auth as subprocess, poll /health, then terminate."""
    port = _free_port()
    proc = _spawn(port, "--no-auth")
    try:
        _wait_healthy(proc, port)
        resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        _stop(proc)


@pytest.mark.e2e
def test_serve_refuses_without_key_store_or_no_auth():
    port = _free_port()
    proc = _spawn(port)
    try:
        rc = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("serve did not refuse")
    err = proc.stderr.read()
    assert rc == EXIT_BAD_INPUT
    for remedy in REFUSAL_REMEDIES:
        assert remedy in err
    assert NO_AUTH_WARNING not in err
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", port)) != 0  # nothing bound


@pytest.mark.e2e
def test_serve_no_auth_serves_and_warns():
    port = _free_port()
    proc = _spawn(port, "--no-auth")
    try:
        _wait_healthy(proc, port)
        assert _invoke(port).status_code != 401
    finally:
        err = _stop(proc)
    assert NO_AUTH_WARNING in err


@pytest.mark.e2e
def test_serve_no_auth_workers_2():
    port = _free_port()
    proc = _spawn(port, "--no-auth", "--workers", "2")
    try:
        _wait_healthy(proc, port)
        for _ in range(4):  # hit more than one worker
            assert _invoke(port).status_code != 401
    finally:
        err = _stop(proc)
    assert NO_AUTH_WARNING in err


@pytest.mark.e2e
def test_serve_no_auth_reload():
    port = _free_port()
    proc = _spawn(port, "--no-auth", "--reload")
    try:
        _wait_healthy(proc, port)
        assert _invoke(port).status_code != 401
    finally:
        _stop(proc)


@pytest.mark.e2e
def test_serve_with_key_store_enforces_auth():
    port = _free_port()
    proc = _spawn(port, redis_url=KEY_STORE_URL)
    try:
        _wait_healthy(proc, port)
        assert _invoke(port).status_code == 401
    finally:
        err = _stop(proc)
    assert NO_AUTH_WARNING not in err


@pytest.mark.e2e
def test_serve_with_key_store_workers_2_enforces_auth():
    port = _free_port()
    proc = _spawn(port, "--workers", "2", redis_url=KEY_STORE_URL)
    try:
        _wait_healthy(proc, port)
        for _ in range(4):
            assert _invoke(port).status_code == 401
    finally:
        _stop(proc)


@pytest.mark.e2e
def test_serve_no_auth_wins_over_key_store():
    port = _free_port()
    proc = _spawn(port, "--no-auth", redis_url=KEY_STORE_URL)
    try:
        _wait_healthy(proc, port)
        assert _invoke(port).status_code != 401
    finally:
        err = _stop(proc)
    assert NO_AUTH_WARNING in err


@pytest.mark.e2e
def test_serve_no_auth_wins_over_key_store_workers_2():
    port = _free_port()
    proc = _spawn(port, "--no-auth", "--workers", "2", redis_url=KEY_STORE_URL)
    try:
        _wait_healthy(proc, port)
        for _ in range(4):
            assert _invoke(port).status_code != 401
    finally:
        _stop(proc)


@pytest.mark.e2e
def test_serve_ignores_stray_env_no_auth_without_flag():
    # EVA_NO_AUTH is set by --no-auth only; an inherited value must not
    # silently disable auth when the flag is absent.
    port = _free_port()
    env = _env(KEY_STORE_URL)
    env["EVA_NO_AUTH"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "cli.main", "serve", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    try:
        _wait_healthy(proc, port)
        assert _invoke(port).status_code == 401
    finally:
        _stop(proc)

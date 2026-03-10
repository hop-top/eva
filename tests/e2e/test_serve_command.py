# tests/e2e/test_serve_command.py
import subprocess
import sys
import time
import httpx
import pytest


@pytest.mark.e2e
def test_eva_serve_starts_and_responds():
    """Start eva serve as subprocess, poll /health, then terminate."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "cli.main", "serve", "--host", "127.0.0.1", "--port", "18765"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Poll until server is up (max 5s)
        for _ in range(50):
            time.sleep(0.1)
            try:
                resp = httpx.get("http://127.0.0.1:18765/health", timeout=0.5)
                if resp.status_code == 200:
                    break
            except Exception:
                continue
        else:
            proc.terminate()
            raise AssertionError("Server did not start within 5s")

        resp = httpx.get("http://127.0.0.1:18765/health", timeout=2)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        proc.terminate()
        proc.wait(timeout=5)

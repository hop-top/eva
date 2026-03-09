# tests/e2e/test_run.py
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FIXTURES = Path("tests/fixtures/datasets")


class AlwaysHelloHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            self.rfile.read(content_length)
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"hello world")

    def log_message(self, *args):
        pass  # suppress server logs in test output


def start_fake_agent(port: int):
    import time
    server = HTTPServer(("127.0.0.1", port), AlwaysHelloHandler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    time.sleep(0.1)  # Give it a moment to start
    return server


def run_eva(*args):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
    )


def test_eva_run_all_pass(tmp_path):
    server = start_fake_agent(18999)
    try:
        result = run_eva(
            "run",
            "--dataset", str(FIXTURES / "e2e_suite.yaml"),
            "--target", "http://127.0.0.1:18999/chat",
        )
        assert result.returncode == 0
        assert "passed" in result.stdout.lower() or "pass" in result.stdout.lower()
    finally:
        server.shutdown()


def test_eva_run_exit_code_zero_on_pass(tmp_path):
    server = start_fake_agent(18998)
    try:
        result = run_eva(
            "run",
            "--dataset", str(FIXTURES / "e2e_suite.yaml"),
            "--target", "http://127.0.0.1:18998/chat",
        )
        assert result.returncode == 0
    finally:
        server.shutdown()

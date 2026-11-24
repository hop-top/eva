"""Fake OpenAI-compatible / Anthropic HTTP server for tests (no live network)."""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# reply(prompt) -> dict with optional keys:
#   content, reasoning_content, reasoning, status, thinking, usage
Reply = Callable[[str], dict]


class FakeChatServer:
    def __init__(self, reply: Reply):
        self.reply = reply
        self.requests: list[dict] = []  # {path, headers, body}
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                outer.requests.append(
                    {"path": self.path, "headers": dict(self.headers), "body": body}
                )
                prompt = body["messages"][-1]["content"]
                r = outer.reply(prompt)
                status = r.get("status", 200)
                if status != 200:
                    payload = {"error": {"message": r.get("error", "boom")}}
                elif self.path.endswith("/chat/completions"):
                    msg = {"role": "assistant", "content": r.get("content", "")}
                    for k in ("reasoning_content", "reasoning"):
                        if k in r:
                            msg[k] = r[k]
                    payload = {
                        "model": r.get("model", body["model"]),
                        "choices": [{"message": msg, "finish_reason": "stop"}],
                        "usage": r.get(
                            "usage",
                            {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
                        ),
                    }
                elif self.path.endswith("/messages"):
                    blocks = []
                    if "thinking" in r:
                        blocks.append({"type": "thinking", "thinking": r["thinking"]})
                    blocks.append({"type": "text", "text": r.get("content", "")})
                    payload = {
                        "model": body["model"],
                        "content": blocks,
                        "stop_reason": "end_turn",
                        "usage": r.get("usage", {"input_tokens": 9, "output_tokens": 4}),
                    }
                else:
                    status, payload = 404, {"error": "no route"}
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

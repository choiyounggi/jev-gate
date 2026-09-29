"""A fake TypeSafe-compatible server so the model layer of both hooks can be tested deterministically,
on any machine, without ollaya. It records every request body and returns whatever answers the test
configures."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


class FakeSystemOne:
    def __init__(self):
        self.requests = []
        self.answers = {}
        self.status = 200
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/systemone"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                try:
                    fake.requests.append(json.loads(body))
                except json.JSONDecodeError:
                    fake.requests.append({"raw": body.decode("utf-8", "replace")})
                payload = json.dumps({"model": "fake", "answers": fake.answers, "usage": {"input_tokens": 1, "output_tokens": 0}}).encode()
                self.send_response(fake.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        return H

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake_server():
    s = FakeSystemOne()
    yield s
    s.close()

"""A local server that speaks TypeSafe's System One HTTP API.

It implements ``POST /v1/systemone`` and ``GET /v1/models`` with the same
request validation, error statuses (401, 422) and answer shapes as the real
service, backed by any local adapter. Pointing the official SDK at it
(``base_url=http://127.0.0.1:PORT``) exercises the exact client path used for
real Jev runs, including latency measurement, without an API key or cost.
"""

from __future__ import annotations

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from streamdecisionbench.adapters.base import Adapter
from streamdecisionbench.jev import ContractError, validate_request, validate_response

MOCK_MODEL = "jev-mock-0.1"


def _handler(backend_factory: Callable[[], Adapter], latency_ms: float, jitter_ms: float, api_key: str | None):
    local = threading.local()
    rng = random.Random(0)
    lock = threading.Lock()

    def backend() -> Adapter:
        if not hasattr(local, "adapter"):
            local.adapter = backend_factory()
        return local.adapter

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # quiet
            return None

        def _send(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self) -> bool:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or not header[7:].strip():
                return False
            return api_key is None or header[7:].strip() == api_key

        def do_GET(self) -> None:
            if self.path.rstrip("/") != "/v1/models":
                self._send(404, {"detail": "not found"})
                return
            if not self._authorised():
                self._send(401, {"detail": "missing or invalid API key"})
                return
            self._send(
                200,
                {"models": [{"name": MOCK_MODEL, "description": "Local Jev-compatible mock", "release_date": "2026-09-25"}]},
            )

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/v1/systemone":
                self._send(404, {"detail": "not found"})
                return
            if not self._authorised():
                self._send(401, {"detail": "missing or invalid API key"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
                if not isinstance(body, dict) or not isinstance(body.get("model"), str):
                    raise ContractError("model is required")
                request = {"state": body.get("state"), "questions": body.get("questions")}
                validate_request(request)
            except (json.JSONDecodeError, ContractError) as error:
                self._send(422, {"detail": str(error)})
                return
            if latency_ms or jitter_ms:
                with lock:
                    delay = max(0.0, rng.gauss(latency_ms, jitter_ms))
                time.sleep(delay / 1000)
            response = backend().system_one(request)
            try:
                validate_response(response, request["questions"])
            except ContractError as error:  # a broken backend is a server fault
                self._send(500, {"detail": f"backend broke the contract: {error}"})
                return
            self._send(
                200,
                {
                    "model": MOCK_MODEL,
                    "answers": response["answers"],
                    "usage": {"input_tokens": max(1, len(raw) // 4), "output_tokens": 10 * len(request["questions"])},
                },
            )

    return Handler


def serve(
    backend_factory: Callable[[], Adapter],
    host: str = "127.0.0.1",
    port: int = 8787,
    latency_ms: float = 0.0,
    jitter_ms: float = 0.0,
    api_key: str | None = None,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), _handler(backend_factory, latency_ms, jitter_ms, api_key))
    server.daemon_threads = True
    return server


def serve_in_background(backend_factory: Callable[[], Adapter], **kwargs: Any) -> tuple[ThreadingHTTPServer, str]:
    server = serve(backend_factory, **{"port": 0, **kwargs})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"

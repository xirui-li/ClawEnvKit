#!/usr/bin/env python3
"""LLM API Proxy — intercepts and logs all LLM calls for trajectory capture.

Runs inside Docker containers alongside mock services. Forwards requests
to the real LLM API while recording full request/response to JSONL.

Usage:
    LLM_PROXY_TARGET=https://openrouter.ai/api/v1 python3 llm_proxy.py &

Env vars:
    LLM_PROXY_TARGET   — real API base URL (required)
    LLM_PROXY_PORT     — listen port (default 9201)
    LLM_PROXY_LOG      — output JSONL path (default /logs/llm_trajectory.jsonl)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error

TARGET = os.environ.get("LLM_PROXY_TARGET", "")
PORT = int(os.environ.get("LLM_PROXY_PORT", "9201"))
LOG_FILE = os.environ.get("LLM_PROXY_LOG", "/logs/llm_trajectory.jsonl")

_lock = threading.Lock()
_start_time = time.time()
_call_count = 0


def _log_stderr(msg):
    print(f"[llm-proxy] {msg}", file=sys.stderr, flush=True)


def _redact_key(headers: dict) -> dict:
    """Redact API keys from headers for safe logging."""
    safe = dict(headers)
    for k in ("Authorization", "authorization", "x-api-key"):
        if k in safe:
            v = safe[k]
            safe[k] = v[:15] + "..." if len(v) > 15 else "***"
    return safe


def _write_trajectory(record: dict):
    """Thread-safe append to JSONL trajectory file."""
    with _lock:
        try:
            os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            _log_stderr(f"Failed to write trajectory: {e}")


class ProxyHandler(BaseHTTPRequestHandler):
    """Forward LLM API requests, log request + response."""

    def log_message(self, format, *args):
        """Suppress default access log."""
        pass

    def do_POST(self):
        global _call_count
        _call_count += 1
        call_id = _call_count

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        request_body = self.rfile.read(content_length) if content_length else b""

        # Parse request JSON (for logging)
        try:
            req_json = json.loads(request_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            req_json = {"_raw": request_body.decode("utf-8", errors="replace")[:500]}

        # Force non-streaming (simpler proxy, fine for eval)
        modified_body = request_body
        if req_json.get("stream"):
            req_json["stream"] = False
            modified_body = json.dumps(req_json).encode("utf-8")

        # Build target URL — avoid double /v1 when TARGET already ends with /v1
        target_base = TARGET.rstrip("/")
        req_path = self.path
        if target_base.endswith("/v1") and req_path.startswith("/v1"):
            req_path = req_path[3:]  # strip /v1 prefix from path
        target_url = target_base + req_path

        # Forward headers (preserve auth)
        forward_headers = {
            "Content-Type": self.headers.get("Content-Type", "application/json"),
        }
        for h in ("Authorization", "x-api-key", "anthropic-version",
                   "anthropic-beta", "OpenAI-Organization"):
            if self.headers.get(h):
                forward_headers[h] = self.headers.get(h)

        # Forward request
        t0 = time.time()
        resp_status = 0
        resp_json = {}
        error_msg = ""

        try:
            req = urllib.request.Request(
                target_url,
                data=modified_body,
                headers=forward_headers,
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=180)
            resp_body = resp.read()
            resp_status = resp.status

            try:
                resp_json = json.loads(resp_body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                resp_json = {"_raw": resp_body.decode("utf-8", errors="replace")[:2000]}

            # Return response to agent
            self.send_response(resp_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

        except urllib.error.HTTPError as e:
            resp_status = e.code
            error_body = e.read()
            error_msg = error_body.decode("utf-8", errors="replace")[:500]
            try:
                resp_json = json.loads(error_body)
            except Exception:
                resp_json = {"_error": error_msg}

            self.send_response(resp_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_body)))
            self.end_headers()
            self.wfile.write(error_body)

        except Exception as e:
            error_msg = str(e)[:200]
            self.send_response(502)
            err = json.dumps({"error": error_msg}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

        latency_ms = (time.time() - t0) * 1000

        # Extract model name
        model = req_json.get("model", "unknown")

        # Log trajectory
        _write_trajectory({
            "call_id": call_id,
            "timestamp": round(time.time() - _start_time, 3),
            "path": self.path,
            "model": model,
            "request": {
                "messages": req_json.get("messages", []),
                "tools": [t.get("function", {}).get("name", "") for t in req_json.get("tools", [])],
                "max_tokens": req_json.get("max_tokens") or req_json.get("max_completion_tokens"),
                "temperature": req_json.get("temperature"),
            },
            "response": {
                "status": resp_status,
                "choices": resp_json.get("choices", []),
                "usage": resp_json.get("usage", {}),
                "error": resp_json.get("error") if resp_status >= 400 else None,
            },
            "latency_ms": round(latency_ms, 1),
        })

        _log_stderr(f"#{call_id} {model} {self.path} → {resp_status} ({latency_ms:.0f}ms)")

    def do_GET(self):
        """Forward GET requests (e.g., /v1/models)."""
        target_base = TARGET.rstrip("/")
        req_path = self.path
        if target_base.endswith("/v1") and req_path.startswith("/v1"):
            req_path = req_path[3:]
        target_url = target_base + req_path
        forward_headers = {}
        for h in ("Authorization", "x-api-key"):
            if self.headers.get(h):
                forward_headers[h] = self.headers.get(h)

        try:
            req = urllib.request.Request(target_url, headers=forward_headers)
            resp = urllib.request.urlopen(req, timeout=30)
            body = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            err = json.dumps({"error": str(e)[:200]}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err)


class ThreadedHTTPServer(HTTPServer):
    """Handle requests in separate threads."""
    daemon_threads = True

    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle, args=(request, client_address))
        t.daemon = True
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


if __name__ == "__main__":
    if not TARGET:
        _log_stderr("ERROR: LLM_PROXY_TARGET not set")
        sys.exit(1)

    server = ThreadedHTTPServer(("127.0.0.1", PORT), ProxyHandler)
    _log_stderr(f"Listening on :{PORT}, forwarding to {TARGET}")
    _log_stderr(f"Trajectory log: {LOG_FILE}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log_stderr(f"Stopped. {_call_count} calls logged.")
        server.shutdown()

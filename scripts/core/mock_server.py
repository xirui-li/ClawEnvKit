"""Mock API server for simulating external services in Docker containers.

Runs a lightweight HTTP server that records all incoming requests and
validates them against expected call patterns. Used for testing agent
interactions with Slack, Discord, Hue, HomeAssistant, etc.

Usage inside Docker:
    python3 /workspace/mock_server/server.py &
    # agent runs its code, hitting http://localhost:8080/...
    python3 /workspace/mock_server/verify.py

The mock server:
1. Accepts ANY request to ANY path
2. Returns configured responses (from responses.json)
3. Records all requests to /tmp/mock_requests.jsonl
4. verify.py checks recorded requests against expected_calls.json
"""

from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional


# --- Mock Server ---


class MockAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler that records requests and returns configured responses."""

    # Class-level config, set before server starts
    responses: dict = {}      # path+method → response config
    default_response: dict = {"status": 200, "body": {"ok": True}}
    request_log: list = []    # recorded requests

    def _get_response_config(self, method: str, path: str) -> dict:
        """Find matching response config for this request."""
        # Try exact match first: "POST /api/chat.postMessage"
        key = f"{method} {path}"
        if key in self.responses:
            return self.responses[key]
        # Try path-only match
        if path in self.responses:
            return self.responses[path]
        # Try prefix match for path patterns
        for pattern, config in self.responses.items():
            if path.startswith(pattern.split("*")[0]) if "*" in pattern else False:
                return config
        return self.default_response

    def _handle_request(self, method: str):
        """Generic handler for all HTTP methods."""
        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

        # Parse body as JSON if possible
        try:
            body_json = json.loads(body) if body else None
        except json.JSONDecodeError:
            body_json = None

        # Record request
        record = {
            "method": method,
            "path": self.path,
            "headers": dict(self.headers),
            "body": body_json if body_json else body,
        }
        self.request_log.append(record)

        # Write to log file (append)
        log_path = os.environ.get("MOCK_LOG_PATH", "/tmp/mock_requests.jsonl")
        with open(log_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Get configured response
        config = self._get_response_config(method, self.path)
        status = config.get("status", 200)
        resp_body = config.get("body", {"ok": True})

        # Send response
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp_body, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def do_PUT(self):
        self._handle_request("PUT")

    def do_DELETE(self):
        self._handle_request("DELETE")

    def do_PATCH(self):
        self._handle_request("PATCH")

    def log_message(self, format, *args):
        """Suppress default logging to stderr."""
        pass


def start_mock_server(
    port: int = 8080,
    responses_file: Optional[str] = None,
    log_path: str = "/tmp/mock_requests.jsonl",
    background: bool = True,
) -> HTTPServer:
    """Start mock API server.

    Args:
        port: Port to listen on
        responses_file: Path to JSON file mapping path+method → response
        log_path: Path to write request log
        background: If True, run in background thread
    """
    # Load response configs
    if responses_file and os.path.exists(responses_file):
        with open(responses_file) as f:
            MockAPIHandler.responses = json.load(f)
    else:
        MockAPIHandler.responses = {}

    MockAPIHandler.request_log = []
    os.environ["MOCK_LOG_PATH"] = log_path

    # Clear previous log
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    open(log_path, "w").close()

    server = HTTPServer(("0.0.0.0", port), MockAPIHandler)

    if background:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    else:
        server.serve_forever()

    return server


# --- Verification ---


def verify_calls(
    expected_calls_file: str,
    log_path: str = "/tmp/mock_requests.jsonl",
) -> tuple[bool, list[str]]:
    """Verify recorded requests match expected calls.

    Args:
        expected_calls_file: Path to JSON file with expected call patterns
        log_path: Path to request log written by mock server

    Returns:
        (all_passed, list of issue strings)
    """
    # Load expected calls
    with open(expected_calls_file) as f:
        expected = json.load(f)

    # Load recorded requests
    recorded = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    recorded.append(json.loads(line))

    issues = []

    # Check each expected call
    for i, exp in enumerate(expected.get("calls", [])):
        exp_method = exp.get("method", "POST")
        exp_path = exp.get("path")
        exp_body_contains = exp.get("body_contains", {})  # key-value pairs that must be in body

        # Find matching recorded request
        matched = False
        for rec in recorded:
            if rec["method"] != exp_method:
                continue
            if exp_path and not rec["path"].startswith(exp_path):
                continue

            # Check body contains
            if exp_body_contains and isinstance(rec.get("body"), dict):
                all_match = True
                for key, val in exp_body_contains.items():
                    if rec["body"].get(key) != val:
                        all_match = False
                        break
                if not all_match:
                    continue

            matched = True
            break

        if not matched:
            issues.append(
                f"Expected call #{i+1} not found: {exp_method} {exp_path} "
                f"with body containing {exp_body_contains}"
            )

    # Check minimum call count
    min_calls = expected.get("min_calls")
    if min_calls and len(recorded) < min_calls:
        issues.append(f"Expected at least {min_calls} API calls, got {len(recorded)}")

    # Check no unexpected paths (if strict mode)
    if expected.get("strict", False):
        allowed_paths = {c.get("path") for c in expected.get("calls", [])}
        for rec in recorded:
            if not any(rec["path"].startswith(p) for p in allowed_paths if p):
                issues.append(f"Unexpected API call: {rec['method']} {rec['path']}")

    return len(issues) == 0, issues


# --- Standalone entry point (for running inside Docker) ---


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mock API Server")
    subparsers = parser.add_subparsers(dest="command")

    # serve command
    serve = subparsers.add_parser("serve", help="Start mock server")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--responses", help="Path to responses.json")
    serve.add_argument("--log", default="/tmp/mock_requests.jsonl")

    # verify command
    verify = subparsers.add_parser("verify", help="Verify recorded calls")
    verify.add_argument("--expected", required=True, help="Path to expected_calls.json")
    verify.add_argument("--log", default="/tmp/mock_requests.jsonl")

    args = parser.parse_args()

    if args.command == "serve":
        print(f"Starting mock server on port {args.port}...", file=sys.stderr)
        start_mock_server(
            port=args.port,
            responses_file=args.responses,
            log_path=args.log,
            background=False,
        )
    elif args.command == "verify":
        passed, issues = verify_calls(args.expected, args.log)
        result = {"passed": passed, "issues": issues}
        print(json.dumps(result, indent=2))
        sys.exit(0 if passed else 1)
    else:
        parser.print_help()

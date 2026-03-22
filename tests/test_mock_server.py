"""Tests for scripts/core/mock_server.py"""

import json
import time
import urllib.request
import urllib.error

import pytest

from scripts.core.mock_server import start_mock_server, verify_calls


@pytest.fixture
def mock_server(tmp_path):
    """Start a mock server on a random-ish port for testing."""
    log_path = str(tmp_path / "requests.jsonl")
    responses_file = tmp_path / "responses.json"
    responses_file.write_text(json.dumps({
        "POST /api/chat.postMessage": {
            "status": 200,
            "body": {"ok": True, "ts": "1234567890.123456"},
        },
        "GET /api/users.list": {
            "status": 200,
            "body": {"ok": True, "members": [{"id": "U1", "name": "alice"}]},
        },
        "PUT /api/lights/1/state": {
            "status": 200,
            "body": [{"success": {"/lights/1/state/on": True}}],
        },
    }))

    port = 18765
    server = start_mock_server(
        port=port,
        responses_file=str(responses_file),
        log_path=log_path,
        background=True,
    )
    time.sleep(0.1)  # let server start
    yield port, log_path, server
    server.shutdown()


class TestMockServer:
    def test_post_request_recorded(self, mock_server):
        port, log_path, _ = mock_server
        data = json.dumps({"channel": "#general", "text": "hello"}).encode()
        req = urllib.request.Request(
            f"http://localhost:{port}/api/chat.postMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req)
        body = json.loads(resp.read())

        assert resp.status == 200
        assert body["ok"] is True
        assert body["ts"] == "1234567890.123456"

        # Check log
        with open(log_path) as f:
            records = [json.loads(l) for l in f if l.strip()]
        assert len(records) == 1
        assert records[0]["method"] == "POST"
        assert records[0]["path"] == "/api/chat.postMessage"
        assert records[0]["body"]["channel"] == "#general"

    def test_get_request(self, mock_server):
        port, log_path, _ = mock_server
        resp = urllib.request.urlopen(f"http://localhost:{port}/api/users.list")
        body = json.loads(resp.read())

        assert body["ok"] is True
        assert body["members"][0]["name"] == "alice"

    def test_unknown_path_returns_default(self, mock_server):
        port, log_path, _ = mock_server
        resp = urllib.request.urlopen(f"http://localhost:{port}/unknown/path")
        body = json.loads(resp.read())

        assert resp.status == 200
        assert body["ok"] is True  # default response

    def test_multiple_requests_logged(self, mock_server):
        port, log_path, _ = mock_server

        # Make 3 requests
        for i in range(3):
            data = json.dumps({"text": f"msg-{i}"}).encode()
            req = urllib.request.Request(
                f"http://localhost:{port}/api/chat.postMessage",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req)

        with open(log_path) as f:
            records = [json.loads(l) for l in f if l.strip()]
        assert len(records) == 3


class TestVerifyCalls:
    def _write_log(self, log_path, records):
        with open(log_path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_all_expected_calls_found(self, tmp_path):
        log_path = str(tmp_path / "log.jsonl")
        expected_path = str(tmp_path / "expected.json")

        self._write_log(log_path, [
            {"method": "POST", "path": "/api/chat.postMessage", "body": {"channel": "#general", "text": "hello"}},
        ])

        with open(expected_path, "w") as f:
            json.dump({
                "calls": [
                    {"method": "POST", "path": "/api/chat.postMessage", "body_contains": {"channel": "#general"}},
                ],
            }, f)

        passed, issues = verify_calls(expected_path, log_path)
        assert passed is True
        assert issues == []

    def test_missing_call_detected(self, tmp_path):
        log_path = str(tmp_path / "log.jsonl")
        expected_path = str(tmp_path / "expected.json")

        self._write_log(log_path, [])  # no calls made

        with open(expected_path, "w") as f:
            json.dump({
                "calls": [
                    {"method": "POST", "path": "/api/chat.postMessage", "body_contains": {"channel": "#general"}},
                ],
            }, f)

        passed, issues = verify_calls(expected_path, log_path)
        assert passed is False
        assert any("not found" in i for i in issues)

    def test_wrong_body_detected(self, tmp_path):
        log_path = str(tmp_path / "log.jsonl")
        expected_path = str(tmp_path / "expected.json")

        self._write_log(log_path, [
            {"method": "POST", "path": "/api/chat.postMessage", "body": {"channel": "#random", "text": "hello"}},
        ])

        with open(expected_path, "w") as f:
            json.dump({
                "calls": [
                    {"method": "POST", "path": "/api/chat.postMessage", "body_contains": {"channel": "#general"}},
                ],
            }, f)

        passed, issues = verify_calls(expected_path, log_path)
        assert passed is False

    def test_min_calls_check(self, tmp_path):
        log_path = str(tmp_path / "log.jsonl")
        expected_path = str(tmp_path / "expected.json")

        self._write_log(log_path, [
            {"method": "POST", "path": "/api/send", "body": {}},
        ])

        with open(expected_path, "w") as f:
            json.dump({"calls": [], "min_calls": 3}, f)

        passed, issues = verify_calls(expected_path, log_path)
        assert passed is False
        assert any("at least 3" in i for i in issues)

    def test_strict_mode_rejects_unexpected(self, tmp_path):
        log_path = str(tmp_path / "log.jsonl")
        expected_path = str(tmp_path / "expected.json")

        self._write_log(log_path, [
            {"method": "POST", "path": "/api/chat.postMessage", "body": {"text": "hi"}},
            {"method": "GET", "path": "/api/unexpected", "body": None},
        ])

        with open(expected_path, "w") as f:
            json.dump({
                "calls": [
                    {"method": "POST", "path": "/api/chat.postMessage"},
                ],
                "strict": True,
            }, f)

        passed, issues = verify_calls(expected_path, log_path)
        assert passed is False
        assert any("Unexpected" in i for i in issues)

    def test_multiple_calls_matched(self, tmp_path):
        log_path = str(tmp_path / "log.jsonl")
        expected_path = str(tmp_path / "expected.json")

        self._write_log(log_path, [
            {"method": "GET", "path": "/api/users.list", "body": None},
            {"method": "POST", "path": "/api/chat.postMessage", "body": {"channel": "#general", "text": "hello"}},
            {"method": "PUT", "path": "/api/lights/1/state", "body": {"on": True}},
        ])

        with open(expected_path, "w") as f:
            json.dump({
                "calls": [
                    {"method": "GET", "path": "/api/users.list"},
                    {"method": "POST", "path": "/api/chat.postMessage", "body_contains": {"text": "hello"}},
                    {"method": "PUT", "path": "/api/lights/1/state", "body_contains": {"on": True}},
                ],
            }, f)

        passed, issues = verify_calls(expected_path, log_path)
        assert passed is True

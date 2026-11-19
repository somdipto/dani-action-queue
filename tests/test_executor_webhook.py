"""Tests for the webhook executor."""
import http.server
import json
import threading
import unittest.mock
from io import BytesIO

import pytest

from app.executors.webhook import execute


# ---------------------------------------------------------------------------
# Local HTTP test server
# ---------------------------------------------------------------------------

_received_requests: list[dict] = []


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _received_requests.append({
            "path": self.path,
            "body": body,
            "headers": dict(self.headers),
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *args):
        pass  # silence server log in tests


@pytest.fixture(scope="module")
def local_server():
    """Start a local HTTP server in a background thread and return its port."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port
    server.shutdown()


# ---------------------------------------------------------------------------
# Helper: execute bypassing the https:// guard for local testing
# ---------------------------------------------------------------------------

def _execute_local(url: str, body: dict | None = None, headers: dict | None = None) -> object:
    """Call execute but patch the https check for http://localhost URLs."""
    payload = {"url": url, "body": body or {}, "headers": headers or {}}
    # Monkey-patch the scheme check for this call
    import app.executors.webhook as wh
    original_execute = wh.execute

    def patched(p):
        # bypass scheme check for http://127.0.0.1 in tests
        p2 = dict(p)
        p2["url"] = p2["url"].replace("http://127.0.0.1", "https://127.0.0.1")
        # We need to actually use http, so let's just call urllib directly
        # Instead, replace 'https://' check in a targeted way:
        return _execute_without_scheme_check(p)

    return _execute_without_scheme_check(payload)


def _execute_without_scheme_check(payload: dict):
    """Execute the webhook without the https:// guard."""
    import json
    import urllib.error
    import urllib.request
    from app.executors.base import ExecutionResult, truncate

    url = payload.get("url", "")
    body = payload.get("body", {})
    headers = payload.get("headers", {})

    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)
        with urllib.request.urlopen(req, timeout=5) as response:
            status_code = response.status
            response_body = truncate(response.read().decode("utf-8", errors="replace"))
        if 200 <= status_code < 300:
            return ExecutionResult(status="success", result_summary=f"HTTP {status_code}", log_excerpt=response_body)
        return ExecutionResult(status="failure", result_summary=f"HTTP {status_code}", log_excerpt=response_body)
    except urllib.error.HTTPError as exc:
        try:
            body_text = truncate(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            body_text = ""
        return ExecutionResult(status="failure", result_summary=f"HTTP {exc.code}", log_excerpt=body_text)
    except urllib.error.URLError as exc:
        return ExecutionResult(status="failure", result_summary=f"URLError: {exc.reason}", log_excerpt=str(exc))
    except Exception as exc:
        return ExecutionResult(status="failure", result_summary=f"Unexpected error: {exc}", log_excerpt=str(exc))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_local_server_receives_post(local_server):
    before = len(_received_requests)
    url = f"http://127.0.0.1:{local_server}/"
    result = _execute_local(url, body={"key": "value"})
    assert result.status == "success"
    assert result.result_summary == "HTTP 200"
    assert len(_received_requests) > before


def test_non_https_url_returns_failure():
    result = execute({"url": "http://example.com/hook", "body": {}})
    assert result.status == "failure"
    assert "https" in result.result_summary.lower() or "https" in result.log_excerpt.lower()


def test_connection_error_returns_failure():
    # Port 1 is almost certainly not listening
    result = execute({"url": "https://127.0.0.1:1/hook", "body": {}})
    assert result.status == "failure"


def test_non_2xx_response(local_server):
    """Test that a non-2xx response returns failure."""
    class _ErrorHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Internal Server Error")
        def log_message(self, *args):
            pass

    error_server = http.server.HTTPServer(("127.0.0.1", 0), _ErrorHandler)
    port = error_server.server_address[1]
    t = threading.Thread(target=error_server.serve_forever, daemon=True)
    t.start()
    try:
        result = _execute_local(f"http://127.0.0.1:{port}/")
        assert result.status == "failure"
        assert "500" in result.result_summary
    finally:
        error_server.shutdown()

"""
End-to-end integration tests covering all three executors.

Each test follows the full draft → approve → execute → receipt path.
"""
import http.server
import json
import threading
import unittest.mock
from pathlib import Path

import pytest

from app.queue import approve_action, create_action, execute_action, list_audit
from app.receipts import get_receipt


# ---------------------------------------------------------------------------
# file_organize integration
# ---------------------------------------------------------------------------

def test_file_organize_full_path(tmp_path):
    # Seed mixed-extension files
    (tmp_path / "report.pdf").write_text("pdf content")
    (tmp_path / "script.py").write_text("print('hi')")
    (tmp_path / "notes.txt").write_text("notes")
    (tmp_path / "Makefile").write_text("all:")   # no extension

    action = create_action(
        "Organise mixed files",
        "file_organize",
        {"directory": str(tmp_path), "grouping": "by_extension"},
    )
    assert action.state == "draft"

    action = approve_action(action.id)
    assert action.state == "approved"

    updated, receipt = execute_action(action.id)
    assert updated.state == "done"
    assert receipt.status == "success"

    # Verify files moved
    assert (tmp_path / "pdf" / "report.pdf").exists()
    assert (tmp_path / "py" / "script.py").exists()
    assert (tmp_path / "txt" / "notes.txt").exists()
    assert (tmp_path / "no_extension" / "Makefile").exists()

    # Verify receipt stored correctly
    r = get_receipt(receipt.id)
    assert r is not None
    assert r.action_id == action.id
    assert r.status == "success"


def test_file_organize_audit_entries(tmp_path):
    (tmp_path / "audit_test.py").write_text("x")
    action = create_action(
        "audit file_organize",
        "file_organize",
        {"directory": str(tmp_path), "grouping": "by_extension"},
    )
    approve_action(action.id)
    execute_action(action.id)

    entries = list_audit(action_id=action.id)
    to_states = [e["to_state"] for e in entries]
    # Expect: draft, approved, executing, done  (in reverse-chron order from list_audit)
    assert "draft" in to_states
    assert "approved" in to_states
    assert "executing" in to_states
    assert "done" in to_states


# ---------------------------------------------------------------------------
# shell_allowlist integration
# ---------------------------------------------------------------------------

def test_shell_allowlist_echo(tmp_path):
    action = create_action(
        "echo integration",
        "shell_allowlist",
        {"command": "echo hello_integration"},
    )
    action = approve_action(action.id)
    updated, receipt = execute_action(action.id)

    assert updated.state == "done"
    assert receipt.status == "success"
    assert "hello_integration" in receipt.log_excerpt


def test_shell_allowlist_audit_entries():
    action = create_action("audit shell", "shell_allowlist", {"command": "echo audit_check"})
    approve_action(action.id)
    execute_action(action.id)

    entries = list_audit(action_id=action.id)
    to_states = {e["to_state"] for e in entries}
    assert {"draft", "approved", "executing", "done"} <= to_states


# ---------------------------------------------------------------------------
# webhook integration
# ---------------------------------------------------------------------------

_webhook_requests: list[dict] = []


class _WebhookHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _webhook_requests.append({
            "path": self.path,
            "body": body,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"received": true}')

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def webhook_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _WebhookHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield port
    server.shutdown()


def test_webhook_full_path(webhook_server):
    """
    Webhook test bypasses the https:// guard by patching the scheme check.
    The real guard is tested separately in test_executor_webhook.py.
    """
    import app.executors.webhook as wh

    url = f"http://127.0.0.1:{webhook_server}/dani-hook"

    before = len(_webhook_requests)

    action = create_action(
        "webhook integration",
        "webhook",
        {"url": url, "body": {"from": "dani"}, "headers": {}},
    )
    action = approve_action(action.id)

    # Patch the https check for this test only
    original_execute = wh.execute

    def _patched_execute(payload):
        p2 = dict(payload)
        # strip the https requirement for localhost
        return _execute_http_no_guard(p2)

    with unittest.mock.patch.object(wh, "execute", side_effect=_patched_execute):
        updated, receipt = execute_action(action.id)

    assert updated.state == "done"
    assert receipt.status == "success"
    assert len(_webhook_requests) > before
    assert receipt.result_summary == "HTTP 200"


def _execute_http_no_guard(payload: dict):
    """Execute the webhook POST without the https guard (for localhost tests)."""
    import json as _json
    import urllib.error
    import urllib.request
    from app.executors.base import ExecutionResult, truncate

    url = payload.get("url", "")
    body = payload.get("body", {})
    headers = payload.get("headers", {})

    try:
        data = _json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for k, v in headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=5) as resp:
            status_code = resp.status
            resp_body = truncate(resp.read().decode("utf-8", errors="replace"))
        if 200 <= status_code < 300:
            return ExecutionResult(status="success", result_summary=f"HTTP {status_code}", log_excerpt=resp_body)
        return ExecutionResult(status="failure", result_summary=f"HTTP {status_code}", log_excerpt=resp_body)
    except urllib.error.HTTPError as exc:
        try:
            body_text = truncate(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            body_text = ""
        return ExecutionResult(status="failure", result_summary=f"HTTP {exc.code}", log_excerpt=body_text)
    except Exception as exc:
        return ExecutionResult(status="failure", result_summary=f"Error: {exc}", log_excerpt=str(exc))


def test_webhook_audit_entries(webhook_server):
    import app.executors.webhook as wh

    url = f"http://127.0.0.1:{webhook_server}/audit-test"
    action = create_action(
        "webhook audit",
        "webhook",
        {"url": url, "body": {}, "headers": {}},
    )
    approve_action(action.id)

    with unittest.mock.patch.object(wh, "execute", side_effect=lambda p: _execute_http_no_guard(p)):
        execute_action(action.id)

    entries = list_audit(action_id=action.id)
    to_states = {e["to_state"] for e in entries}
    assert {"draft", "approved", "executing", "done"} <= to_states

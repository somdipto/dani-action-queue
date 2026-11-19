"""Tests for the CLI (app/cli.py)."""
import json
import sys
from io import StringIO

import pytest

from app.cli import main


def run_cli(*args: str) -> tuple[str, int]:
    """Run the CLI, capture stdout, return (output, exit_code)."""
    buf = StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    exit_code = 0
    try:
        main(list(args))
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.stdout = old_stdout
    return buf.getvalue(), exit_code


def test_action_create_outputs_draft():
    out, code = run_cli(
        "action", "create",
        "--title", "cli test",
        "--executor", "shell_allowlist",
        "--payload", '{"command": "echo cli"}',
    )
    assert code == 0
    data = json.loads(out)
    assert data["state"] == "draft"
    assert data["title"] == "cli test"


def test_action_approve_and_list():
    out, _ = run_cli(
        "action", "create",
        "--title", "approve cli",
        "--executor", "shell_allowlist",
        "--payload", '{"command": "echo approve"}',
    )
    action_id = json.loads(out)["id"]

    out_approve, code = run_cli("action", "approve", action_id)
    assert code == 0
    assert json.loads(out_approve)["state"] == "approved"

    out_list, _ = run_cli("action", "list", "--state", "approved")
    ids = {a["id"] for a in json.loads(out_list)}
    assert action_id in ids


def test_action_reject():
    out, _ = run_cli(
        "action", "create",
        "--title", "reject cli",
        "--executor", "shell_allowlist",
        "--payload", '{"command": "echo reject"}',
    )
    action_id = json.loads(out)["id"]

    out_rej, code = run_cli("action", "reject", action_id, "--reason", "not needed")
    assert code == 0
    data = json.loads(out_rej)
    assert data["state"] == "rejected"
    assert data["reject_reason"] == "not needed"


def test_receipt_list_after_execution():
    out, _ = run_cli(
        "action", "create",
        "--title", "receipt cli",
        "--executor", "shell_allowlist",
        "--payload", '{"command": "echo receipt"}',
    )
    action_id = json.loads(out)["id"]
    run_cli("action", "approve", action_id)
    run_cli("action", "execute", action_id)

    out_receipts, code = run_cli("receipt", "list", "--action-id", action_id)
    assert code == 0
    recs = json.loads(out_receipts)
    assert len(recs) >= 1
    assert recs[0]["action_id"] == action_id


def test_unknown_executor_exits_1():
    buf = StringIO()
    old_stderr = sys.stderr
    sys.stderr = buf
    _, code = run_cli(
        "action", "create",
        "--title", "bad executor",
        "--executor", "shell_allowlist",  # valid for argparse
        "--payload", '{"command": "echo hi"}',
    )
    sys.stderr = old_stderr
    # We test truly unknown by bypassing argparse choices:
    # patch create_action to raise ValueError for unknown executor
    # Actually, argparse enforces choices so we test via direct call:
    from app.cli import cmd_action_create
    import argparse
    args = argparse.Namespace(title="t", executor="nonexistent", payload='{}')
    with pytest.raises(SystemExit) as exc_info:
        cmd_action_create(args)
    assert exc_info.value.code == 1

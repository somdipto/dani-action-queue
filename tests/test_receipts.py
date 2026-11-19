"""Tests for receipts.py."""
from datetime import datetime, timezone

from app.executors.base import ExecutionResult
from app.receipts import get_receipt, list_receipts, write_receipt


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_write_and_get_receipt():
    result = ExecutionResult(status="success", result_summary="All good.", log_excerpt="done")
    r = write_receipt(
        action_id="action-001",
        executor="shell_allowlist",
        payload_snapshot={"command": "echo hi"},
        started_at=_now(),
        finished_at=_now(),
        result=result,
    )
    assert r.id is not None
    fetched = get_receipt(r.id)
    assert fetched is not None
    assert fetched.id == r.id
    assert fetched.status == "success"


def test_get_receipt_nonexistent_returns_none():
    assert get_receipt("no-such-id") is None


def test_list_receipts_filter_by_action_id():
    r1 = ExecutionResult(status="success", result_summary="ok", log_excerpt="")
    r2 = ExecutionResult(status="failure", result_summary="bad", log_excerpt="err")
    receipt1 = write_receipt("action-aaa", "shell_allowlist", {}, _now(), _now(), r1)
    receipt2 = write_receipt("action-bbb", "shell_allowlist", {}, _now(), _now(), r2)

    by_a = list_receipts(action_id="action-aaa")
    ids = {r.id for r in by_a}
    assert receipt1.id in ids
    assert receipt2.id not in ids


def test_list_receipts_filter_by_status():
    r_ok = ExecutionResult(status="success", result_summary="ok", log_excerpt="")
    r_bad = ExecutionResult(status="failure", result_summary="bad", log_excerpt="err")
    ok_receipt = write_receipt("action-ccc", "shell_allowlist", {}, _now(), _now(), r_ok)
    fail_receipt = write_receipt("action-ccc", "shell_allowlist", {}, _now(), _now(), r_bad)

    successes = list_receipts(status="success")
    failures = list_receipts(status="failure")
    success_ids = {r.id for r in successes}
    failure_ids = {r.id for r in failures}
    assert ok_receipt.id in success_ids
    assert fail_receipt.id in failure_ids
    assert ok_receipt.id not in failure_ids


def test_payload_snapshot_round_trips():
    snapshot = {"command": "echo round-trip", "nested": {"key": 42}}
    result = ExecutionResult(status="success", result_summary="ok", log_excerpt="")
    r = write_receipt("action-ddd", "shell_allowlist", snapshot, _now(), _now(), result)
    fetched = get_receipt(r.id)
    assert fetched.payload_snapshot == snapshot


def test_receipt_integrity_verify_and_tamper_detection():
    import json
    from app.db import get_connection
    from app.receipts import verify_receipt

    result = ExecutionResult(status="success", result_summary="ok", log_excerpt="log")
    r = write_receipt(
        action_id="action-verify",
        executor="shell_allowlist",
        payload_snapshot={"command": "date"},
        started_at=_now(),
        finished_at=_now(),
        result=result,
    )
    assert r.integrity_hash
    assert verify_receipt(r.id) is True

    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE receipts SET result_summary = ? WHERE id = ?", ("forged", r.id)
        )
    conn.close()
    assert verify_receipt(r.id) is False
    assert verify_receipt("no-such-id") is None

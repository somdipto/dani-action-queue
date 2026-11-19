"""
Action CRUD and state machine.

All state transitions are enforced here and append a row to audit_log.
"""
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.db import get_connection

VALID_EXECUTORS = {"file_organize", "shell_allowlist", "webhook"}

TERMINAL_STATES = {"done", "failed", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Action:
    id: str
    title: str
    executor: str
    payload: dict
    state: str
    created_at: str
    decided_at: str | None
    executed_at: str | None
    receipt_id: str | None
    reject_reason: str | None


def _row_to_action(row) -> Action:
    return Action(
        id=row["id"],
        title=row["title"],
        executor=row["executor"],
        payload=json.loads(row["payload"]),
        state=row["state"],
        created_at=row["created_at"],
        decided_at=row["decided_at"],
        executed_at=row["executed_at"],
        receipt_id=row["receipt_id"],
        reject_reason=row["reject_reason"],
    )


def _append_audit(conn, action_id: str, from_state: str, to_state: str, note: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (id, action_id, from_state, to_state, actor, timestamp, note)
        VALUES (?, ?, ?, ?, 'human', ?, ?)
        """,
        (_uuid(), action_id, from_state, to_state, _now(), note),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_action(title: str, executor: str, payload: dict) -> Action:
    if executor not in VALID_EXECUTORS:
        raise ValueError(f"Unknown executor '{executor}'. Must be one of {sorted(VALID_EXECUTORS)}.")

    # file_organize: compute plan at draft time
    if executor == "file_organize":
        from app.executors import file_organize as fo
        plan = fo.plan(payload)
        payload = {**payload, "plan": plan}

    action_id = _uuid()
    now = _now()
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO actions (id, title, executor, payload, state, created_at)
            VALUES (?, ?, ?, ?, 'draft', ?)
            """,
            (action_id, title, executor, json.dumps(payload), now),
        )
        _append_audit(conn, action_id, "none", "draft")
    action = get_action(action_id)
    conn.close()
    return action


def get_action(action_id: str) -> Action | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_action(row)


def list_actions(
    state: str | None = None,
    executor: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Action]:
    query = "SELECT * FROM actions WHERE 1=1"
    params: list = []
    if state:
        query += " AND state = ?"
        params.append(state)
    if executor:
        query += " AND executor = ?"
        params.append(executor)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_action(r) for r in rows]


def approve_action(action_id: str) -> Action:
    conn = get_connection()
    row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    if row is None:
        raise ValueError(f"Action {action_id} not found.")
    action = _row_to_action(row)
    if action.state != "draft":
        raise ValueError(f"Cannot approve action in state '{action.state}'; must be 'draft'.")
    with conn:
        conn.execute(
            "UPDATE actions SET state='approved', decided_at=? WHERE id=?",
            (_now(), action_id),
        )
        _append_audit(conn, action_id, "draft", "approved")
    conn.close()
    return get_action(action_id)


def reject_action(action_id: str, reason: str) -> Action:
    conn = get_connection()
    row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    if row is None:
        raise ValueError(f"Action {action_id} not found.")
    action = _row_to_action(row)
    if action.state in TERMINAL_STATES:
        raise ValueError(f"Cannot reject action in terminal state '{action.state}'.")
    if action.state not in ("draft", "approved"):
        raise ValueError(f"Cannot reject action in state '{action.state}'.")
    with conn:
        conn.execute(
            "UPDATE actions SET state='rejected', decided_at=?, reject_reason=? WHERE id=?",
            (_now(), reason, action_id),
        )
        _append_audit(conn, action_id, action.state, "rejected", note=reason)
    conn.close()
    return get_action(action_id)


def begin_execution(action_id: str) -> Action:
    conn = get_connection()
    row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    if row is None:
        raise ValueError(f"Action {action_id} not found.")
    action = _row_to_action(row)
    if action.state != "approved":
        raise ValueError(f"Cannot execute action in state '{action.state}'; must be 'approved'.")
    with conn:
        conn.execute(
            "UPDATE actions SET state='executing' WHERE id=?",
            (action_id,),
        )
        _append_audit(conn, action_id, "approved", "executing")
    conn.close()
    return get_action(action_id)


def finish_execution(
    action_id: str,
    receipt_id: str,
    status: Literal["done", "failed"],
) -> Action:
    final_state = status  # "done" or "failed"
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE actions SET state=?, executed_at=?, receipt_id=? WHERE id=?",
            (final_state, _now(), receipt_id, action_id),
        )
        _append_audit(conn, action_id, "executing", final_state)
    conn.close()
    return get_action(action_id)


def execute_action(action_id: str) -> tuple:
    """
    Full execution pipeline:
      1. Transition approved → executing.
      2. Dispatch to the correct executor.
      3. Write receipt.
      4. Transition executing → done | failed.

    Returns (updated_action, receipt).
    Raises ValueError if action is not approved.
    """
    from datetime import datetime, timezone
    from app import receipts as receipts_mod
    from app.executors.base import ExecutionResult

    action = begin_execution(action_id)  # raises ValueError if not approved

    started_at = datetime.now(timezone.utc).isoformat()
    result: ExecutionResult

    try:
        if action.executor == "file_organize":
            from app.executors import file_organize as fo
            result = fo.execute(action.payload)
        elif action.executor == "shell_allowlist":
            from app.executors import shell_allowlist as sa
            result = sa.execute(action.payload)
        elif action.executor == "webhook":
            from app.executors import webhook as wh
            result = wh.execute(action.payload)
        else:
            result = ExecutionResult(
                status="failure",
                result_summary=f"Unknown executor: {action.executor}",
                log_excerpt="",
            )
    except Exception as exc:
        result = ExecutionResult(
            status="failure",
            result_summary=f"Executor raised an unexpected exception: {exc}",
            log_excerpt=str(exc),
        )

    finished_at = datetime.now(timezone.utc).isoformat()

    receipt = receipts_mod.write_receipt(
        action_id=action_id,
        executor=action.executor,
        payload_snapshot=action.payload,
        started_at=started_at,
        finished_at=finished_at,
        result=result,
    )

    final_status: Literal["done", "failed"] = "done" if result.status == "success" else "failed"
    updated_action = finish_execution(action_id, receipt.id, final_status)

    return updated_action, receipt


def list_audit(action_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    query = "SELECT * FROM audit_log WHERE 1=1"
    params: list = []
    if action_id:
        query += " AND action_id = ?"
        params.append(action_id)
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

"""
Immutable receipt records.

write_receipt  — insert and return a new Receipt.
get_receipt    — fetch by id.
list_receipts  — list with optional filters.
"""
import hashlib
import json
import uuid
from dataclasses import dataclass

from app.db import get_connection
from app.executors.base import ExecutionResult


@dataclass
class Receipt:
    id: str
    action_id: str
    executor: str
    payload_snapshot: dict
    started_at: str
    finished_at: str
    status: str
    result_summary: str
    log_excerpt: str
    integrity_hash: str


def _integrity_hash(
    receipt_id: str,
    action_id: str,
    executor: str,
    payload_snapshot: dict,
    started_at: str,
    finished_at: str,
    status: str,
    result_summary: str,
    log_excerpt: str,
) -> str:
    """SHA-256 over the receipt's canonical fields, for tamper evidence."""
    canonical = json.dumps(
        {
            "id": receipt_id,
            "action_id": action_id,
            "executor": executor,
            "payload_snapshot": payload_snapshot,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "result_summary": result_summary,
            "log_excerpt": log_excerpt,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row_to_receipt(row) -> Receipt:
    return Receipt(
        id=row["id"],
        action_id=row["action_id"],
        executor=row["executor"],
        payload_snapshot=json.loads(row["payload_snapshot"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        status=row["status"],
        result_summary=row["result_summary"],
        log_excerpt=row["log_excerpt"],
        integrity_hash=row["integrity_hash"],
    )


def write_receipt(
    action_id: str,
    executor: str,
    payload_snapshot: dict,
    started_at: str,
    finished_at: str,
    result: ExecutionResult,
) -> Receipt:
    receipt_id = str(uuid.uuid4())
    ihash = _integrity_hash(
        receipt_id,
        action_id,
        executor,
        payload_snapshot,
        started_at,
        finished_at,
        result.status,
        result.result_summary,
        result.log_excerpt,
    )
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO receipts
              (id, action_id, executor, payload_snapshot, started_at, finished_at,
               status, result_summary, log_excerpt, integrity_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id,
                action_id,
                executor,
                json.dumps(payload_snapshot),
                started_at,
                finished_at,
                result.status,
                result.result_summary,
                result.log_excerpt,
                ihash,
            ),
        )
    conn.close()
    return get_receipt(receipt_id)


def verify_receipt(receipt_id: str) -> bool | None:
    """Recompute the integrity hash. None if missing, True/False otherwise."""
    r = get_receipt(receipt_id)
    if r is None:
        return None
    expected = _integrity_hash(
        r.id,
        r.action_id,
        r.executor,
        r.payload_snapshot,
        r.started_at,
        r.finished_at,
        r.status,
        r.result_summary,
        r.log_excerpt,
    )
    return expected == r.integrity_hash


def get_receipt(receipt_id: str) -> Receipt | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_receipt(row)


def list_receipts(
    action_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Receipt]:
    query = "SELECT * FROM receipts WHERE 1=1"
    params: list = []
    if action_id:
        query += " AND action_id = ?"
        params.append(action_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    conn = get_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_receipt(r) for r in rows]

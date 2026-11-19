"""Tests for database initialisation."""
from app.db import get_connection, init_db


def test_init_db_idempotent():
    """Calling init_db twice must not raise."""
    init_db()
    init_db()


def test_all_tables_exist():
    conn = get_connection()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    conn.close()
    assert "actions" in names
    assert "receipts" in names
    assert "audit_log" in names

"""
Database initialisation and connection management.

DAQ_DB_PATH env var controls the SQLite file location (default: data/queue.db).
"""
import os
import sqlite3
from pathlib import Path


def _db_path() -> str:
    return os.environ.get("DAQ_DB_PATH", "data/queue.db")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Return a WAL-mode SQLite connection, creating parent directories as needed."""
    path = db_path or _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None) -> None:
    """Create all tables if they do not already exist."""
    conn = get_connection(db_path)
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS actions (
                id            TEXT PRIMARY KEY,
                title         TEXT NOT NULL,
                executor      TEXT NOT NULL,
                payload       TEXT NOT NULL,
                state         TEXT NOT NULL DEFAULT 'draft',
                created_at    TEXT NOT NULL,
                decided_at    TEXT,
                executed_at   TEXT,
                receipt_id    TEXT,
                reject_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS receipts (
                id               TEXT PRIMARY KEY,
                action_id        TEXT NOT NULL,
                executor         TEXT NOT NULL,
                payload_snapshot TEXT NOT NULL,
                started_at       TEXT NOT NULL,
                finished_at      TEXT NOT NULL,
                status           TEXT NOT NULL,
                result_summary   TEXT NOT NULL,
                log_excerpt      TEXT NOT NULL,
                integrity_hash   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id          TEXT PRIMARY KEY,
                action_id   TEXT NOT NULL,
                from_state  TEXT NOT NULL,
                to_state    TEXT NOT NULL,
                actor       TEXT NOT NULL DEFAULT 'human',
                timestamp   TEXT NOT NULL,
                note        TEXT
            );
        """)
    conn.close()

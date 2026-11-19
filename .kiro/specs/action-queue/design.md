# Design: Dani Action Queue

## 1. Architecture Overview

The system is a local, single-user FastAPI service with a SQLite database, a vanilla-JS single-page dashboard, and a CLI that calls the same Python layer directly (no HTTP round-trip).

```
┌─────────────────────────────────────────────┐
│                 Clients                     │
│  Browser (dashboard)   CLI (daq)            │
└────────────┬───────────────────┬────────────┘
             │ HTTP (JSON)       │ Python import
             ▼                   ▼
┌────────────────────────────────────────────┐
│              app/api.py  (FastAPI)         │
│   routes: actions, receipts, audit         │
└────────────────────┬───────────────────────┘
                     │
          ┌──────────▼──────────┐
          │    app/queue.py     │  state machine + business logic
          └──┬───────────┬──────┘
             │           │
  ┌──────────▼───┐  ┌────▼──────────┐
  │  app/        │  │ app/receipts  │
  │  executors/  │  │    .py        │
  │  (3 modules) │  └───────────────┘
  └──────────────┘
             │
  ┌──────────▼──────────────────────┐
  │     data/queue.db  (SQLite)     │
  │  tables: actions, receipts,     │
  │          audit_log              │
  └─────────────────────────────────┘
```

**Module responsibilities:**

| Module | Role |
|---|---|
| `app/api.py` | FastAPI router, request/response models (Pydantic), HTTP entry points |
| `app/queue.py` | State machine transitions, guard conditions, action CRUD against SQLite |
| `app/receipts.py` | Write and read immutable receipt records |
| `app/executors/base.py` | Abstract base class `Executor` with a single `execute(payload) -> ExecutionResult` method |
| `app/executors/file_organize.py` | Plan and apply directory reorganisation |
| `app/executors/shell_allowlist.py` | Validate command against `allowlist.json`, then run via subprocess |
| `app/executors/webhook.py` | HTTP POST using `urllib.request` (stdlib only) |
| `app/cli.py` | Thin argparse wrapper; calls `queue.py` and `receipts.py` directly |
| `app/static/` | Served as static files; no build step |

---

## 2. Data Model

All tables live in a single SQLite file at `data/queue.db`.  The path is configurable via the environment variable `DAQ_DB_PATH` so tests can supply an isolated temp file.

### 2.1 `actions`

```sql
CREATE TABLE actions (
    id           TEXT PRIMARY KEY,          -- UUIDv4
    title        TEXT NOT NULL,
    executor     TEXT NOT NULL,             -- 'file_organize' | 'shell_allowlist' | 'webhook'
    payload      TEXT NOT NULL,             -- JSON string
    state        TEXT NOT NULL DEFAULT 'draft',
    created_at   TEXT NOT NULL,             -- ISO-8601 UTC
    decided_at   TEXT,                      -- set on approve or reject
    executed_at  TEXT,                      -- set when execution completes
    receipt_id   TEXT,                      -- FK -> receipts.id, nullable
    reject_reason TEXT                      -- populated on rejection, else NULL
);
```

### 2.2 `receipts`

```sql
CREATE TABLE receipts (
    id               TEXT PRIMARY KEY,      -- UUIDv4
    action_id        TEXT NOT NULL,         -- FK -> actions.id
    executor         TEXT NOT NULL,
    payload_snapshot TEXT NOT NULL,         -- JSON string; copy of payload at execution time
    started_at       TEXT NOT NULL,         -- ISO-8601 UTC
    finished_at      TEXT NOT NULL,         -- ISO-8601 UTC
    status           TEXT NOT NULL,         -- 'success' | 'failure'
    result_summary   TEXT NOT NULL,         -- human-readable one-liner
    log_excerpt      TEXT NOT NULL          -- stdout/stderr or detail, up to 4 KB
);
```

### 2.3 `audit_log`

```sql
CREATE TABLE audit_log (
    id           TEXT PRIMARY KEY,          -- UUIDv4
    action_id    TEXT NOT NULL,             -- FK -> actions.id
    from_state   TEXT NOT NULL,
    to_state     TEXT NOT NULL,
    actor        TEXT NOT NULL DEFAULT 'human',
    timestamp    TEXT NOT NULL,             -- ISO-8601 UTC
    note         TEXT                       -- rejection reason or free text, nullable
);
```

**Notes:**
- `payload` and `payload_snapshot` are stored as JSON strings; `queue.py` and `receipts.py` parse them at the Python boundary.
- No foreign-key enforcement is configured (SQLite default), but application code always writes consistent references.
- `data/` is gitignored; `data/queue.db` is created on first startup via `CREATE TABLE IF NOT EXISTS`.

---

## 3. State Machine

```
              ┌─────────┐
              │  draft  │ ◄── initial state on create
              └────┬────┘
        approve /  │  \ reject
                   │
          ┌────────▼────────┐         ┌──────────┐
          │    approved     │──reject─►  rejected │ (terminal)
          └────────┬────────┘         └──────────┘
                   │ execute
          ┌────────▼────────┐
          │   executing     │  (synchronous; set before executor runs)
          └───┬─────────┬───┘
        done  │         │  error
      ┌───────▼──┐  ┌───▼──────┐
      │   done   │  │  failed  │  (both terminal)
      └──────────┘  └──────────┘
```

**Transition rules (enforced in `queue.py`):**

| Transition | From | To | Guard |
|---|---|---|---|
| `approve` | `draft` | `approved` | — |
| `reject` | `draft` or `approved` | `rejected` | reason required |
| `execute` | `approved` | `executing` → `done` \| `failed` | executor must succeed to set `done`; any exception sets `failed` |

- `executing` is a transient in-process state. Because the server is single-threaded with sync executors, it will never be persisted in a "stuck" condition under normal operation. Future async extensions would treat it as resumable.
- Every transition appends a row to `audit_log`.

---

## 4. API Surface

Base path: `/api/v1`

All request and response bodies are JSON. Error responses follow `{"detail": "<message>"}`.

### Actions

| Method | Path | Description |
|---|---|---|
| `POST` | `/actions` | Create a draft action |
| `GET` | `/actions` | List actions; query params: `state`, `executor`, `limit` (default 50), `offset` (default 0) |
| `GET` | `/actions/{id}` | Get a single action |
| `POST` | `/actions/{id}/approve` | Approve a draft |
| `POST` | `/actions/{id}/reject` | Reject a draft or approved action; body `{"reason": "..."}` |
| `POST` | `/actions/{id}/execute` | Execute an approved action (synchronous) |

### Receipts

| Method | Path | Description |
|---|---|---|
| `GET` | `/receipts` | List receipts; query params: `action_id`, `status`, `limit`, `offset` |
| `GET` | `/receipts/{id}` | Get a single receipt |

### Audit

| Method | Path | Description |
|---|---|---|
| `GET` | `/audit` | List audit log entries; query params: `action_id`, `limit`, `offset` |

### Static / Dashboard

`GET /` and `GET /static/{path}` — served from `app/static/` by FastAPI's `StaticFiles` mount.

### Pydantic schemas (request / response)

**ActionCreate** — `title: str`, `executor: Literal[...]`, `payload: dict`

**ActionOut** — all columns from `actions` table (payload as `dict`).

**ApproveOut** / **RejectIn** / **RejectOut** — minimal wrappers around state change results.

**ReceiptOut** — all columns from `receipts` table (payload_snapshot as `dict`).

**AuditEntryOut** — all columns from `audit_log`.

---

## 5. Executor Contracts

All executors live in `app/executors/`. Each is a module exporting a function (not a class instance) with this signature:

```python
def execute(payload: dict) -> ExecutionResult:
    ...
```

`ExecutionResult` is a dataclass defined in `app/executors/base.py`:

```python
@dataclass
class ExecutionResult:
    status: Literal["success", "failure"]
    result_summary: str    # one line, ≤ 200 chars
    log_excerpt: str       # detail, truncated to 4096 chars
```

Executors never raise; they catch all exceptions and return `status="failure"` with the traceback in `log_excerpt`. The caller in `queue.py` treats any unexpected exception as a bug and sets state to `failed` with a generic log entry.

### 5.1 `file_organize`

**Payload fields:**
```json
{
  "directory": "/absolute/or/relative/path",
  "grouping": "by_extension"
}
```

**Behaviour:**
1. On draft creation, `queue.py` calls a `plan(payload) -> list[MoveOp]` function that returns the list of `{src, dst}` moves without touching the filesystem. This plan is stored in the action payload as a `"plan"` key.
2. On execution, the plan is applied: each `src` is moved to `dst`. If any move fails, the executor marks the whole action as `failed` and records which moves succeeded in `log_excerpt`.
3. Only files are moved; directories are left in place. Existing files at the destination raise an error (no silent overwrite).
4. `grouping: "by_extension"` groups by lowercased extension (`.py`, `.txt`, etc.). Files without an extension go into `no_extension/`.

### 5.2 `shell_allowlist`

**Payload fields:**
```json
{
  "command": "ls -la /tmp"
}
```

**Allowlist file:** `allowlist.json` in the repository root (next to `app/`). Format:
```json
["ls", "echo", "date"]
```
Only the base command name (first token) is checked. The full command string is passed to `subprocess.run` with `shell=False` after splitting via `shlex.split`.

**Behaviour:**
1. Split the command with `shlex.split`. If the first token is not in the allowlist, return `status="failure"` with `result_summary="command not in allowlist"`.
2. Run with `subprocess.run(..., capture_output=True, text=True, timeout=30)`.
3. `log_excerpt` = combined stdout + stderr, truncated to 4096 chars.
4. Exit code ≠ 0 → `status="failure"`.

### 5.3 `webhook`

**Payload fields:**
```json
{
  "url": "https://example.com/hook",
  "body": { "any": "json" },
  "headers": { "X-Custom": "value" }
}
```
`headers` is optional. `url` must be `https://` (enforced at execute time, not at draft time).

**Behaviour:**
1. Serialize `body` as JSON. POST to `url` using `urllib.request.urlopen` with a 15-second timeout.
2. `result_summary` = `"HTTP <status_code>"`.
3. Response body (up to 4096 chars) stored in `log_excerpt`.
4. Any `URLError` or timeout → `status="failure"`.

---

## 6. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DAQ_DB_PATH` | `data/queue.db` | SQLite file path |
| `DAQ_ALLOWLIST_PATH` | `allowlist.json` | Shell allowlist file |
| `DAQ_HOST` | `127.0.0.1` | Server bind address |
| `DAQ_PORT` | `8000` | Server port |

Configuration is read from environment variables at startup. No `.env` file parsing; callers set vars before launching.

---

## 7. Dashboard (Single-Page)

`app/static/index.html` loads `app.js` and `style.css` with no bundler or framework.

**Views:**
- **Queue view** (default): table of actions with columns title, executor, state, created_at. Approve / Reject / Execute buttons appear contextually based on current state. A filter bar filters by `state`.
- **Receipt view**: shown when the user clicks an action row that has a receipt. Displays all receipt fields and the log excerpt in a `<pre>` block.
- **Audit view**: accessible from a nav link; shows the audit log in reverse-chronological order.

`app.js` communicates with the API exclusively via `fetch`. All rendering is DOM manipulation; no virtual DOM or template engine.

---

## 8. CLI (`app/cli.py`)

Entry point: `python -m app.cli` (also exposed as `daq` via `pyproject.toml` or `setup.cfg` console_scripts).

Subcommands mirror API operations:

```
daq action create --title "..." --executor file_organize --payload '{"directory": "."}'
daq action list [--state draft|approved|done|failed|rejected] [--executor ...]
daq action get <id>
daq action approve <id>
daq action reject <id> --reason "..."
daq action execute <id>
daq receipt list [--action-id ...] [--status ...]
daq receipt get <id>
daq audit list [--action-id ...]
```

The CLI imports `app.queue` and `app.receipts` directly; it does not make HTTP calls. Output is formatted as pretty-printed JSON to stdout. Errors go to stderr with a non-zero exit code.

---

## 9. Database Initialisation

`app/queue.py` exposes an `init_db(db_path: str)` function that runs `CREATE TABLE IF NOT EXISTS` for all three tables. `api.py` calls `init_db` in a FastAPI `lifespan` startup handler. The CLI calls `init_db` before any operation.

---

## 10. Testing Strategy

- Tests live in `tests/`. Each test module gets a temp directory (via `tmp_path` fixture) for the SQLite file and any filesystem operations.
- `DAQ_DB_PATH` and `DAQ_ALLOWLIST_PATH` are set to temp paths in a `conftest.py` autouse fixture.
- FastAPI routes are tested via `TestClient` (from `starlette.testclient`, bundled with FastAPI).
- Executor tests run against a real temp filesystem; `webhook` tests use a local `http.server` thread.
- No mocks for executors — the product principle requires real effects.

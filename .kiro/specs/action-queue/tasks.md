# Tasks: Dani Action Queue

Tasks are ordered so each builds on what came before. Complete them in sequence. Run `pytest` after every task that touches runtime code; all tests must stay green.

---

## Task 1 — Project skeleton and database layer

**Goal:** establish the package structure, configuration, and SQLite schema so every later task has a stable foundation.

1. Create the Python package `app/` with an `__init__.py`.
2. Create `app/executors/` with an `__init__.py`.
3. Create `app/static/` (empty placeholder files `index.html`, `app.js`, `style.css`).
4. Create `data/.gitkeep` and add `data/*.db` to `.gitignore`.
5. Create `app/db.py`:
   - Read `DAQ_DB_PATH` from env (default `data/queue.db`).
   - Expose `get_connection() -> sqlite3.Connection` (creates parent dirs, enables WAL mode).
   - Expose `init_db(db_path: str | None = None)` that runs `CREATE TABLE IF NOT EXISTS` for `actions`, `receipts`, and `audit_log` exactly as specified in the design.
6. Create `tests/conftest.py` with an autouse session-scoped fixture that sets `DAQ_DB_PATH` to a temp file and calls `init_db()`.
7. Write `tests/test_db.py` verifying that `init_db` is idempotent (callable twice without error) and that all three tables exist.

**Acceptance:** `pytest tests/test_db.py` passes.

---

## Task 2 — `app/queue.py`: action CRUD and state machine

**Goal:** implement all action persistence and state transitions against SQLite, with no FastAPI dependency.

1. Define an `Action` dataclass (or namedtuple) mirroring the `actions` table columns.
2. Implement:
   - `create_action(title, executor, payload: dict) -> Action` — inserts a draft; appends audit row.
   - `get_action(action_id: str) -> Action | None`
   - `list_actions(state=None, executor=None, limit=50, offset=0) -> list[Action]`
   - `approve_action(action_id: str) -> Action` — transitions `draft → approved`; appends audit row; raises `ValueError` if wrong state.
   - `reject_action(action_id: str, reason: str) -> Action` — transitions `draft | approved → rejected`; raises `ValueError` if terminal.
   - `begin_execution(action_id: str) -> Action` — transitions `approved → executing`; raises `ValueError` if not approved.
   - `finish_execution(action_id: str, receipt_id: str, status: Literal["done","failed"]) -> Action` — transitions `executing → done | failed`; sets `executed_at` and `receipt_id`.
3. Each function that changes state appends a row to `audit_log`.
4. Write `tests/test_queue.py` covering:
   - Happy-path create → approve → execute (done).
   - Rejection from draft and from approved.
   - Guard: executing a non-approved action raises `ValueError`.
   - Guard: approving an already-approved action raises `ValueError`.
   - `list_actions` filtering by state.

**Acceptance:** `pytest tests/test_queue.py` passes.

---

## Task 3 — Executor base and `file_organize` executor

**Goal:** implement the executor contract and the first real executor.

1. Create `app/executors/base.py`:
   - `ExecutionResult` dataclass: `status`, `result_summary`, `log_excerpt`.
   - Abstract helper `truncate(s: str, limit=4096) -> str`.
2. Create `app/executors/file_organize.py`:
   - `plan(payload: dict) -> list[dict]` — returns `[{"src": "...", "dst": "..."}]` without touching the filesystem. Raises `ValueError` for missing/invalid fields.
   - `execute(payload: dict) -> ExecutionResult` — applies the plan stored in `payload["plan"]`; moves files using `shutil.move`; records successes/failures in `log_excerpt`; never raises.
3. Update `app/queue.py`'s `create_action` to call `file_organize.plan` when `executor == "file_organize"` and merge the plan into the payload before storing.
4. Write `tests/test_executor_file_organize.py`:
   - `plan` groups files correctly by extension into expected subfolder names.
   - `plan` on an empty directory returns an empty list.
   - Files without extension map to `no_extension/`.
   - `execute` moves files and returns `status="success"`.
   - `execute` returns `status="failure"` when a destination file already exists.

**Acceptance:** `pytest tests/test_executor_file_organize.py` passes.

---

## Task 4 — `shell_allowlist` executor

**Goal:** implement the shell executor with allowlist enforcement.

1. Create `app/executors/shell_allowlist.py`:
   - Read `DAQ_ALLOWLIST_PATH` from env (default `allowlist.json`).
   - `load_allowlist(path: str | None = None) -> list[str]` — reads and parses the JSON file; returns `[]` if file absent.
   - `execute(payload: dict) -> ExecutionResult` — split with `shlex.split`, check allowlist, run via `subprocess.run(shell=False, capture_output=True, text=True, timeout=30)`, never raises.
2. Create `allowlist.json` in the repo root with a minimal safe set: `["echo", "date", "ls"]`.
3. Add `DAQ_ALLOWLIST_PATH` to the test fixture in `conftest.py` pointing to a temp allowlist file.
4. Write `tests/test_executor_shell.py`:
   - Allowed command (`echo hello`) returns `status="success"` and stdout in `log_excerpt`.
   - Non-allowed command returns `status="failure"` with reason in `result_summary`.
   - Non-zero exit code returns `status="failure"`.
   - Empty allowlist file blocks everything.

**Acceptance:** `pytest tests/test_executor_shell.py` passes.

---

## Task 5 — `webhook` executor

**Goal:** implement the HTTP webhook executor using stdlib only.

1. Create `app/executors/webhook.py`:
   - `execute(payload: dict) -> ExecutionResult` — POST JSON body to `payload["url"]`; merge optional `payload["headers"]`; enforce `https://`; 15-second timeout; never raises.
2. Write `tests/test_executor_webhook.py`:
   - Spin up a minimal `http.server.HTTPServer` in a background thread that records the received request and returns 200.
   - `execute` with a valid HTTPS-equivalent (use a mock/local server responding at `http://` only for testing — note the design enforces `https://` at execute time; the test may use a subclass that skips the scheme check, or test the guard separately).
   - Non-HTTPS URL returns `status="failure"`.
   - Connection error returns `status="failure"`.
   - Non-2xx response sets `status="failure"` with `result_summary="HTTP <code>"`.

**Acceptance:** `pytest tests/test_executor_webhook.py` passes.

---

## Task 6 — `app/receipts.py`

**Goal:** write and read immutable receipt records.

1. Define a `Receipt` dataclass mirroring the `receipts` table columns.
2. Implement:
   - `write_receipt(action_id, executor, payload_snapshot: dict, started_at, finished_at, result: ExecutionResult) -> Receipt` — inserts a row and returns the new `Receipt`.
   - `get_receipt(receipt_id: str) -> Receipt | None`
   - `list_receipts(action_id=None, status=None, limit=50, offset=0) -> list[Receipt]`
3. Write `tests/test_receipts.py`:
   - `write_receipt` stores and returns a valid receipt.
   - `get_receipt` retrieves it by id.
   - `list_receipts` filters by `action_id` and `status`.
   - `payload_snapshot` round-trips as a dict.

**Acceptance:** `pytest tests/test_receipts.py` passes.

---

## Task 7 — Execution orchestration in `queue.py`

**Goal:** wire state transitions to executor dispatch and receipt writing.

1. Add `execute_action(action_id: str) -> tuple[Action, Receipt]` to `app/queue.py`:
   - Calls `begin_execution`.
   - Dispatches to the correct executor module based on `action.executor`.
   - Calls `write_receipt` with the result.
   - Calls `finish_execution` with `"done"` or `"failed"` based on `result.status`.
   - Returns `(updated_action, receipt)`.
2. Write `tests/test_execute_action.py`:
   - Full happy path for `file_organize`: create → approve → execute → receipt shows `success`.
   - Full path for `shell_allowlist` with `echo` command.
   - Execution of a non-approved action raises `ValueError`.
   - Failed executor (bad command) transitions action to `failed` and writes a failure receipt.

**Acceptance:** `pytest tests/test_execute_action.py` passes.

---

## Task 8 — FastAPI application (`app/api.py`)

**Goal:** expose all operations as a JSON API.

1. Define Pydantic models: `ActionCreate`, `ActionOut`, `RejectIn`, `ReceiptOut`, `AuditEntryOut`.
2. Implement all routes from the design's API surface table, calling `queue.py`, `receipts.py` for data.
3. Mount `app/static/` at `/static` and serve `index.html` at `GET /`.
4. Add a `lifespan` startup handler that calls `init_db()`.
5. Create `app/main.py` as the uvicorn entry point (`uvicorn app.main:app`).
6. Write `tests/test_api.py` using `TestClient`:
   - POST `/api/v1/actions` creates a draft; response has `state="draft"`.
   - GET `/api/v1/actions` lists it; filter by `state=draft` returns it, `state=done` does not.
   - Approve then execute an `echo`-based `shell_allowlist` action end-to-end; final state is `done`.
   - Reject a draft; response has `state="rejected"`.
   - GET `/api/v1/receipts/{id}` returns the receipt after execution.
   - GET `/api/v1/audit` returns audit entries.
   - Executing a non-approved action returns HTTP 409.

**Acceptance:** `pytest tests/test_api.py` passes.

---

## Task 9 — CLI (`app/cli.py`)

**Goal:** provide a `daq` command that mirrors every API operation.

1. Implement the CLI using `argparse` with subcommands exactly as listed in the design.
2. The CLI imports `app.queue`, `app.receipts` directly (no HTTP). It calls `init_db()` before any operation.
3. Output is `json.dumps(..., indent=2)` to stdout. Errors print to stderr and exit with code 1.
4. Register `daq = app.cli:main` in `pyproject.toml` (or `setup.cfg`) under `[project.scripts]`.
5. Write `tests/test_cli.py`:
   - `daq action create ...` outputs JSON with `state="draft"`.
   - `daq action approve <id>` succeeds; `daq action list --state approved` lists it.
   - `daq action reject <id> --reason "..."` outputs `state="rejected"`.
   - `daq receipt list` returns receipts after execution.
   - Unknown executor name in create exits with code 1.

**Acceptance:** `pytest tests/test_cli.py` passes.

---

## Task 10 — Dashboard (`app/static/`)

**Goal:** deliver a working single-page dashboard with no build step.

1. `index.html`: semantic HTML5 shell with a `<nav>` (Queue | Audit), a `<main>` region, and script/style tags. No external CDN resources.
2. `style.css`: minimal legible styles — table layout, state-coloured badges (draft: grey, approved: blue, executing: yellow, done: green, failed/rejected: red), button styles, responsive single-column on narrow viewports.
3. `app.js`:
   - On load, fetch `/api/v1/actions?limit=100` and render the queue table.
   - Approve button: POST to `/api/v1/actions/{id}/approve`; refresh table.
   - Reject button: prompt for reason, POST to `/api/v1/actions/{id}/reject`; refresh table.
   - Execute button: POST to `/api/v1/actions/{id}/execute`; refresh table.
   - Clicking an action row that has a `receipt_id` fetches and displays the receipt inline below the row.
   - Audit nav link: fetch `/api/v1/audit?limit=200` and render audit table.
   - State filter `<select>` re-fetches with `?state=<value>`.
   - All fetch errors display a dismissible error banner.
4. No test is required for static files; manual verification via browser is sufficient. Add a brief smoke-test note in `tests/test_api.py` that `GET /` returns 200.

**Acceptance:** `pytest` (full suite) passes; `GET /` returns 200 in the API test.

---

## Task 11 — Integration test and final validation

**Goal:** one end-to-end test that exercises the full draft → approve → execute → receipt path for all three executors.

1. Add `tests/test_integration.py`:
   - `file_organize`: create a temp dir with mixed-extension files, create action, approve, execute via `execute_action`, verify files moved to correct subfolders, verify receipt status is `success`.
   - `shell_allowlist`: create action with `echo "hello"`, approve, execute, verify receipt log contains `hello`.
   - `webhook`: start a local HTTP server thread, create action pointing to it, approve, execute, verify server received the POST and receipt status is `success` (note: test may bypass the `https://` guard by patching the scheme check for localhost).
   - Verify audit log has correct number of entries for each action.
2. Run `pytest` with `-v` to confirm all tests pass.
3. Remove any temporary scripts or scratch files from the workspace.

**Acceptance:** `pytest -v` exits 0 with all tests passing.

---

## Completion checklist

- [ ] All 11 tasks complete and all tests green.
- [ ] `daq --help` lists all subcommands.
- [ ] `uvicorn app.main:app` starts without error and `GET /` returns the dashboard.
- [ ] `data/` is gitignored; `.kiro/` is not gitignored.
- [ ] No hardcoded secrets, URLs, or paths outside of configurable defaults.
- [ ] `allowlist.json` present in repo root.

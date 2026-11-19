# Tech constraints

- Python 3.11+, FastAPI + uvicorn for the API, vanilla HTML/JS single page for the dashboard.
- SQLite via Python stdlib sqlite3. No ORM.
- Dependencies: fastapi, uvicorn, pydantic only. No other packages.
- CLI entry point `daq` (python -m app.cli) mirroring every API operation.
- Tests: pytest against a temp directory and temp database. Tests must pass before commit.
- No secrets in code. Webhook URLs come from the action payload, never hardcoded.

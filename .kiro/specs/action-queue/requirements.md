# Requirements: action queue core

1. Action lifecycle: an action has states draft -> approved -> executing -> done | failed | rejected. Only approved actions may execute. Rejection is terminal with a reason.
2. Action fields: id, title, executor (file_organize | shell_allowlist | webhook), payload (JSON), state, created_at, decided_at, executed_at, receipt_id (nullable).
3. Executors:
   - file_organize: given a directory path and grouping rule (by extension), move files into subfolders. Dry-run plan stored on the draft; execution applies the plan.
   - shell_allowlist: run one command from a configurable allowlist file (allowlist.json in repo root). Reject anything not listed.
   - webhook: POST a JSON body to a URL from the payload; record status code.
4. Receipts: immutable record per execution (id, action_id, started/finished timestamps, executor, payload snapshot, result summary, status, log excerpt).
5. API: create draft, list/filter actions, get action, approve, reject, execute (approved only), list receipts, get receipt.
6. Dashboard: single page showing the queue with approve/reject/execute buttons and a receipt view. No build step.
7. CLI: same operations as API for terminal use.
8. Audit: state transitions are appended to an audit log table with timestamp and actor ("human").

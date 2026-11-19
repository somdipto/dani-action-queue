# Product: Dani Action Queue

Dan Lab's agent Dani drafts useful actions, but nothing runs until a human approves it.
This app is the queue in the middle: draft -> approve -> execute -> receipt.

Principles:
- Every action starts as a draft. Nothing executes without explicit approval.
- Every execution writes a receipt: what ran, when, inputs, outputs, status.
- Executors are real: they perform actual local effects (filesystem, shell allowlist, HTTP webhook). No mocks.
- Single user, runs locally. No accounts, no cloud dependencies.

"""
shell_allowlist executor.

Runs a shell command only if its base name is in the allowlist.
DAQ_ALLOWLIST_PATH env var controls the allowlist file location.
"""
import json
import os
import shlex
import subprocess
from pathlib import Path

from app.executors.base import ExecutionResult, truncate


def _allowlist_path() -> str:
    return os.environ.get("DAQ_ALLOWLIST_PATH", "allowlist.json")


def load_allowlist(path: str | None = None) -> list[str]:
    """Load allowlist from JSON file. Returns [] if file is absent."""
    p = Path(path or _allowlist_path())
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        if isinstance(data, list):
            return [str(x) for x in data]
        return []
    except (json.JSONDecodeError, OSError):
        return []


def execute(payload: dict) -> ExecutionResult:
    """Execute the command from payload["command"] if allowed."""
    command = payload.get("command", "")
    if not command:
        return ExecutionResult(
            status="failure",
            result_summary="No command specified.",
            log_excerpt="payload missing 'command' key.",
        )

    try:
        args = shlex.split(command)
    except ValueError as exc:
        return ExecutionResult(
            status="failure",
            result_summary=f"Failed to parse command: {exc}",
            log_excerpt=str(exc),
        )

    if not args:
        return ExecutionResult(
            status="failure",
            result_summary="Empty command.",
            log_excerpt="",
        )

    base_cmd = os.path.basename(args[0])
    allowlist = load_allowlist()
    if base_cmd not in allowlist:
        return ExecutionResult(
            status="failure",
            result_summary="command not in allowlist",
            log_excerpt=f"'{base_cmd}' is not in the allowlist: {allowlist}",
        )

    try:
        proc = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            status="failure",
            result_summary="Command timed out after 30 seconds.",
            log_excerpt="TimeoutExpired",
        )
    except Exception as exc:
        return ExecutionResult(
            status="failure",
            result_summary=f"Unexpected error: {exc}",
            log_excerpt=str(exc),
        )

    combined = proc.stdout + proc.stderr
    log_excerpt = truncate(combined)

    if proc.returncode != 0:
        return ExecutionResult(
            status="failure",
            result_summary=f"Command exited with code {proc.returncode}.",
            log_excerpt=log_excerpt,
        )

    return ExecutionResult(
        status="success",
        result_summary=f"Command exited with code 0.",
        log_excerpt=log_excerpt,
    )

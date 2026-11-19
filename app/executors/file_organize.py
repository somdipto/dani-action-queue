"""
file_organize executor.

plan()    — build a list of {src, dst} moves without touching the filesystem.
execute() — apply a pre-computed plan stored in payload["plan"].
"""
import os
import shutil
from pathlib import Path

from app.executors.base import ExecutionResult, truncate


def plan(payload: dict) -> list[dict]:
    """
    Return [{src: str, dst: str}, ...] for files in payload["directory"].

    Only files are included; subdirectories are skipped.
    grouping must be "by_extension".
    Raises ValueError for missing/invalid fields.
    """
    directory = payload.get("directory")
    grouping = payload.get("grouping", "by_extension")

    if not directory:
        raise ValueError("payload must include 'directory'")
    if grouping != "by_extension":
        raise ValueError(f"Unsupported grouping '{grouping}'. Only 'by_extension' is supported.")

    base = Path(directory)
    if not base.exists():
        raise ValueError(f"Directory does not exist: {directory}")
    if not base.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    moves = []
    for entry in base.iterdir():
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        subfolder = ext.lstrip(".") if ext else "no_extension"
        dst = base / subfolder / entry.name
        moves.append({"src": str(entry), "dst": str(dst)})

    return moves


def execute(payload: dict) -> ExecutionResult:
    """Apply the plan from payload["plan"], moving files."""
    plan_steps: list[dict] = payload.get("plan", [])
    if not plan_steps:
        return ExecutionResult(
            status="success",
            result_summary="No files to move.",
            log_excerpt="Plan was empty.",
        )

    successes = []
    failures = []

    for step in plan_steps:
        src = step["src"]
        dst = step["dst"]
        try:
            dst_path = Path(dst)
            if dst_path.exists():
                raise FileExistsError(f"Destination already exists: {dst}")
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
            successes.append(f"OK  {src} -> {dst}")
        except Exception as exc:
            failures.append(f"ERR {src} -> {dst}: {exc}")

    log_lines = successes + failures
    log_excerpt = truncate("\n".join(log_lines))

    if failures:
        return ExecutionResult(
            status="failure",
            result_summary=f"Moved {len(successes)}/{len(plan_steps)} files; {len(failures)} failed.",
            log_excerpt=log_excerpt,
        )

    return ExecutionResult(
        status="success",
        result_summary=f"Moved {len(successes)} file(s) successfully.",
        log_excerpt=log_excerpt,
  )

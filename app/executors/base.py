"""Shared executor types."""
from dataclasses import dataclass
from typing import Literal


@dataclass
class ExecutionResult:
    status: Literal["success", "failure"]
    result_summary: str   # one line, ≤ 200 chars
    log_excerpt: str      # detail, truncated to 4096 chars


def truncate(s: str, limit: int = 4096) -> str:
    if len(s) <= limit:
        return s
    return s[:limit]

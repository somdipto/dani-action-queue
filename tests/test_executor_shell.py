"""Tests for the shell_allowlist executor."""
import json
import os
from pathlib import Path

import pytest

from app.executors.shell_allowlist import execute, load_allowlist


def test_allowed_command_success():
    result = execute({"command": "echo hello"})
    assert result.status == "success"
    assert "hello" in result.log_excerpt


def test_non_allowed_command_failure():
    result = execute({"command": "rm -rf /tmp/should_not_run"})
    assert result.status == "failure"
    assert "allowlist" in result.result_summary


def test_nonzero_exit_code_failure(tmp_path):
    # 'ls' on a path that doesn't exist exits with non-zero
    result = execute({"command": f"ls /nonexistent_path_dani_{os.getpid()}"})
    assert result.status == "failure"


def test_empty_allowlist_blocks_everything(tmp_path, monkeypatch):
    empty = tmp_path / "empty_allowlist.json"
    empty.write_text("[]")
    monkeypatch.setenv("DAQ_ALLOWLIST_PATH", str(empty))
    result = execute({"command": "echo hello"})
    assert result.status == "failure"
    assert "allowlist" in result.result_summary

"""Tests for the execute_action orchestration in queue.py."""
import os
from pathlib import Path

import pytest

from app.queue import approve_action, create_action, execute_action


def test_file_organize_full_happy_path(tmp_path):
    # Seed the directory
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("y")

    action = create_action(
        "organise tmp",
        "file_organize",
        {"directory": str(tmp_path), "grouping": "by_extension"},
    )
    action = approve_action(action.id)
    updated, receipt = execute_action(action.id)

    assert updated.state == "done"
    assert receipt.status == "success"
    assert (tmp_path / "py" / "a.py").exists()
    assert (tmp_path / "txt" / "b.txt").exists()


def test_shell_allowlist_echo_happy_path():
    action = create_action("echo test", "shell_allowlist", {"command": "echo integration"})
    action = approve_action(action.id)
    updated, receipt = execute_action(action.id)

    assert updated.state == "done"
    assert receipt.status == "success"
    assert "integration" in receipt.log_excerpt


def test_execute_non_approved_raises():
    action = create_action("not approved", "shell_allowlist", {"command": "echo hi"})
    with pytest.raises(ValueError):
        execute_action(action.id)


def test_failed_executor_transitions_to_failed():
    # Command not in allowlist → executor returns failure
    action = create_action("bad cmd", "shell_allowlist", {"command": "badcmd --foo"})
    action = approve_action(action.id)
    updated, receipt = execute_action(action.id)

    assert updated.state == "failed"
    assert receipt.status == "failure"

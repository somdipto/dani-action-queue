"""Tests for action CRUD and state machine (queue.py)."""
import pytest

from app.queue import (
    approve_action,
    begin_execution,
    create_action,
    finish_execution,
    get_action,
    list_actions,
    reject_action,
)


def _shell_action(title="Test echo"):
    return create_action(title, "shell_allowlist", {"command": "echo hello"})


def test_create_action_draft():
    action = _shell_action()
    assert action.state == "draft"
    assert action.id is not None
    assert action.executor == "shell_allowlist"


def test_approve_action():
    action = _shell_action("approve me")
    approved = approve_action(action.id)
    assert approved.state == "approved"
    assert approved.decided_at is not None


def test_happy_path_create_approve_execute_done():
    action = _shell_action("happy path")
    action = approve_action(action.id)
    action = begin_execution(action.id)
    assert action.state == "executing"
    action = finish_execution(action.id, "fake-receipt-1", "done")
    assert action.state == "done"
    assert action.receipt_id == "fake-receipt-1"
    assert action.executed_at is not None


def test_reject_from_draft():
    action = _shell_action("reject draft")
    rejected = reject_action(action.id, "not needed")
    assert rejected.state == "rejected"
    assert rejected.reject_reason == "not needed"


def test_reject_from_approved():
    action = _shell_action("reject approved")
    action = approve_action(action.id)
    rejected = reject_action(action.id, "changed my mind")
    assert rejected.state == "rejected"


def test_reject_terminal_raises():
    action = _shell_action("reject done")
    action = approve_action(action.id)
    action = begin_execution(action.id)
    action = finish_execution(action.id, "fake-receipt-2", "done")
    with pytest.raises(ValueError, match="terminal"):
        reject_action(action.id, "too late")


def test_execute_non_approved_raises():
    action = _shell_action("not approved")
    with pytest.raises(ValueError, match="approved"):
        begin_execution(action.id)


def test_approve_already_approved_raises():
    action = _shell_action("double approve")
    approve_action(action.id)
    with pytest.raises(ValueError, match="draft"):
        approve_action(action.id)


def test_list_actions_filter_by_state():
    # create two actions; approve only one
    a1 = _shell_action("list filter 1")
    a2 = _shell_action("list filter 2")
    approve_action(a2.id)

    drafts = list_actions(state="draft")
    draft_ids = {a.id for a in drafts}
    approved = list_actions(state="approved")
    approved_ids = {a.id for a in approved}

    assert a1.id in draft_ids
    assert a2.id not in draft_ids
    assert a2.id in approved_ids
    assert a1.id not in approved_ids

"""Tests for the FastAPI application."""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_root_returns_200():
    r = client.get("/")
    assert r.status_code == 200


def test_create_draft():
    r = client.post(
        "/api/v1/actions",
        json={"title": "Test action", "executor": "shell_allowlist", "payload": {"command": "echo api_test"}},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["state"] == "draft"
    assert data["id"] is not None


def test_list_actions_state_filter():
    # create a known action
    r = client.post(
        "/api/v1/actions",
        json={"title": "filter test", "executor": "shell_allowlist", "payload": {"command": "echo filter"}},
    )
    action_id = r.json()["id"]

    r_draft = client.get("/api/v1/actions?state=draft")
    assert r_draft.status_code == 200
    draft_ids = {a["id"] for a in r_draft.json()}
    assert action_id in draft_ids

    r_done = client.get("/api/v1/actions?state=done")
    done_ids = {a["id"] for a in r_done.json()}
    assert action_id not in done_ids


def test_approve_then_execute_shell():
    r = client.post(
        "/api/v1/actions",
        json={"title": "execute me", "executor": "shell_allowlist", "payload": {"command": "echo e2e"}},
    )
    action_id = r.json()["id"]

    r_approve = client.post(f"/api/v1/actions/{action_id}/approve")
    assert r_approve.status_code == 200
    assert r_approve.json()["state"] == "approved"

    r_exec = client.post(f"/api/v1/actions/{action_id}/execute")
    assert r_exec.status_code == 200
    data = r_exec.json()
    assert data["state"] == "done"


def test_reject_draft():
    r = client.post(
        "/api/v1/actions",
        json={"title": "reject me", "executor": "shell_allowlist", "payload": {"command": "echo reject"}},
    )
    action_id = r.json()["id"]

    r_reject = client.post(f"/api/v1/actions/{action_id}/reject", json={"reason": "not needed"})
    assert r_reject.status_code == 200
    assert r_reject.json()["state"] == "rejected"


def test_get_receipt_after_execution():
    # create + approve + execute
    r = client.post(
        "/api/v1/actions",
        json={"title": "receipt test", "executor": "shell_allowlist", "payload": {"command": "echo receipt"}},
    )
    action_id = r.json()["id"]
    client.post(f"/api/v1/actions/{action_id}/approve")
    exec_data = client.post(f"/api/v1/actions/{action_id}/execute").json()
    receipt_id = exec_data["receipt_id"]

    r_receipt = client.get(f"/api/v1/receipts/{receipt_id}")
    assert r_receipt.status_code == 200
    assert r_receipt.json()["action_id"] == action_id


def test_audit_entries():
    r = client.get("/api/v1/audit?limit=200")
    assert r.status_code == 200
    entries = r.json()
    assert isinstance(entries, list)
    assert len(entries) > 0


def test_execute_non_approved_returns_409():
    r = client.post(
        "/api/v1/actions",
        json={"title": "not approved", "executor": "shell_allowlist", "payload": {"command": "echo no"}},
    )
    action_id = r.json()["id"]
    r_exec = client.post(f"/api/v1/actions/{action_id}/execute")
    assert r_exec.status_code == 409

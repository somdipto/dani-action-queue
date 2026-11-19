"""
FastAPI application.

All routes live under /api/v1.
The dashboard is served from app/static/ at / and /static/*.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.db import init_db
import app.queue as queue
import app.receipts as receipts_mod


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ActionCreate(BaseModel):
    title: str
    executor: Literal["file_organize", "shell_allowlist", "webhook"]
    payload: dict[str, Any]


class ActionOut(BaseModel):
    id: str
    title: str
    executor: str
    payload: dict[str, Any]
    state: str
    created_at: str
    decided_at: Optional[str]
    executed_at: Optional[str]
    receipt_id: Optional[str]
    reject_reason: Optional[str]


class RejectIn(BaseModel):
    reason: str


class ReceiptOut(BaseModel):
    id: str
    action_id: str
    executor: str
    payload_snapshot: dict[str, Any]
    started_at: str
    finished_at: str
    status: str
    result_summary: str
    log_excerpt: str
    integrity_hash: str


class AuditEntryOut(BaseModel):
    id: str
    action_id: str
    from_state: str
    to_state: str
    actor: str
    timestamp: str
    note: Optional[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action_out(a: queue.Action) -> ActionOut:
    return ActionOut(
        id=a.id,
        title=a.title,
        executor=a.executor,
        payload=a.payload,
        state=a.state,
        created_at=a.created_at,
        decided_at=a.decided_at,
        executed_at=a.executed_at,
        receipt_id=a.receipt_id,
        reject_reason=a.reject_reason,
    )


def _receipt_out(r: receipts_mod.Receipt) -> ReceiptOut:
    return ReceiptOut(
        id=r.id,
        action_id=r.action_id,
        executor=r.executor,
        payload_snapshot=r.payload_snapshot,
        started_at=r.started_at,
        finished_at=r.finished_at,
        status=r.status,
        result_summary=r.result_summary,
        log_excerpt=r.log_excerpt,
        integrity_hash=r.integrity_hash,
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Dani Action Queue", version="1.0.0", lifespan=lifespan)

_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(_static_dir / "index.html"))


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@app.post("/api/v1/actions", response_model=ActionOut, status_code=201)
def create_action(body: ActionCreate):
    try:
        action = queue.create_action(body.title, body.executor, body.payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _action_out(action)


@app.get("/api/v1/actions", response_model=list[ActionOut])
def list_actions(
    state: Optional[str] = Query(None),
    executor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    actions = queue.list_actions(state=state, executor=executor, limit=limit, offset=offset)
    return [_action_out(a) for a in actions]


@app.get("/api/v1/actions/{action_id}", response_model=ActionOut)
def get_action(action_id: str):
    action = queue.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found.")
    return _action_out(action)


@app.post("/api/v1/actions/{action_id}/approve", response_model=ActionOut)
def approve_action(action_id: str):
    try:
        action = queue.approve_action(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _action_out(action)


@app.post("/api/v1/actions/{action_id}/reject", response_model=ActionOut)
def reject_action(action_id: str, body: RejectIn):
    try:
        action = queue.reject_action(action_id, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _action_out(action)


@app.post("/api/v1/actions/{action_id}/execute", response_model=ActionOut)
def execute_action(action_id: str):
    try:
        updated_action, _receipt = queue.execute_action(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _action_out(updated_action)


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------

@app.get("/api/v1/receipts", response_model=list[ReceiptOut])
def list_receipts(
    action_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    recs = receipts_mod.list_receipts(action_id=action_id, status=status, limit=limit, offset=offset)
    return [_receipt_out(r) for r in recs]


@app.get("/api/v1/receipts/{receipt_id}", response_model=ReceiptOut)
def get_receipt(receipt_id: str):
    r = receipts_mod.get_receipt(receipt_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return _receipt_out(r)


@app.get("/api/v1/receipts/{receipt_id}/verify")
def verify_receipt(receipt_id: str):
    valid = receipts_mod.verify_receipt(receipt_id)
    if valid is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return {"receipt_id": receipt_id, "valid": valid}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@app.get("/api/v1/audit", response_model=list[AuditEntryOut])
def list_audit(
    action_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    entries = queue.list_audit(action_id=action_id, limit=limit, offset=offset)
    return [AuditEntryOut(**e) for e in entries]

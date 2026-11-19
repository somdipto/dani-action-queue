"""
CLI entry point for Dani Action Queue.

Usage: python -m app.cli  (or `daq` after installation)
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from typing import Any

from app.db import init_db


def _as_dict(obj) -> dict:
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return dict(obj)


def _out(obj) -> None:
    print(json.dumps(_as_dict(obj), indent=2))


def _err(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_action_create(args) -> None:
    import app.queue as q

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        _err(f"Invalid JSON payload: {exc}")

    try:
        action = q.create_action(args.title, args.executor, payload)
    except ValueError as exc:
        _err(str(exc))

    _out(action)


def cmd_action_list(args) -> None:
    import app.queue as q

    actions = q.list_actions(
        state=args.state,
        executor=args.executor,
        limit=args.limit,
        offset=args.offset,
    )
    print(json.dumps([_as_dict(a) for a in actions], indent=2))


def cmd_action_get(args) -> None:
    import app.queue as q

    action = q.get_action(args.id)
    if action is None:
        _err(f"Action '{args.id}' not found.")
    _out(action)


def cmd_action_approve(args) -> None:
    import app.queue as q

    try:
        action = q.approve_action(args.id)
    except ValueError as exc:
        _err(str(exc))
    _out(action)


def cmd_action_reject(args) -> None:
    import app.queue as q

    try:
        action = q.reject_action(args.id, args.reason)
    except ValueError as exc:
        _err(str(exc))
    _out(action)


def cmd_action_execute(args) -> None:
    import app.queue as q

    try:
        updated_action, _receipt = q.execute_action(args.id)
    except ValueError as exc:
        _err(str(exc))
    _out(updated_action)


def cmd_receipt_list(args) -> None:
    import app.receipts as r

    recs = r.list_receipts(
        action_id=args.action_id,
        status=args.status,
        limit=args.limit,
        offset=args.offset,
    )
    print(json.dumps([_as_dict(rc) for rc in recs], indent=2))


def cmd_receipt_get(args) -> None:
    import app.receipts as r

    rec = r.get_receipt(args.id)
    if rec is None:
        _err(f"Receipt '{args.id}' not found.")
    _out(rec)


def cmd_audit_list(args) -> None:
    import app.queue as q

    entries = q.list_audit(action_id=args.action_id, limit=args.limit, offset=args.offset)
    print(json.dumps(entries, indent=2))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daq",
        description="Dani Action Queue CLI",
    )
    sub = parser.add_subparsers(dest="resource", required=True)

    # --- action ---
    action_parser = sub.add_parser("action", help="Manage actions")
    action_sub = action_parser.add_subparsers(dest="action_cmd", required=True)

    # action create
    p_create = action_sub.add_parser("create", help="Create a draft action")
    p_create.add_argument("--title", required=True)
    p_create.add_argument(
        "--executor",
        required=True,
        choices=["file_organize", "shell_allowlist", "webhook"],
    )
    p_create.add_argument("--payload", required=True, help="JSON string")
    p_create.set_defaults(func=cmd_action_create)

    # action list
    p_list = action_sub.add_parser("list", help="List actions")
    p_list.add_argument("--state", default=None)
    p_list.add_argument("--executor", default=None)
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--offset", type=int, default=0)
    p_list.set_defaults(func=cmd_action_list)

    # action get
    p_get = action_sub.add_parser("get", help="Get a single action")
    p_get.add_argument("id")
    p_get.set_defaults(func=cmd_action_get)

    # action approve
    p_approve = action_sub.add_parser("approve", help="Approve a draft action")
    p_approve.add_argument("id")
    p_approve.set_defaults(func=cmd_action_approve)

    # action reject
    p_reject = action_sub.add_parser("reject", help="Reject an action")
    p_reject.add_argument("id")
    p_reject.add_argument("--reason", required=True)
    p_reject.set_defaults(func=cmd_action_reject)

    # action execute
    p_execute = action_sub.add_parser("execute", help="Execute an approved action")
    p_execute.add_argument("id")
    p_execute.set_defaults(func=cmd_action_execute)

    # --- receipt ---
    receipt_parser = sub.add_parser("receipt", help="Manage receipts")
    receipt_sub = receipt_parser.add_subparsers(dest="receipt_cmd", required=True)

    p_rlist = receipt_sub.add_parser("list", help="List receipts")
    p_rlist.add_argument("--action-id", dest="action_id", default=None)
    p_rlist.add_argument("--status", default=None)
    p_rlist.add_argument("--limit", type=int, default=50)
    p_rlist.add_argument("--offset", type=int, default=0)
    p_rlist.set_defaults(func=cmd_receipt_list)

    p_rget = receipt_sub.add_parser("get", help="Get a single receipt")
    p_rget.add_argument("id")
    p_rget.set_defaults(func=cmd_receipt_get)

    # --- audit ---
    audit_parser = sub.add_parser("audit", help="View audit log")
    audit_sub = audit_parser.add_subparsers(dest="audit_cmd", required=True)

    p_alist = audit_sub.add_parser("list", help="List audit entries")
    p_alist.add_argument("--action-id", dest="action_id", default=None)
    p_alist.add_argument("--limit", type=int, default=50)
    p_alist.add_argument("--offset", type=int, default=0)
    p_alist.set_defaults(func=cmd_audit_list)

    return parser


def main(argv: list[str] | None = None) -> None:
    init_db()
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

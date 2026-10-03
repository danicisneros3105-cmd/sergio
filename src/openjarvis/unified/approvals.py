"""Shared approval flow for risky actions (Clacky tasks, calls, messages).

An action is queued in the approval store, shown in the app's approval bell
(and ``sergio approvals``), and only runs once the user approves it. The
payload stored at queue time is authoritative, and the approved→executed
transition is atomic, so one approval runs the action exactly once.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Decision:
    """Outcome of :func:`request_approval`."""

    payload: dict | None  # set when approved and claimed
    action_id: str
    status: str  # "approved", "pending" (timed out), or the final status
    message: str = ""  # explanation for the model when not approved


def find_open(store: Any, action_type: str, payload: dict[str, Any]) -> Any:
    """An earlier, still-open request with the same payload (avoids duplicates)."""
    for action in [*store.list_approved(), *store.list_pending()]:
        if action.action_type == action_type and action.payload == payload:
            return action
    return None


def request_approval(
    store: Any,
    *,
    action_type: str,
    description: str = "",
    payload: dict[str, Any] | None = None,
    approval_id: str = "",
    wait_seconds: float = 300.0,
    validate: Callable[[dict], str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Decision:
    """Queue (or resume, with *approval_id*) an action and wait for the user.

    *validate* may return an error string for an approved payload that can
    no longer run (e.g. a missing folder); the approval is then left unused.
    """
    from openjarvis.tools.approval_store import (
        STATUS_APPROVED,
        STATUS_EXECUTED,
        STATUS_PENDING,
        TIER_HIGH,
    )

    if approval_id:
        action = store.get_action(approval_id)
        if action is None or action.action_type != action_type:
            return Decision(
                None, approval_id, "missing", f"Unknown approval_id '{approval_id}'."
            )
    else:
        payload = payload or {}
        action = find_open(store, action_type, payload) or store.queue_action(
            action_type=action_type,
            description=description,
            payload=payload,
            permission_key=action_type,
            tier=TIER_HIGH,
        )
    action_id = action.id

    deadline = clock() + float(wait_seconds)
    while True:
        action = store.get_action(action_id)
        status = action.status if action else "missing"
        if status == STATUS_APPROVED:
            problem = validate(action.payload) if validate else ""
            if problem:
                return Decision(None, action_id, "invalid", problem)
            if store.transition(action_id, STATUS_APPROVED, STATUS_EXECUTED):
                return Decision(dict(action.payload), action_id, "approved")
            continue  # another call claimed it first; re-read the status
        if status == STATUS_EXECUTED:
            return Decision(
                None,
                action_id,
                status,
                "This approval was already used: the action ran (or was "
                "attempted) once. Ask the user before requesting it again.",
            )
        if status != STATUS_PENDING:
            return Decision(
                None,
                action_id,
                status,
                f"The user did not approve this (status: {status}). "
                "Do not retry unless the user asks again.",
            )
        if clock() >= deadline:
            return Decision(
                None,
                action_id,
                "pending",
                "Still waiting for the user's approval "
                f"(approval_id='{action_id}'). They can approve it in the app's "
                f"approval bell or with `sergio approvals approve {action_id}`. "
                "Tell the user, and call this tool again with this approval_id "
                "once they approve.",
            )
        sleep(1.0)


def default_store() -> Any:
    from openjarvis.tools.approval_store import ApprovalStore

    return ApprovalStore()


__all__ = ["Decision", "default_store", "find_open", "request_approval"]

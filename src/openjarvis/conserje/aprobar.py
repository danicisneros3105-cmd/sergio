"""The owner's yes for the last step (buy, book, publish, send, unlock)."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

Approver = Callable[[str, Dict[str, Any]], bool]
WAIT = 300.0


def owner_yes(
    what: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    approver: Optional[Approver] = None,
    timeout: float = WAIT,
) -> bool:
    """True only when the owner said yes: Sergio's Face ID on the PC, or the
    approvals bell in the app. No answer is a no."""
    if approver is not None:
        return bool(approver(what, payload or {}))
    try:
        from openjarvis.tools.desktop_tools import FaceApprovalTool

        if FaceApprovalTool().execute(what=what).success:
            return True
    except Exception:  # noqa: BLE001 — no desktop: the bell
        pass
    try:
        from openjarvis.tools.approval_store import (
            STATUS_APPROVED,
            STATUS_DENIED,
            ApprovalStore,
        )

        store = ApprovalStore()
        action = store.queue_action(
            action_type="conserje",
            description=what,
            payload=payload or {},
            permission_key="conserje:" + what[:40],
            tier="high",
            ttl_hours=1,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = store.get_action(action.id)
            if current is not None and current.status == STATUS_APPROVED:
                store.update_status(action.id, "executed")
                return True
            if current is not None and current.status == STATUS_DENIED:
                return False
            time.sleep(0.5)
        store.update_status(action.id, "expired")
    except Exception:  # noqa: BLE001 — no store: no yes
        return False
    return False


__all__ = ["owner_yes"]

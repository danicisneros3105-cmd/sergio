"""``sergio approvals`` — review actions waiting for the user's approval.

The same queue backs the approval bell in the web UI; this command lets a
terminal-only user approve or deny, e.g. a pending ``clacky_task``.
"""

from __future__ import annotations

import click
from rich.console import Console
from rich.markup import escape

console = Console()


def _store():
    from openjarvis.tools.approval_store import ApprovalStore

    return ApprovalStore()


@click.group()
def approvals() -> None:
    """List, approve or deny actions waiting for your approval."""


@approvals.command("list")
def list_cmd() -> None:
    """Show pending actions."""
    store = _store()
    store.expire_stale()
    pending = store.list_pending()
    if not pending:
        console.print("No pending approvals.")
        return
    for action in pending:
        # One line per action so ids stay copyable on narrow terminals.
        console.print(
            f"[bold]{action.id}[/bold]  {escape(f'[{action.tier}]')}  "
            f"{escape(action.description)}",
            soft_wrap=True,
        )
    console.print("Approve with: sergio approvals approve <ID>")


def _decide(action_id: str, status: str) -> None:
    from openjarvis.tools.approval_store import STATUS_PENDING

    store = _store()
    action = store.get_action(action_id)
    if action is None:
        raise click.ClickException(f"No action with id {action_id}")
    if not store.transition(action_id, STATUS_PENDING, status):
        raise click.ClickException(
            f"Action {action_id} is not pending (status: {action.status})"
        )
    console.print(f"{action_id}: {status} — {escape(action.description)}")


@approvals.command("approve")
@click.argument("action_id")
def approve(action_id: str) -> None:
    """Approve a pending action."""
    from openjarvis.tools.approval_store import STATUS_APPROVED

    _decide(action_id, STATUS_APPROVED)


@approvals.command("deny")
@click.argument("action_id")
def deny(action_id: str) -> None:
    """Deny a pending action."""
    from openjarvis.tools.approval_store import STATUS_DENIED

    _decide(action_id, STATUS_DENIED)

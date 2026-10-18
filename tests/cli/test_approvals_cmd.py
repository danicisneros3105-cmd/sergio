"""Tests for `sergio approvals`."""

from __future__ import annotations

from click.testing import CliRunner

from openjarvis.cli.approvals_cmd import approvals
from openjarvis.tools.approval_store import ApprovalStore


def _queue() -> str:
    return (
        ApprovalStore()
        .queue_action(
            action_type="clacky_task",
            description="El agente de código hará en su equipo: tidy Downloads",
            payload={"task": "tidy Downloads"},
            permission_key="clacky_task",
            tier="high",
        )
        .id
    )


def test_list_approve_and_refuse_twice():
    action_id = _queue()
    runner = CliRunner()
    listed = runner.invoke(approvals, ["list"])
    assert action_id in listed.output and "tidy Downloads" in listed.output
    assert "[high]" in listed.output

    assert runner.invoke(approvals, ["approve", action_id]).exit_code == 0
    assert ApprovalStore().get_action(action_id).status == "approved"
    again = runner.invoke(approvals, ["deny", action_id])
    assert again.exit_code != 0 and "not pending" in again.output
    assert runner.invoke(approvals, ["approve", "nope"]).exit_code != 0

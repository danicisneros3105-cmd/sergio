"""Delegate hands-on tasks to the bundled OpenClacky agent.

OpenClacky drives the terminal, the file system and the user's real Chrome
(via chrome-devtools-mcp). OpenJarvis keeps planning, memory and scheduling,
and hands concrete computer work to OpenClacky with this tool. Both agents
share the same model through :mod:`openjarvis.unified.model_bridge`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_TOOL_NAME = "clacky_task"
_MAX_OUTPUT_CHARS = 8000

Runner = Callable[..., subprocess.CompletedProcess]


def summarize_events(stdout: str) -> tuple[str, list[str], str, float]:
    """Parse OpenClacky NDJSON output.

    Returns ``(final_message, tool_names, error, cost_usd)``.
    """
    messages: list[str] = []
    tools: list[str] = []
    error = ""
    cost = 0.0
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "assistant_message" and event.get("content"):
            messages.append(str(event["content"]))
        elif kind == "tool_call" and event.get("name"):
            tools.append(str(event["name"]))
        elif kind == "error":
            error = str(event.get("message") or event.get("error") or "unknown error")
        elif kind == "done":
            try:
                cost = float(event.get("total_cost") or 0.0)
            except (TypeError, ValueError):
                cost = 0.0
    return (messages[-1] if messages else ""), tools, error, cost


@ToolRegistry.register(_TOOL_NAME)
class ClackyTaskTool(BaseTool):
    """Run one task end-to-end with the OpenClacky agent."""

    tool_id = _TOOL_NAME

    def __init__(
        self,
        *,
        config: Any = None,
        runner: Runner = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        approvals: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if config is None:
            from openjarvis.core.config import load_config

            config = load_config()
        self._config = config
        self._runner = runner
        self._which = which
        self._approvals = approvals
        self._sleep = sleep
        self._clock = clock

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=_TOOL_NAME,
            description=(
                "Delegate a hands-on computer task to the OpenClacky agent, which "
                "can run terminal commands, read and write files, search the web "
                "and control the user's Chrome browser (open sites, click, type, "
                "fill forms). Use it for multi-step tasks on the user's computer "
                "such as organizing files, installing apps or operating a website. "
                "Describe the goal completely; the agent works autonomously and "
                "returns a summary of what it did. Every task waits for the user's "
                "approval in the app's approval bell before it runs; if the result "
                "says it is still waiting, call again later with the same "
                "approval_id."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Complete description of the task to perform.",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Directory to work in (default: user's home).",
                    },
                    "approval_id": {
                        "type": "string",
                        "description": "Id returned by an earlier call that was "
                        "still waiting for approval.",
                    },
                },
                "required": ["task"],
            },
            category="agent",
            # Approval is handled by the tool itself through the approval queue
            # (works in the web UI, where no interactive callback exists).
            requires_confirmation=False,
            timeout_seconds=float(self._config.extensions.clacky.timeout_seconds)
            + float(self._config.extensions.clacky.approval_wait_seconds),
        )

    def _store(self) -> Any:
        if self._approvals is None:
            from openjarvis.tools.approval_store import ApprovalStore

            self._approvals = ApprovalStore()
        return self._approvals

    def _approve(self, params: dict[str, Any]) -> tuple[dict | None, ToolResult | None]:
        """Queue (or look up) the task and wait for the user's decision.

        Returns ``(payload, None)`` when approved — the payload stored at
        queue time is authoritative, so the task cannot change after the
        user approved it — or ``(None, result)`` to return to the model.
        """
        from openjarvis.tools.approval_store import (
            STATUS_APPROVED,
            STATUS_EXECUTED,
            STATUS_PENDING,
        )

        store = self._store()
        action_id = str(params.get("approval_id") or "").strip()
        if action_id:
            action = store.get_action(action_id)
            if action is None or action.action_type != _TOOL_NAME:
                return None, self._fail(f"Unknown approval_id '{action_id}'.")
        else:
            task = str(params.get("task") or "").strip()
            if not task:
                return None, self._fail("The 'task' parameter is required.")
            workdir = str(params.get("working_dir") or Path.home())
            action = store.queue_action(
                action_type=_TOOL_NAME,
                description=f"Clacky will do on your computer: {task}",
                payload={"task": task, "working_dir": workdir},
                permission_key=_TOOL_NAME,
                tier="confirm",
            )
            action_id = action.id

        deadline = self._clock() + float(
            self._config.extensions.clacky.approval_wait_seconds
        )
        while True:
            action = store.get_action(action_id)
            status = action.status if action else "missing"
            if status == STATUS_APPROVED:
                store.update_status(action_id, STATUS_EXECUTED)
                return dict(action.payload), None
            if status != STATUS_PENDING:
                return None, self._fail(
                    f"The user did not approve this task (status: {status}). "
                    "Do not retry unless the user asks again."
                )
            if self._clock() >= deadline:
                return None, ToolResult(
                    tool_name=_TOOL_NAME,
                    content=(
                        "Still waiting for the user's approval in the approval "
                        f"bell (approval_id='{action_id}'). Tell the user, and "
                        "call clacky_task again with this approval_id once they "
                        "approve."
                    ),
                    success=False,
                    metadata={"approval_id": action_id, "pending": True},
                )
            self._sleep(1.0)

    def _fail(self, message: str) -> ToolResult:
        return ToolResult(tool_name=_TOOL_NAME, content=message, success=False)

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.unified.model_bridge import ModelBridgeError, clacky_env
        from openjarvis.unified.paths import extension_dir

        if not str(params.get("task") or params.get("approval_id") or "").strip():
            return self._fail("The 'task' parameter is required.")
        cfg = self._config.extensions.clacky
        if not cfg.enabled:
            return self._fail("OpenClacky is disabled ([extensions.clacky] enabled).")
        root = extension_dir("clacky", cfg.path)
        if root is None:
            return self._fail(
                "OpenClacky is not installed (extensions/clacky missing)."
            )
        bundle = self._which("bundle")
        if bundle is None or self._which("ruby") is None:
            return self._fail("OpenClacky needs Ruby and Bundler; run the installer.")
        try:
            env = {**os.environ, **clacky_env(self._config)}
        except ModelBridgeError as exc:
            return self._fail(str(exc))
        env["BUNDLE_GEMFILE"] = str(root / "Gemfile")

        requested = Path(params.get("working_dir") or Path.home()).expanduser()
        if not params.get("approval_id") and not requested.is_dir():
            return self._fail(f"Working directory does not exist: {requested}")

        approved, refusal = self._approve(params)
        if refusal is not None:
            return refusal
        task = str(approved["task"])
        workdir = Path(approved["working_dir"]).expanduser()
        if not workdir.is_dir():
            return self._fail(f"Working directory does not exist: {workdir}")

        cmd = [
            bundle, "exec", "ruby", str(root / "bin" / "clacky"), "agent",
            "--json", "--path", str(workdir), "-m", task,
        ]  # fmt: skip
        try:
            done = self._runner(
                cmd,
                cwd=str(workdir),
                env=env,
                capture_output=True,
                text=True,
                timeout=float(cfg.timeout_seconds),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return self._fail(
                f"OpenClacky did not finish within {cfg.timeout_seconds:.0f}s."
            )
        except OSError as exc:
            return self._fail(f"Could not start OpenClacky: {exc}")

        final, tools, error, cost = summarize_events(done.stdout or "")
        if done.returncode != 0 or error:
            detail = error or (done.stderr or "").strip()[-1000:] or "no output"
            return ToolResult(
                tool_name=_TOOL_NAME,
                content=f"OpenClacky failed: {detail}",
                success=False,
                cost_usd=cost,
                metadata={"tools_used": tools},
            )
        lines = [final or "Task finished (no summary returned)."]
        if tools:
            lines.append(f"\nActions taken: {', '.join(tools)}")
        return ToolResult(
            tool_name=_TOOL_NAME,
            content="\n".join(lines)[:_MAX_OUTPUT_CHARS],
            cost_usd=cost,
            metadata={"tools_used": tools},
        )


__all__ = ["ClackyTaskTool", "summarize_events"]

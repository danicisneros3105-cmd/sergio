"""Shell execution tool — run shell commands with security constraints."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.security.process_runner import run_bounded
from openjarvis.tools._stubs import BaseTool, ToolSpec

# Maximum output size per stream (100 KB)
_MAX_OUTPUT_BYTES = 102_400

# Maximum allowed timeout (seconds)
_MAX_TIMEOUT = 300

# Default timeout (seconds)
_DEFAULT_TIMEOUT = 30

# Environment variables always passed through on every platform.
_PORTABLE_ENV_KEYS = (
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "TERM",
)

# Windows needs these to bootstrap ordinary child processes: missing
# SystemRoot breaks Winsock/DNS initialization, while missing LOCALAPPDATA
# can make the Store Python launcher provision a fresh interpreter in cwd.
# Keep them conditional so a POSIX host that happens to define similarly
# named variables does not expand the tool's minimal environment.
_WINDOWS_ENV_KEYS = (
    "SystemRoot",
    "SystemDrive",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
)
_BASE_ENV_KEYS = _PORTABLE_ENV_KEYS + (_WINDOWS_ENV_KEYS if os.name == "nt" else ())


@ToolRegistry.register("shell_exec")
class ShellExecTool(BaseTool):
    """Execute shell commands with a sanitised environment."""

    tool_id = "shell_exec"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="shell_exec",
            description=(
                "Execute a shell command and return its stdout/stderr."
                " Runs with a minimal environment for security."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": ("Timeout in seconds (default 30, max 300)."),
                    },
                    "working_dir": {
                        "type": "string",
                        "description": (
                            "Working directory for the command."
                            " Must exist and be a directory."
                        ),
                    },
                    "env_passthrough": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Additional environment variable names"
                            " to pass through from the host."
                        ),
                    },
                },
                "required": ["command"],
            },
            category="system",
            requires_confirmation=True,
            timeout_seconds=float(_MAX_TIMEOUT + 15),
            required_capabilities=["code:execute"],
        )

    def execute(self, **params: Any) -> ToolResult:
        command = params.get("command", "")
        if not isinstance(command, str) or not command.strip():
            return ToolResult(
                tool_name="shell_exec",
                content="No command provided.",
                success=False,
            )

        # Resolve timeout (capped at _MAX_TIMEOUT)
        timeout = params.get("timeout", _DEFAULT_TIMEOUT)
        try:
            timeout = int(timeout)
        except (TypeError, ValueError, OverflowError):
            timeout = _DEFAULT_TIMEOUT
        if timeout < 1:
            timeout = 1
        if timeout > _MAX_TIMEOUT:
            timeout = _MAX_TIMEOUT

        # Validate working_dir
        working_dir = params.get("working_dir")
        if working_dir is not None:
            if not isinstance(working_dir, (str, os.PathLike)):
                return ToolResult(
                    tool_name="shell_exec",
                    content="Invalid working_dir.",
                    success=False,
                )
            wd_path = Path(working_dir)
            if not wd_path.exists():
                return ToolResult(
                    tool_name="shell_exec",
                    content=f"Working directory does not exist: {working_dir}",
                    success=False,
                )
            if not wd_path.is_dir():
                return ToolResult(
                    tool_name="shell_exec",
                    content=f"Working directory is not a directory: {working_dir}",
                    success=False,
                )

        # Build sanitised environment
        env: dict[str, str] = {}
        for key in _BASE_ENV_KEYS:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val

        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env_passthrough: List[str] = params.get("env_passthrough") or []
        if not isinstance(env_passthrough, (list, tuple)) or any(
            not isinstance(key, str) for key in env_passthrough
        ):
            return ToolResult(
                tool_name="shell_exec",
                content="env_passthrough must be a list of names.",
                success=False,
            )
        for key in env_passthrough:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val

        mode = os.environ.get("SERGIO_EXECUTION_MODE", "local")
        if mode not in {"local", "container"}:
            return ToolResult(
                tool_name="shell_exec", content="Unknown execution mode.", success=False
            )
        try:
            if mode == "container":
                from openjarvis.security.project_execution import run_in_project

                if env_passthrough:
                    return ToolResult(
                        tool_name="shell_exec",
                        content="Host environment passthrough is disabled in container mode.",
                        success=False,
                    )
                result = run_in_project(
                    command, timeout=timeout, working_dir=working_dir
                )
            else:
                result = run_bounded(
                    command,
                    shell=True,
                    timeout=timeout,
                    cwd=working_dir,
                    env=env,
                    max_output_bytes=_MAX_OUTPUT_BYTES,
                )
        except (OSError, ValueError, RuntimeError) as exc:
            return ToolResult(
                tool_name="shell_exec", content=f"Execution error: {exc}", success=False
            )
        stdout, stderr = result.stdout, result.stderr
        if result.truncated:
            stdout += "\n... (output truncated)"
        if result.timed_out:
            return ToolResult(
                tool_name="shell_exec",
                content=f"Command timed out after {timeout} seconds.",
                success=False,
                metadata={
                    "returncode": -1,
                    "timeout_used": timeout,
                    "working_dir": working_dir,
                    "execution_mode": mode,
                },
            )

        # Format output
        sections: list[str] = []
        if stdout:
            sections.append(f"=== STDOUT ===\n{stdout}")
        if stderr:
            sections.append(f"=== STDERR ===\n{stderr}")
        content = "\n".join(sections) if sections else "(no output)"

        return ToolResult(
            tool_name="shell_exec",
            content=content,
            success=result.returncode == 0,
            metadata={
                "returncode": result.returncode,
                "timeout_used": timeout,
                "working_dir": working_dir,
                "execution_mode": mode,
                "output_truncated": result.truncated,
            },
        )


__all__ = ["ShellExecTool"]

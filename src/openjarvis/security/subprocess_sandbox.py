"""Subprocess sandbox — secure process execution with environment isolation."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Safe environment variables to pass through
_SAFE_ENV_VARS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "TERM",
        "SHELL",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "TZ",
    }
)


@dataclass(slots=True)
class SandboxResult:
    """Result of a sandboxed subprocess execution."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    timed_out: bool = False
    killed: bool = False


def build_safe_env(
    passthrough: Optional[List[str]] = None,
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build a sanitized environment dict.

    Only copies safe vars from current env, plus any in passthrough list.
    Extra vars are added directly.
    """
    env: Dict[str, str] = {}
    allowed = _SAFE_ENV_VARS | frozenset(passthrough or [])
    for key in allowed:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    if extra:
        env.update(extra)
    return env


def kill_process_tree(pid: int) -> None:
    """Kill a process and its children, using the host platform's process API."""
    if type(pid) is not int or pid <= 0:
        raise ValueError("A positive process ID is required")
    if os.name == "nt":
        try:
            subprocess.run(
                [
                    os.path.join(
                        os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32",
                        "taskkill.exe",
                    ),
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                ],
                capture_output=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("Failed to terminate process %d: %s", pid, exc)
        return
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError) as exc:
        logger.debug("Failed to terminate process %d: %s", pid, exc)
    try:
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError) as exc:
        logger.debug("Failed to kill process %d: %s", pid, exc)


def run_sandboxed(
    command: str,
    *,
    timeout: float = 30.0,
    working_dir: Optional[str] = None,
    env_passthrough: Optional[List[str]] = None,
    env_extra: Optional[Dict[str, str]] = None,
    max_output_bytes: int = 102_400,
) -> SandboxResult:
    """Execute a command in a sandboxed subprocess.

    Features:
    - Clean environment (only safe vars passed through)
    - Timeout enforcement with process tree kill
    - Output truncation
    - New process group for clean cleanup
    """
    env = build_safe_env(passthrough=env_passthrough, extra=env_extra)
    cwd = working_dir if working_dir and os.path.isdir(working_dir) else None

    from openjarvis.security.process_runner import run_bounded

    try:
        captured = run_bounded(
            command,
            shell=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            max_output_bytes=max_output_bytes,
        )
    except (OSError, ValueError) as exc:
        return SandboxResult(stderr=f"Execution error: {exc}")
    return SandboxResult(
        stdout=captured.stdout,
        stderr=captured.stderr,
        returncode=captured.returncode,
        timed_out=captured.timed_out,
        killed=captured.timed_out,
    )


__all__ = ["SandboxResult", "build_safe_env", "kill_process_tree", "run_sandboxed"]

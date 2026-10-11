"""Bounded process capture and cleanup; this is not filesystem isolation."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass
class ProcessResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    timed_out: bool = False
    truncated: bool = False


def terminate_tree(proc: subprocess.Popen) -> None:
    """Terminate our new process group, including children holding pipes."""
    if os.name == "nt":
        subprocess.run(
            [
                os.path.join(
                    os.environ.get("SystemRoot", r"C:\Windows"),
                    "System32",
                    "taskkill.exe",
                ),
                "/PID",
                str(proc.pid),
                "/T",
                "/F",
            ],
            capture_output=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if proc.poll() is None:
            proc.kill()
    else:
        # start_new_session makes this PID the group ID; never target ours.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_bounded(
    command: str | Sequence[str],
    *,
    timeout: float = 30,
    cwd: str | os.PathLike | None = None,
    env: Mapping[str, str] | None = None,
    shell: bool = False,
    max_output_bytes: int = 102_400,
    max_memory_bytes: int | None = None,
) -> ProcessResult:
    """Drain both pipes concurrently, keeping at most the limit per stream."""
    if not math.isfinite(timeout) or timeout <= 0 or max_output_bytes < 1:
        raise ValueError("Timeout and output limit must be positive")
    result = ProcessResult()
    proc = subprocess.Popen(
        command,
        # Shell commands are an explicit caller API, behind tool confirmation.
        shell=shell,  # nosec B602
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        start_new_session=os.name != "nt",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | (0x4 if os.name == "nt" else 0),
    )
    job = None
    if os.name == "nt":
        from .windows_job import WindowsJob

        try:
            job = WindowsJob(int(proc._handle), memory_bytes=max_memory_bytes)
        except BaseException:
            # No uncontained execution if attachment fails.
            proc.kill()
            proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()
            raise
    buffers = [bytearray(), bytearray()]

    def drain(stream, target):
        try:
            while block := stream.read(8192):
                remaining = max_output_bytes - len(target)
                target.extend(block[: max(0, remaining)])
                if len(block) > remaining:
                    result.truncated = True
        finally:
            stream.close()

    readers = [
        threading.Thread(target=drain, args=(pipe, target), daemon=True)
        for pipe, target in zip((proc.stdout, proc.stderr), buffers)
    ]
    deadline = time.monotonic() + timeout
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=max(0.001, deadline - time.monotonic()))
        for reader in readers:
            reader.join(max(0, deadline - time.monotonic()))
        if any(reader.is_alive() for reader in readers):
            raise subprocess.TimeoutExpired(command, timeout)
        result.returncode = proc.returncode
    except subprocess.TimeoutExpired:
        result.timed_out = True
        if job:
            job.terminate()
        else:
            terminate_tree(proc)
        proc.wait(timeout=5)
    finally:
        # Clean children even when the shell exits normally and closes pipes.
        if job:
            job.close()
        elif os.name != "nt":
            terminate_tree(proc)
        for reader in readers:
            reader.join(1)
    result.stdout = bytes(buffers[0]).decode("utf-8", errors="replace")
    result.stderr = bytes(buffers[1]).decode("utf-8", errors="replace")
    # A bounded buffer can end inside a valid UTF-8 character.
    if result.truncated:
        result.stdout = bytes(buffers[0]).decode("utf-8", errors="ignore")
        result.stderr = bytes(buffers[1]).decode("utf-8", errors="ignore")
    return result


__all__ = ["ProcessResult", "terminate_tree", "run_bounded"]

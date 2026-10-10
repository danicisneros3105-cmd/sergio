"""Owner-configured, offline container execution for one project."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

from openjarvis.security.process_runner import ProcessResult, run_bounded


def run_in_project(
    command: str, *, timeout: float, working_dir: str | None
) -> ProcessResult:
    """Fail closed; runtime, image and project are controlled by the owner."""
    configured = os.environ.get("SERGIO_PROJECT_ROOT", "")
    if not configured:
        raise ValueError("Set SERGIO_PROJECT_ROOT before using container mode")
    root = Path(configured).resolve(strict=True)
    if not root.is_dir() or root == Path(root.anchor) or root == Path.home().resolve():
        raise ValueError("Choose a project directory, not a disk root or home")
    work = Path(working_dir).resolve(strict=True) if working_dir else root
    if not work.is_dir() or not work.is_relative_to(root):
        raise ValueError("Working directory must stay inside SERGIO_PROJECT_ROOT")
    if any(char in str(root) for char in (",", "\n", "\r")):
        raise ValueError("Project path cannot contain mount separators")
    runtime = shutil.which("docker") or shutil.which("podman")
    if runtime is None:
        raise RuntimeError(
            "Container mode requires Docker or Podman; no local fallback"
        )
    image = os.environ.get("SERGIO_SANDBOX_IMAGE", "python:3.12-slim")
    if not image or image.startswith("-") or any(c.isspace() for c in image):
        raise ValueError("Invalid container image")
    name = "sergio-project-" + uuid.uuid4().hex
    args = [
        runtime,
        "run",
        "--rm",
        "--pull=never",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=128",
        "--memory=512m",
        "--cpus=2",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--mount",
        f"type=bind,src={root},dst=/workspace",
        "--workdir",
        "/workspace/" + work.relative_to(root).as_posix(),
    ]
    if os.name != "nt":
        args.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    args.extend(["--entrypoint", "/bin/sh", image, "-c", command])
    # Do not inherit credentials or Docker context changes from tool params.
    env = {
        k: os.environ[k]
        for k in ("PATH", "HOME", "SystemRoot", "USERPROFILE")
        if k in os.environ
    }
    try:
        return run_bounded(args, timeout=timeout, env=env)
    finally:
        # Killing a CLI does not stop its container. Remove our unique instance.
        subprocess.run(
            [runtime, "rm", "-f", name],
            capture_output=True,
            timeout=10,
            env=env,
            check=False,
        )


__all__ = ["run_in_project"]

"""Real process regressions and owner-controlled project boundaries."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from openjarvis.security.process_runner import ProcessResult, run_bounded
from openjarvis.security.project_execution import run_in_project
from openjarvis.tools.shell_exec import ShellExecTool


def test_both_output_streams_are_bounded_while_draining():
    result = run_bounded(
        [
            sys.executable,
            "-c",
            "import sys;sys.stdout.write('x'*2000000);sys.stderr.write('y'*2000000)",
        ],
        timeout=10,
        max_output_bytes=4096,
    )
    assert result.returncode == 0 and result.truncated
    assert result.stdout == "x" * 4096
    assert result.stderr == "y" * 4096


@pytest.mark.parametrize("parent_exits", [False, True])
def test_timeout_stops_child_even_if_shell_exits(tmp_path, parent_exits):
    marker = tmp_path / "escaped.txt"
    child = f"import time;from pathlib import Path;time.sleep(1.5);Path({str(marker)!r}).write_text('escaped')"
    parent = (
        f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);"
        + ("" if parent_exits else "time.sleep(10)")
    )
    result = run_bounded([sys.executable, "-c", parent], timeout=0.2)
    assert result.timed_out
    time.sleep(1.7)
    assert not marker.exists()


def test_container_mode_never_falls_back_to_host(tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_EXECUTION_MODE", "container")
    monkeypatch.setenv("SERGIO_PROJECT_ROOT", str(tmp_path))
    with patch("openjarvis.security.project_execution.shutil.which", return_value=None):
        with patch("openjarvis.tools.shell_exec.run_bounded") as local:
            result = ShellExecTool().execute(command="echo unsafe")
    assert not result.success and "no local fallback" in result.content
    local.assert_not_called()


def test_project_boundary_resolves_symlinks(tmp_path, monkeypatch):
    root, outside = tmp_path / "project", tmp_path / "other"
    root.mkdir()
    outside.mkdir()
    monkeypatch.setenv("SERGIO_PROJECT_ROOT", str(root))
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError, match="inside"):
        run_in_project("echo hello", timeout=1, working_dir=str(link))


def test_container_is_offline_limited_and_always_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_PROJECT_ROOT", str(tmp_path))
    with patch(
        "openjarvis.security.project_execution.shutil.which", return_value="/bin/docker"
    ):
        with patch(
            "openjarvis.security.project_execution.run_bounded",
            return_value=ProcessResult(timed_out=True),
        ) as execute:
            with patch(
                "openjarvis.security.project_execution.subprocess.run"
            ) as cleanup:
                result = run_in_project("echo report", timeout=1, working_dir=None)
    args = execute.call_args.args[0]
    for option in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--pull=never",
        "--memory=512m",
        "--pids-limit=128",
        "--cpus=2",
    ):
        assert option in args
    assert result.timed_out
    assert cleanup.call_args.args[0][1:3] == ["rm", "-f"]
    assert cleanup.call_args.args[0][-1] == args[args.index("--name") + 1]


def test_separately_installed_desktop_uses_identical_process_helper():
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/openjarvis/security/process_runner.py").read_bytes() == (
        root / "windows/sergio_escritorio/process_runner.py"
    ).read_bytes()
    assert (root / "src/openjarvis/security/windows_job.py").read_bytes() == (
        root / "windows/sergio_escritorio/windows_job.py"
    ).read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="Requires a real Windows Job Object")
def test_windows_job_enforces_memory_budget():
    result = run_bounded(
        [sys.executable, "-c", "data=bytearray(500*1024*1024)"],
        timeout=5,
        max_memory_bytes=128 * 1024 * 1024,
    )
    assert result.returncode != 0

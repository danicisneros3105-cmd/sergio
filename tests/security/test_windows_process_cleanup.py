"""Platform-specific process cleanup must not call POSIX APIs on Windows."""

import os
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from openjarvis.security import subprocess_sandbox as sandbox


def windows_api(monkeypatch):
    posix_kill = Mock(side_effect=AssertionError("POSIX API used on Windows"))
    api = SimpleNamespace(
        name="nt",
        path=os.path,
        environ={"SystemRoot": r"C:\Windows"},
        kill=posix_kill,
        getpgid=posix_kill,
        killpg=posix_kill,
    )
    monkeypatch.setattr(sandbox, "os", api)
    return posix_kill


def test_windows_terminates_descendants_without_a_shell(monkeypatch):
    posix = windows_api(monkeypatch)
    run = Mock()
    monkeypatch.setattr(sandbox.subprocess, "run", run)
    sandbox.kill_process_tree(4321)
    args, kwargs = run.call_args
    assert args[0][0].endswith("taskkill.exe")
    assert args[0][1:] == ["/PID", "4321", "/T", "/F"]
    assert not kwargs.get("shell", False) and kwargs["timeout"] == 5
    posix.assert_not_called()


@pytest.mark.parametrize(
    "error", [OSError("missing"), subprocess.TimeoutExpired("taskkill", 5)]
)
def test_windows_cleanup_failure_remains_best_effort(monkeypatch, error):
    posix = windows_api(monkeypatch)
    monkeypatch.setattr(sandbox.subprocess, "run", Mock(side_effect=error))
    sandbox.kill_process_tree(4321)
    posix.assert_not_called()


@pytest.mark.parametrize("pid", [0, -1, True, "4321"])
def test_never_target_process_groups_or_unvalidated_ids(pid):
    with pytest.raises(ValueError, match="positive process ID"):
        sandbox.kill_process_tree(pid)

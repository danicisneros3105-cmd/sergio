"""Public shell contract with real local processes and a native backend present."""

from __future__ import annotations

import importlib
import os
import shlex
import subprocess
import sys
from unittest.mock import patch

import pytest

from openjarvis.tools.shell_exec import ShellExecTool


def python_command(code):
    args = [sys.executable, "-c", code]
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


def test_registration_and_spec():
    import openjarvis.tools as tools_pkg
    from openjarvis.core.registry import ToolRegistry

    sys.modules.pop("openjarvis.tools.shell_exec", None)
    importlib.reload(tools_pkg)
    assert ToolRegistry.contains("shell_exec")
    tool = ShellExecTool()
    assert tool.spec.requires_confirmation
    assert "code:execute" in tool.spec.required_capabilities
    assert tool.to_openai_function()["function"]["name"] == "shell_exec"


@pytest.mark.parametrize("command", [None, "", "  ", {"command": "echo"}])
def test_invalid_command_never_starts_process(command):
    with patch("openjarvis.tools.shell_exec.subprocess.run") as run:
        assert not ShellExecTool().execute(command=command).success
    run.assert_not_called()


def test_output_stderr_and_failed_status_with_native_available():
    with patch("openjarvis._rust_bridge.get_rust_module") as native:
        result = ShellExecTool().execute(
            command=python_command(
                "import sys;print('build output');print('failure detail',file=sys.stderr);sys.exit(42)"
            )
        )
    native.assert_not_called()
    assert not result.success
    assert result.metadata["returncode"] == 42
    assert "build output" in result.content and "failure detail" in result.content


def test_success_and_empty_output():
    result = ShellExecTool().execute(command=python_command("print(42)"))
    assert result.success and "42" in result.content
    assert result.metadata["returncode"] == 0
    assert (
        ShellExecTool().execute(command=python_command("pass")).content == "(no output)"
    )


def test_timeout_applies_even_with_native_available():
    with patch("openjarvis._rust_bridge.get_rust_module") as native:
        result = ShellExecTool().execute(
            command=python_command("import time;time.sleep(5)"), timeout=1
        )
    native.assert_not_called()
    assert not result.success and "timed out" in result.content
    assert result.metadata["returncode"] == -1
    assert result.metadata["timeout_used"] == 1


@pytest.mark.parametrize(
    "timeout, expected", [(999, 300), (-1, 1), ("bad", 30), (None, 30)]
)
def test_timeout_boundaries(timeout, expected):
    with patch("openjarvis.tools.shell_exec.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess("command", 0, "ok", "")
        result = ShellExecTool().execute(command="echo ok", timeout=timeout)
    assert result.success
    assert run.call_args.kwargs["timeout"] == expected


def test_working_directory_and_invalid_paths(tmp_path):
    result = ShellExecTool().execute(
        command=python_command("import os;print(os.getcwd())"),
        working_dir=str(tmp_path),
    )
    assert result.success and str(tmp_path) in result.content
    assert result.metadata["working_dir"] == str(tmp_path)
    file = tmp_path / "file.txt"
    file.write_text("data")
    for path in (file, tmp_path / "missing"):
        with patch("openjarvis.tools.shell_exec.subprocess.run") as run:
            assert (
                not ShellExecTool()
                .execute(command="echo", working_dir=str(path))
                .success
            )
        run.assert_not_called()


def test_environment_is_minimal_and_explicit_passthrough_works(monkeypatch):
    marker = "OPENJARVIS_TEST_SHELL_PRIVATE"
    monkeypatch.setenv(marker, "private-test-value")
    command = python_command(f"import os;print(os.environ.get('{marker}', 'absent'))")
    with patch("openjarvis._rust_bridge.get_rust_module") as native:
        denied = ShellExecTool().execute(command=command)
        allowed = ShellExecTool().execute(command=command, env_passthrough=[marker])
    native.assert_not_called()
    assert denied.success and "private-test-value" not in denied.content
    assert allowed.success and "private-test-value" in allowed.content


@pytest.mark.parametrize("names", ["PATH", [123]])
def test_invalid_environment_names_rejected(names):
    with patch("openjarvis.tools.shell_exec.subprocess.run") as run:
        assert (
            not ShellExecTool().execute(command="echo", env_passthrough=names).success
        )
    run.assert_not_called()


def test_large_unicode_output_is_truncated_by_bytes():
    result = ShellExecTool().execute(command=python_command("print('é' * 100000)"))
    assert result.success and "truncated" in result.content
    assert len(result.content.encode("utf-8")) < 103000
    assert "\ufffd" not in result.content


@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("failed")])
def test_spawn_errors_are_failures(error):
    with patch("openjarvis.tools.shell_exec.subprocess.run", side_effect=error):
        assert not ShellExecTool().execute(command="echo").success


def test_platform_base_environment(monkeypatch):
    from openjarvis.tools.shell_exec import _BASE_ENV_KEYS

    monkeypatch.setenv("SystemRoot", "C:\\Windows")
    with patch("openjarvis.tools.shell_exec.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess("command", 0, "", "")
        ShellExecTool().execute(command="echo")
    assert ("SystemRoot" in run.call_args.kwargs["env"]) == (
        "SystemRoot" in _BASE_ENV_KEYS
    )

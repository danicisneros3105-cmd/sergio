"""Repeat a developer's build/review loop without real services or credentials."""

import json
import os
import shlex
import subprocess
import sys
from unittest.mock import patch

import pytest

from openjarvis.core.types import ToolCall
from openjarvis.tools._stubs import ToolExecutor
from openjarvis.tools.code_interpreter import CodeInterpreterTool
from openjarvis.tools.repl import ReplTool
from openjarvis.tools.shell_exec import ShellExecTool


def command(code):
    argv = [sys.executable, "-c", code]
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def test_repeated_developer_builds_keep_failures_and_workdir(tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_TEST_PRIVATE_KEY", "private-test-value")
    approvals = []
    executor = ToolExecutor(
        [ShellExecTool()],
        interactive=True,
        confirm_callback=lambda text: approvals.append(text) or True,
    )
    for turn in range(20):
        code = (
            "import json,os,sys;from pathlib import Path;"
            f"Path('build.json').write_text(json.dumps({{'turn':{turn}}}));"
            "print('private='+str(os.environ.get('SERGIO_TEST_PRIVATE_KEY')));"
            f"sys.exit({42 if turn % 3 == 0 else 0})"
        )
        result = executor.execute(
            ToolCall(
                id=str(turn),
                name="shell_exec",
                arguments=json.dumps(
                    {"command": command(code), "working_dir": str(tmp_path)}
                ),
            )
        )
        assert result.success == (turn % 3 != 0)
        assert json.loads((tmp_path / "build.json").read_text()) == {"turn": turn}
        assert "private-test-value" not in result.content
    assert len(approvals) == 20


@pytest.mark.parametrize("answer", [None, "yes", {"approved": True}, 1])
def test_truthy_confirmation_is_not_authorization(tmp_path, answer):
    marker = tmp_path / "must-not-exist"
    executor = ToolExecutor(
        [ShellExecTool()], interactive=True, confirm_callback=lambda _: answer
    )
    result = executor.execute(
        ToolCall(
            id="denied",
            name="shell_exec",
            arguments=json.dumps(
                {
                    "command": command(
                        f"from pathlib import Path;Path({str(marker)!r}).touch()"
                    )
                }
            ),
        )
    )
    assert not result.success and not marker.exists()


def test_confirmation_exception_denies_execution():
    def broken(_):
        raise RuntimeError("UI closed")

    executor = ToolExecutor(
        [ShellExecTool()], interactive=True, confirm_callback=broken
    )
    result = executor.execute(
        ToolCall(id="denied", name="shell_exec", arguments='{"command":"echo denied"}')
    )
    assert not result.success


def test_container_profile_disables_in_process_repl(monkeypatch):
    monkeypatch.setenv("SERGIO_EXECUTION_MODE", "container")
    with patch.object(ReplTool, "_exec_with_timeout") as execute:
        result = ReplTool().execute(code="print(42)")
    assert not result.success and "disabled" in result.content
    execute.assert_not_called()
    assert CodeInterpreterTool().spec.requires_confirmation


def test_container_profile_cannot_escape_through_windows_tools(monkeypatch):
    from unittest.mock import MagicMock

    from openjarvis.tools.desktop_tools import PythonRunTool, TerminalRunTool

    monkeypatch.setenv("SERGIO_EXECUTION_MODE", "container")
    http = MagicMock()
    assert not PythonRunTool(http=http).execute(code="print(42)").success
    assert not TerminalRunTool(http=http).execute(command="Get-Process").success
    http.request.assert_not_called()


def test_project_profile_cannot_write_host_files_via_another_tool(
    tmp_path, monkeypatch
):
    from openjarvis.tools.file_write import FileWriteTool

    monkeypatch.setenv("SERGIO_EXECUTION_MODE", "container")
    target = tmp_path / "host-file.txt"
    result = ToolExecutor([FileWriteTool()]).execute(
        ToolCall(
            id="blocked",
            name="file_write",
            arguments=json.dumps({"path": str(target), "content": "escape"}),
        )
    )
    assert not result.success and not target.exists()

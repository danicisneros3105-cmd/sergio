"""Terminal (PowerShell), closing apps, and choosing the cloud brain."""

import sys

import pytest
from sergio_escritorio import files

from openjarvis.cli import escritorio_cmd
from openjarvis.tools.desktop_tools import DesktopActionTool, TerminalRunTool


@pytest.fixture
def wired(control_server, monkeypatch):
    controller, url = control_server
    monkeypatch.setenv("SERGIO_DESKTOP_URL", url)
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "secreto")
    return controller


def test_terminal_tool_runs_powershell(wired, desktop):
    result = TerminalRunTool().execute(command="Get-Location", seconds=20)
    assert result.success and "C:\\Users\\dani" in result.content
    assert desktop.calls[-1] == ("shell", "Get-Location", 20.0)


def test_terminal_needs_a_command(wired):
    assert not TerminalRunTool().execute(command="").success


def test_close_app(wired, desktop):
    ok = DesktopActionTool().execute(action="close_app", target="Spotify")
    assert ok.success and "Spotify Premium" in ok.content
    missing = DesktopActionTool().execute(action="close_app", target="Photoshop")
    assert not missing.success and "No open app" in missing.content


def test_shell_command_is_utf8_powershell():
    argv = files.shell_command("dir")
    assert argv[0] == "powershell.exe" and "-NoProfile" in argv
    assert argv[-1].endswith("dir") and "UTF8" in argv[-1]


def test_run_shell_output_and_timeout(tmp_path):
    ok = files.run_shell(
        "", argv=[sys.executable, "-c", "print('hola')"], workdir=str(tmp_path)
    )
    assert ok["exit_code"] == 0 and ok["stdout"].strip() == "hola"
    slow = files.run_shell(
        "", timeout=0.5, argv=[sys.executable, "-c", "import time; time.sleep(5)"]
    )
    assert slow["exit_code"] == -1
    missing = files.run_shell("", argv=["no-such-program-xyz"])
    assert missing["exit_code"] == -1


@pytest.mark.parametrize(
    ("config", "env", "brain", "fallback"),
    [
        (
            '[intelligence]\ndefault_model = "qwen3:8b"\n',
            {"MOONSHOT_API_KEY": "k"},
            "kimi-k2.6",
            "qwen3:8b",
        ),
        (
            '[intelligence]\ndefault_model = "kimi-k2.5"\n',
            {"MOONSHOT_API_KEY": "k"},
            "kimi-k2.5",
            None,
        ),
        ("", {"GEMINI_API_KEY": "g"}, "gemini-2.5-flash", None),
        ('[intelligence]\ndefault_model = "qwen3:8b"\n', {}, "", None),
    ],
)
def test_prefer_cloud(tmp_path, config, env, brain, fallback):
    import tomllib

    cfg = tmp_path / "config.toml"
    cfg.write_text(config)
    assert escritorio_cmd.prefer_cloud(cfg, env) == brain
    intel = tomllib.loads(cfg.read_text()).get("intelligence", {})
    if brain:
        assert intel["default_model"] == brain
    if fallback:
        assert intel["fallback_model"] == fallback

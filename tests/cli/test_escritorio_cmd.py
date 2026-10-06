"""`sergio escritorio`: config changes and the Windows hand-off."""

import subprocess

from click.testing import CliRunner

from openjarvis.cli import escritorio_cmd


def test_enable_tools_adds_desktop_tools_and_turns(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[tools]\nenabled = ["think", "screen_read"]\n\n[agent]\nmax_turns = 10\n'
    )
    escritorio_cmd.enable_tools(cfg)
    text = cfg.read_text()
    assert (
        'enabled = ["think", "screen_read", "calculator", "get_weather", '
        '"globe_view", "live_flights", "flights_overhead", "live_earthquakes", "desktop_action", '
        '"camera_look", "video_edit", "blender_create", "face_approval", '
        '"face_enroll", "files_organize", "python_run", "terminal_run", '
        '"skill_guide", "web_search"]'
    ) in text
    assert "max_turns = 25" in text
    escritorio_cmd.enable_tools(cfg)  # idempotent
    assert cfg.read_text() == text


def test_enable_tools_without_a_list_turns_everything_on(tmp_path):
    # No list would leave the server defaults: no screen, no camera.
    cfg = tmp_path / "config.toml"
    cfg.write_text('[agent]\nmax_turns = 40\n[tools]\nenabled = "think,shell_exec"\n')
    escritorio_cmd.enable_tools(cfg)
    text = cfg.read_text()
    assert "max_turns = 40" in text
    for name in ("think", "shell_exec", "screen_read", "camera_look", "globe_view"):
        assert f'"{name}"' in text


def test_instalar_runs_powershell_with_token_in_env(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        out = "\\\\wsl.localhost\\Ubuntu" + cmd[-1] if cmd[0] == "wslpath" else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(
        escritorio_cmd.shutil, "which", lambda _n: "/mnt/c/powershell.exe"
    )
    monkeypatch.setattr(escritorio_cmd.subprocess, "run", fake_run)
    monkeypatch.setattr(
        "openjarvis.cli.service_cmd.env_file", lambda: tmp_path / "sergio.env"
    )
    monkeypatch.setattr("openjarvis.core.paths.get_config_dir", lambda: tmp_path)
    waited = []
    monkeypatch.setattr(
        "openjarvis.cli.service_cmd.wait_for_server",
        lambda base, **kw: waited.append(base) or True,
    )
    result = CliRunner().invoke(escritorio_cmd.escritorio, ["instalar"])
    assert result.exit_code == 0, result.output
    # after restarting the server it waits until it answers again
    assert waited and waited[0].startswith("http://127.0.0.1:")
    env_text = (tmp_path / "sergio.env").read_text()
    token = env_text.split("SERGIO_DESKTOP_TOKEN=")[1].strip()
    assert len(token) > 30
    ps = [c for c in calls if c[0][0] == "powershell.exe"][0]
    assert token not in " ".join(ps[0])  # never on the command line
    assert ps[1]["env"]["SERGIO_DESKTOP_TOKEN"] == token
    assert "SERGIO_DESKTOP_TOKEN" in ps[1]["env"]["WSLENV"]
    assert ps[0][ps[0].index("-Fuente") + 1].endswith("windows")
    assert any(c[0][:1] == ["git"] and "gc" in c[0] for c in calls)  # keeps only the latest
    # re-running keeps the same token (Windows side already has it)
    CliRunner().invoke(escritorio_cmd.escritorio, ["instalar"])
    assert (tmp_path / "sergio.env").read_text().count("SERGIO_DESKTOP_TOKEN") == 1
    assert token in (tmp_path / "sergio.env").read_text()


def test_instalar_outside_wsl_is_explained(monkeypatch):
    monkeypatch.setattr(escritorio_cmd.shutil, "which", lambda _n: None)
    result = CliRunner().invoke(escritorio_cmd.escritorio, ["instalar"])
    assert result.exit_code != 0 and "WSL" in result.output


def test_wait_for_server_until_it_answers():
    import httpx

    from openjarvis.cli.service_cmd import wait_for_server

    tries = []

    def get(url, **kw):
        tries.append(url)
        if len(tries) < 3:  # still starting: port closed
            raise httpx.ConnectError("refused")
        return httpx.Response(503)  # up (engine still warming) counts

    assert wait_for_server("http://x:1/", get=get, sleep=lambda s: None)
    assert tries == ["http://x:1/health"] * 3


def test_wait_for_server_gives_up():
    import httpx

    from openjarvis.cli.service_cmd import wait_for_server

    now = [0.0]

    def get(url, **kw):
        raise httpx.ConnectError("refused")

    def sleep(s):
        now[0] += s

    assert not wait_for_server(
        "http://x:1", timeout=10, get=get, sleep=sleep, clock=lambda: now[0]
    )
    assert 9 <= now[0] <= 11


def test_sync_server_adds_the_face_mesh_without_removing_anything(monkeypatch, tmp_path):
    import sys

    uv = tmp_path / "uv"
    uv.write_text("")
    monkeypatch.setattr(escritorio_cmd.shutil, "which", lambda _n: str(uv))
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "venv"))
    seen = []
    ok = escritorio_cmd.sync_server(
        run=lambda cmd, **kw: seen.append((cmd, kw)) or subprocess.CompletedProcess(cmd, 0)
    )
    cmd, kw = seen[0]
    assert ok and cmd[:3] == [str(uv), "sync", "--inexact"] and cmd[-2:] == ["--extra", "faces"]
    assert kw["env"]["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "venv")

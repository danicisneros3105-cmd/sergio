"""Tests for `sergio servicio` (permanent background mode)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from openjarvis.cli import service_cmd
from openjarvis.cli.extensions_cmd import watch_extensions


class FakeSystem:
    def __init__(self, fail: set[str] = frozenset()):
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        key = " ".join(cmd[:3])
        code = 1 if any(f in key for f in self.fail) else 0
        out = "active\n" if "is-active" in cmd else ""
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="boom")


@pytest.fixture
def system(tmp_path, monkeypatch):
    fake = FakeSystem()
    monkeypatch.setattr(service_cmd, "_run", fake)
    monkeypatch.setattr(service_cmd.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    root = tmp_path / "repo"
    static = root / "src" / "openjarvis" / "server" / "static"
    static.mkdir(parents=True)
    (static / "index.html").write_text("<html></html>")
    monkeypatch.setattr("openjarvis.unified.paths._REPO_ROOT", root)
    return fake


def test_units_run_server_and_extensions_with_restart():
    units = service_cmd.render_units(Path("/r"), "/bin/uv", 8000, "/bin")
    server = units["sergio.service"]
    assert "ExecStart=/bin/uv run --project /r sergio serve --host 127.0.0.1" in server
    assert "--port 8000" in server and "Restart=always" in server
    assert 'Environment="PATH=/bin"' in server
    assert "WantedBy=default.target" in server
    ext = units["sergio-extensiones.service"]
    assert "sergio extensions run" in ext and "After=sergio.service" in ext
    assert "EnvironmentFile=-" in ext


def test_units_quote_path_with_windows_spaces_and_prioritize_user_bins(
    monkeypatch, tmp_path
):
    wsl_path = "/usr/bin:/mnt/c/Program Files (x86)/NVIDIA Corporation/PhysX/Common"
    units = service_cmd.render_units(Path("/r"), "/bin/uv", 8000, wsl_path)
    assert f'Environment="PATH={wsl_path}"\n' in units["sergio.service"]
    assert f'Environment="PATH={wsl_path}"\n' in units["sergio-extensiones.service"]

    monkeypatch.setattr(service_cmd.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("PATH", wsl_path)
    computed = service_cmd._service_path().split(service_cmd.os.pathsep)
    mise_shims = str(tmp_path / ".local" / "share" / "mise" / "shims")
    win_entry = "/mnt/c/Program Files (x86)/NVIDIA Corporation/PhysX/Common"
    assert computed.index(mise_shims) < computed.index(win_entry)


def test_instalar_writes_units_enables_and_lingers(system, tmp_path):
    result = CliRunner().invoke(service_cmd.servicio, ["instalar", "--puerto", "8123"])
    assert result.exit_code == 0, result.output
    unit_dir = tmp_path / "cfg" / "systemd" / "user"
    assert "--port 8123" in (unit_dir / "sergio.service").read_text()
    assert (unit_dir / "sergio-extensiones.service").exists()
    cmds = [" ".join(c) for c in system.calls]
    assert "systemctl --user daemon-reload" in cmds
    units = "sergio.service sergio-extensiones.service"
    assert f"systemctl --user enable {units}" in cmds
    # restart, so re-running after an update loads the new code
    assert f"systemctl --user restart {units}" in cmds
    assert any(c.startswith("loginctl enable-linger") for c in cmds)
    assert "http://localhost:8123" in result.output


def test_on_off_status_and_uninstall(system, tmp_path):
    runner = CliRunner()
    assert runner.invoke(service_cmd.servicio, ["instalar"]).exit_code == 0
    assert "off" in runner.invoke(service_cmd.servicio, ["apagar"]).output
    assert "disable --now" in " ".join(system.calls[-1])
    assert "on" in runner.invoke(service_cmd.servicio, ["encender"]).output
    assert "active" in runner.invoke(service_cmd.servicio, ["estado"]).output
    assert runner.invoke(service_cmd.servicio, ["desinstalar"]).exit_code == 0
    assert not (tmp_path / "cfg" / "systemd" / "user" / "sergio.service").exists()


def test_missing_systemd_explains_wsl_setup(system):
    system.fail = {"show-environment"}
    result = CliRunner().invoke(service_cmd.servicio, ["encender"])
    assert result.exit_code != 0 and "systemd=true" in result.output


class FakeSvc:
    def __init__(self, name, problem=""):
        self.name, self.title, self.problem = name, name, problem


class FakeSup:
    def __init__(self):
        self.alive = {"clacky": False, "globe": True}
        self.started: list[str] = []

    def services(self):
        return [FakeSvc("clacky"), FakeSvc("globe"), FakeSvc("broken", "no ruby")]

    def running(self, svc):
        return self.alive.get(svc.name, False)

    def start(self, svc):
        self.started.append(svc.name)
        self.alive[svc.name] = True
        return "running"


def test_watchdog_restarts_only_dead_available_services():
    sup = FakeSup()
    ticks = iter([False, False, True])
    watch_extensions(
        sup, interval=1, should_stop=lambda: next(ticks, True), sleep=lambda s: None
    )
    assert sup.started == ["clacky"]


def test_sergio_env_is_loaded_without_overriding_real_env(tmp_path, monkeypatch):
    import os

    from openjarvis.cli import _load_sergio_env

    env = tmp_path / "sergio.env"
    env.write_text("# keys\nTWILIO_PHONE_NUMBER=+1555\nANTHROPIC_API_KEY=from-file\n")
    monkeypatch.setattr(service_cmd, "env_file", lambda: env)
    monkeypatch.delenv("TWILIO_PHONE_NUMBER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real")
    _load_sergio_env()
    assert os.environ["TWILIO_PHONE_NUMBER"] == "+1555"
    assert os.environ["ANTHROPIC_API_KEY"] == "real"
    monkeypatch.delenv("TWILIO_PHONE_NUMBER")

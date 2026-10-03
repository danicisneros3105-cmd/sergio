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
    assert "--port 8000" in server and "Restart=on-failure" in server
    assert "WantedBy=default.target" in server
    ext = units["sergio-extensiones.service"]
    assert "sergio extensions run" in ext and "After=sergio.service" in ext
    assert "EnvironmentFile=-" in ext


def test_instalar_writes_units_enables_and_lingers(system, tmp_path):
    result = CliRunner().invoke(service_cmd.servicio, ["instalar", "--puerto", "8123"])
    assert result.exit_code == 0, result.output
    unit_dir = tmp_path / "cfg" / "systemd" / "user"
    assert "--port 8123" in (unit_dir / "sergio.service").read_text()
    assert (unit_dir / "sergio-extensiones.service").exists()
    cmds = [" ".join(c) for c in system.calls]
    assert "systemctl --user daemon-reload" in cmds
    assert (
        "systemctl --user enable --now sergio.service sergio-extensiones.service"
        in cmds
    )
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

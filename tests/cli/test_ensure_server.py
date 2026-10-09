"""ensure_server: never a silent wait for Sergio's server."""

from __future__ import annotations

import subprocess

import httpx

from openjarvis.cli import service_cmd


class Sim:
    """A fake systemd + server: the server answers once `up_after` seconds pass after a start."""

    def __init__(self, state, up_after=None, fails=False):
        self.state, self.up_after, self.fails = state, up_after, fails
        self.now = 0.0
        self.started_at = None if state != "active" else 0.0
        self.calls = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.now += s

    def runner(self, cmd):
        self.calls.append(cmd[2:4] if len(cmd) > 3 else cmd)
        out = ""
        if "is-active" in cmd:
            out = self.state
        elif "show" in cmd:
            out = "not-found" if self.state == "missing" else "loaded"
        elif "restart" in cmd:
            self.state = "failed" if self.fails else "activating"
            self.started_at = self.now
        elif "journalctl" in cmd[0]:
            out = "ImportError: no module named x"
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def get(self, url, timeout):
        if (
            self.started_at is not None
            and self.up_after is not None
            and self.now - self.started_at >= self.up_after
        ):
            self.state = "active"
            return httpx.Response(200)
        raise httpx.ConnectError("refused")


def _run(sim, timeout=60):
    lines = []
    ok = service_cmd.ensure_server(
        "http://127.0.0.1:8000",
        lines.append,
        timeout=timeout,
        get=sim.get,
        runner=sim.runner,
        sleep=sim.sleep,
        clock=sim.clock,
    )
    return ok, lines


def test_a_switched_off_sergio_is_switched_on_with_progress(monkeypatch):
    monkeypatch.setattr(service_cmd.shutil, "which", lambda name: "/bin/systemctl")
    sim = Sim("inactive", up_after=12)
    ok, lines = _run(sim)
    assert ok and lines[0].startswith("Sergio estaba apagado")
    assert any("sigue arrancando" in line for line in lines) and lines[-1].startswith(
        "Sergio está encendido"
    )
    assert ["restart", "sergio.service"] in sim.calls


def test_not_installed_answers_at_once(monkeypatch):
    monkeypatch.setattr(service_cmd.shutil, "which", lambda name: "/bin/systemctl")
    sim = Sim("missing")
    ok, lines = _run(sim)
    assert not ok and "sergio servicio instalar" in lines[0] and sim.now == 0


def test_a_crash_stops_the_wait_early_and_shows_the_log(monkeypatch):
    monkeypatch.setattr(service_cmd.shutil, "which", lambda name: "/bin/systemctl")
    sim = Sim("failed", fails=True)
    ok, lines = _run(sim, timeout=120)
    assert not ok and sim.now < 10
    assert "ImportError" in lines[-1] and "servicio: failed" in lines[-2]


def test_already_running_is_instant(monkeypatch):
    sim = Sim("active", up_after=0)
    ok, lines = _run(sim)
    assert ok and lines == [] and sim.calls == []


def test_local_calls_bypass_proxies(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "corp.example")
    monkeypatch.delenv("no_proxy", raising=False)
    service_cmd.bypass_proxy_for_local()
    import os

    assert os.environ["NO_PROXY"].split(",")[:3] == [
        "corp.example",
        "127.0.0.1",
        "localhost",
    ]
    assert "127.0.0.1" in os.environ["no_proxy"]

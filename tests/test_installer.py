"""The one-click Windows installer: asks for admin once, never for typing."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_installer_asks_admin_once_and_runs_hidden():
    nsi = (ROOT / "installer" / "sergio.nsi").read_text(encoding="utf-8")
    assert "RequestExecutionLevel admin" in nsi
    assert "-WindowStyle Hidden" in nsi and "nsExec::ExecToLog" in nsi
    assert "RunOnce" in nsi  # continues by itself after a restart
    boot = (ROOT / "installer" / "bootstrap.ps1").read_text(encoding="utf-8")
    assert "Read-Host" not in boot  # nothing to type
    assert "exit 3010" in boot and "NOPASSWD" in boot
    assert (
        "sergio escritorio instalar" in boot
        and "install-todo-en-uno.sh --permanente" in boot
    )


@pytest.mark.skipif(shutil.which("makensis") is None, reason="NSIS not installed")
def test_installer_builds(tmp_path):
    out = tmp_path / "Sergio-Instalador.exe"
    done = subprocess.run(
        ["makensis", "-V2", f"-DOUTFILE={out}", "sergio.nsi"],
        cwd=ROOT / "installer",
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert out.read_bytes()[:2] == b"MZ"

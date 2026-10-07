"""Useless apps found by Sergio, removed with one approval; temp cleaned alone."""

from __future__ import annotations

import os
import time

from sergio_escritorio.apps_limpieza import (
    App,
    audit,
    clean_temp,
    describe,
    remove,
    uninstall_command,
)
from sergio_escritorio.quick import parse_quick

NOW = 1_800_000_000.0


def test_duplicates_trialware_and_unused_apps_are_found_runtimes_never():
    apps = [
        App("Zoom 5.17.1 (64-bit)", "5.17.1"), App("Zoom 6.0.2 (64-bit)", "6.0.2"),
        App("McAfee LiveSafe", "16.0"),
        App("Juego viejo", "1.0", last_used=NOW - 200 * 86400), App("Chrome", "130", last_used=NOW - 86400),
        App("Microsoft Visual C++ 2015 Redistributable (x64)", "14.0"),
        App("Microsoft Visual C++ 2022 Redistributable (x64)", "14.3"),
        App("NVIDIA Graphics Driver", "560"), App("Blender 4.2", "4.2"), App("Blender 5.0", "5.0"),
    ]
    found = {a.name: why for a, why in audit(apps, now=NOW)}
    assert "Zoom 5.17.1 (64-bit)" in found and "6.0.2" in found["Zoom 5.17.1 (64-bit)"]
    assert "Zoom 6.0.2 (64-bit)" not in found  # the newest stays
    assert "bloatware" in found["McAfee LiveSafe"] and "200 días" in found["Juego viejo"]
    assert not any(k in name for name in found for k in ("Visual C++", "NVIDIA", "Blender", "Chrome"))
    assert "Encontré 3 apps" in describe(audit(apps, now=NOW))


def test_each_app_is_removed_quietly_and_one_failure_does_not_stop_the_rest():
    msi = App("Vieja", uninstall="MsiExec.exe /I{12345678-AAAA-BBBB-CCCC-1234567890AB}")
    assert uninstall_command(msi) == "MsiExec.exe /X{12345678-AAAA-BBBB-CCCC-1234567890AB} /qn /norestart"
    assert uninstall_command(App("X", quiet='"C:\\x\\unins.exe" /S')) == '"C:\\x\\unins.exe" /S'
    assert "winget uninstall --name \"Otra\"" in uninstall_command(App("Otra"))
    ran = []

    def run(cmd, **_k):
        ran.append(cmd)
        if "Otra" in cmd:
            raise OSError("bloqueada")
        return type("R", (), {"returncode": 0})()

    assert remove([App("Otra"), msi], run=run) == [("Otra", False), ("Vieja", True)] and len(ran) == 2


def test_old_temp_files_go_new_ones_stay(tmp_path):
    old, new, folder = tmp_path / "viejo.tmp", tmp_path / "nuevo.tmp", tmp_path / "cache"
    old.write_bytes(b"x" * 1000)
    new.write_bytes(b"y" * 10)
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"z" * 500)
    week_ago = time.time() - 9 * 86400
    for path in (old, folder):
        os.utime(path, (week_ago, week_ago))
    assert clean_temp(tmp_path) == 1500
    assert new.exists() and not old.exists() and not folder.exists()


def test_voice_orders_for_apps_and_skills():
    assert parse_quick("limpia las apps inútiles").kind == "apps_clean"
    assert parse_quick("desinstala los programas que no uso").kind == "apps_clean"
    q = parse_quick("Sergio, aprende este PDF C:\\Users\\Dani\\Descargas\\SKILL_02.pdf")
    assert q.kind == "skill_learn" and q.arg.endswith("SKILL_02.pdf")
    assert parse_quick("qué skills tienes").kind == "skills_show"

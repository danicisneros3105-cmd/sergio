"""Creator's real programs on Windows: found, installed and opened."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest
from sergio_escritorio import creator_apps as ca


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    ca._state.clear()
    monkeypatch.setattr(ca, "LOG", tmp_path / "programas.log")
    monkeypatch.setattr(ca, "INCOMING", tmp_path / "Creator")
    yield
    ca._state.clear()


def installed(monkeypatch, *keys: str, bonsai: bool = False):
    paths = {k: f"C:/Apps/{k}.exe" for k in keys}

    def expand(pattern: str) -> list[str]:
        for key, prog in ca.PROGRAMS.items():
            if pattern in prog.exe and key in paths:
                return [paths[key]]
        return []

    monkeypatch.setattr(ca, "_expand", expand)
    monkeypatch.setattr(ca.os.path, "isfile", lambda p: p in paths.values())
    monkeypatch.setattr(ca, "bonsai_installed", lambda: bonsai)
    return paths


def test_every_space_has_its_programs():
    assert {
        "artcraft",
        "kdenlive",
        "freecad",
        "librecad",
        "blender",
        "bonsai",
        "vscodium",
    } <= set(ca.PROGRAMS)
    assert ca.PROGRAMS["bonsai"].needs == "blender"
    assert (
        ".ifc" in ca.PROGRAMS["freecad"].opens
        and ".dxf" in ca.PROGRAMS["librecad"].opens
    )


def test_find_and_status(monkeypatch):
    installed(monkeypatch, "freecad", "blender")
    assert ca.find("freecad") == "C:/Apps/freecad.exe"
    assert ca.find("librecad") == ""
    assert ca.find("bonsai") == ""  # Blender is there, Bonsai is not
    st = ca.status()
    assert st["freecad"]["installed"] and not st["kdenlive"]["installed"]
    assert st["freecad"]["name"] == "Planos"


def test_bonsai_counts_once_blender_has_it(monkeypatch):
    installed(monkeypatch, "blender", bonsai=True)
    assert ca.find("bonsai") == "C:/Apps/blender.exe"


def test_winget_install_falls_back_to_machine_scope(monkeypatch):
    installed(monkeypatch)
    calls = []

    def run(cmd):
        calls.append(cmd)
        return SimpleNamespace(
            returncode=1 if "--scope" in cmd else 0, stdout="", stderr=""
        )

    line = ca.install("kdenlive", run)
    assert (
        calls[0][:4] == ["winget", "install", "--id", "KDE.Kdenlive"]
        and "--scope" in calls[0]
    )
    assert "--scope" not in calls[1]
    assert "Video" in line and not ca._state["kdenlive"]


def test_failed_install_is_reported_not_raised(monkeypatch):
    installed(monkeypatch)
    line = ca.install(
        "librecad",
        lambda cmd: SimpleNamespace(returncode=1, stdout="No package found", stderr=""),
    )
    assert "no se pudo" in line and "No package found" in ca._state["librecad"]["error"]
    assert ca.status()["librecad"]["error"]


def test_github_release_installers(monkeypatch, tmp_path):
    installed(monkeypatch)
    releases = [
        {
            "draft": True,
            "assets": [
                {
                    "name": "ArtCraft_9.9.9_x64-setup.exe",
                    "browser_download_url": "draft",
                }
            ],
        },
        {
            "draft": False,
            "assets": [
                {
                    "name": "ArtCraft_0.42.0_x64_en-US.msi",
                    "browser_download_url": "msi",
                },
                {
                    "name": "ArtCraft_0.42.0_x64-setup.exe",
                    "browser_download_url": "https://x/setup.exe",
                },
            ],
        },
    ]
    assert (
        ca.latest_asset(
            "storytold/artcraft", ca.PROGRAMS["artcraft"].asset, get=lambda u: releases
        )
        == "https://x/setup.exe"
    )
    with pytest.raises(RuntimeError):
        ca.latest_asset("storytold/artcraft", r"nothing", get=lambda u: releases)
    bonsai = [
        {
            "assets": [
                {
                    "name": "bonsai_py311-0.8.4-windows-x64.zip",
                    "browser_download_url": "z",
                }
            ]
        }
    ]
    assert (
        ca.latest_asset(
            "IfcOpenShell/IfcOpenShell",
            ca.PROGRAMS["bonsai"].asset,
            get=lambda u: bonsai,
        )
        == "z"
    )
    monkeypatch.setattr(ca, "latest_asset", lambda repo, pattern: "https://x/setup.exe")
    monkeypatch.setattr(ca, "_download", lambda url: tmp_path / "setup.exe")
    ran = []
    ca.install("artcraft", lambda cmd: ran.append(cmd) or SimpleNamespace(returncode=0))
    assert ran == [[str(tmp_path / "setup.exe"), "/S"]]


def test_bonsai_tries_blender_extensions_then_the_zip(monkeypatch, tmp_path):
    installed(monkeypatch, "blender")
    monkeypatch.setattr(
        ca, "latest_asset", lambda repo, pattern: "https://x/bonsai.zip"
    )
    monkeypatch.setattr(ca, "_download", lambda url: tmp_path / "bonsai.zip")
    ran = []
    ca.install("bonsai", lambda cmd: ran.append(cmd) or SimpleNamespace(returncode=1))
    assert ran[0][1:5] == ["--online-mode", "--command", "extension", "install"]
    assert "bonsai" in ran[0]
    assert (
        "package_install_files" in ran[1][-1]
        and str(tmp_path / "bonsai.zip") in ran[1][-1]
    )


def test_files_from_sergio_open_in_the_right_program(monkeypatch, tmp_path):
    installed(monkeypatch, "freecad", "librecad", "blender", bonsai=True)
    opened = []
    monkeypatch.setattr(
        ca.subprocess, "Popen", lambda cmd, cwd=None: opened.append(cmd)
    )
    data = base64.b64encode(b"ISO-10303-21;").decode()
    out = ca.skill(
        {
            "action": "open",
            "app": "freecad",
            "name": "../../plano sergio.ifc",
            "data": data,
        }
    )
    assert "Planos" in out
    saved = ca.INCOMING / "plano sergio.ifc"
    assert saved.read_bytes() == b"ISO-10303-21;"  # no path tricks: kept in Creator
    assert opened[-1] == ["C:/Apps/freecad.exe", str(saved)]
    ca.open_program("bonsai", str(saved))
    assert "bim.load_project" in opened[-1][-1]
    with pytest.raises(ValueError):
        ca.open_command("librecad", str(saved))  # LibreCAD does not read IFC
    with pytest.raises(LookupError):
        ca.open_command("kdenlive")
    with pytest.raises(LookupError):
        ca.skill({"action": "open", "app": "photoshop"})


def test_skill_install_runs_in_the_background(monkeypatch):
    started = []
    monkeypatch.setattr(
        ca.threading,
        "Thread",
        lambda target, args, daemon: SimpleNamespace(
            start=lambda: started.append(args)
        ),
    )
    assert "Instalando Planos" in ca.skill({"action": "install", "app": "freecad"})
    assert ca.status()["freecad"]["installing"]
    assert "ya se está instalando" in ca.skill({"action": "install", "app": "freecad"})
    assert started == [("freecad",)]

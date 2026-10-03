"""Organising folders and running Python on Windows."""

import pytest
from sergio_escritorio import files

from openjarvis.tools.desktop_tools import FilesOrganizeTool, PythonRunTool


@pytest.fixture
def wired(control_server, monkeypatch):
    controller, url = control_server
    monkeypatch.setenv("SERGIO_DESKTOP_URL", url)
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "secreto")
    return controller


@pytest.fixture
def downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "UNDO_DIR", tmp_path / "undo")
    folder = tmp_path / "Downloads"
    folder.mkdir()
    for name in ("foto.JPG", "notas.pdf", "setup.exe", "raro.xyz", "cancion.mp3"):
        (folder / name).write_text(name)
    (folder / "Imágenes").mkdir()
    (folder / "Imágenes" / "foto.JPG").write_text("older photo")  # name clash
    return folder


def test_preview_moves_nothing(downloads, tmp_path):
    plan = files.organize("downloads", home=tmp_path)
    assert plan["applied"] is False and plan["files"] == 5
    assert plan["groups"] == {
        "Imágenes": 1,
        "Documentos": 1,
        "Instaladores": 1,
        "Otros": 1,
        "Música": 1,
    }
    assert (downloads / "foto.JPG").exists()


def test_apply_never_overwrites_and_undo_restores(downloads, tmp_path):
    plan = files.organize(str(downloads), apply=True)
    assert plan["applied"] and (downloads / "Documentos" / "notas.pdf").exists()
    assert (downloads / "Imágenes" / "foto.JPG").read_text() == "older photo"
    assert (downloads / "Imágenes" / "foto (2).JPG").read_text() == "foto.JPG"
    assert files.undo() == 5
    assert sorted(p.name for p in downloads.iterdir() if p.is_file()) == [
        "cancion.mp3",
        "foto.JPG",
        "notas.pdf",
        "raro.xyz",
        "setup.exe",
    ]
    assert not (downloads / "Documentos").exists()  # emptied folders go away
    assert (downloads / "Imágenes" / "foto.JPG").read_text() == "older photo"
    with pytest.raises(ValueError):
        files.undo()


def test_by_month(downloads):
    plan = files.organize(str(downloads), by="month")
    assert all(len(k) == 7 and k[4] == "-" for k in plan["groups"])


def test_run_python_captures_output_and_errors(tmp_path):
    ok = files.run_python("print(6 * 7)", workdir=str(tmp_path))
    assert ok["exit_code"] == 0 and ok["stdout"].strip() == "42"
    bad = files.run_python("raise SystemExit('fallo')", workdir=str(tmp_path))
    assert bad["exit_code"] == 1 and "fallo" in bad["stderr"]
    slow = files.run_python(
        "import time; time.sleep(5)", timeout=0.5, workdir=str(tmp_path)
    )
    assert slow["exit_code"] == -1


def test_organize_tool_previews_then_applies(wired, desktop):
    preview = FilesOrganizeTool().execute(target="Descargas")
    assert (
        preview.success
        and "preview" in preview.content
        and "Imágenes: 2" in preview.content
    )
    assert desktop.calls[-1] == ("organize", "Descargas", "type", False)
    done = FilesOrganizeTool().execute(target="Descargas", apply=True, by="month")
    assert done.success and done.content.startswith("moved 3")
    assert desktop.calls[-1] == ("organize", "Descargas", "month", True)
    assert "put back 3" in FilesOrganizeTool().execute(undo=True).content


def test_python_tool(wired, desktop):
    result = PythonRunTool().execute(code="print(6*7)", seconds=30)
    assert result.success and "42" in result.content
    assert desktop.calls[-1] == ("python", "print(6*7)", 30.0)


def test_python_tool_needs_code(wired):
    assert not PythonRunTool().execute(code=" ").success

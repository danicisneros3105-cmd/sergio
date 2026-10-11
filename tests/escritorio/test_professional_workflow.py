"""A developer's report workflow through authenticated desktop tools."""

import json

from sergio_escritorio import files

from openjarvis.tools.desktop_tools import FilesOrganizeTool, PythonRunTool


def test_generate_report_preview_organize_and_undo(
    control_server, desktop, tmp_path, monkeypatch
):
    controller, url = control_server
    monkeypatch.setenv("SERGIO_DESKTOP_URL", url)
    monkeypatch.setenv("SERGIO_DESKTOP_TOKEN", "secreto")
    monkeypatch.setattr(files, "UNDO_DIR", tmp_path / "undo")
    work = tmp_path / "project-reports"
    work.mkdir()
    desktop.python = lambda code, seconds: files.run_python(
        code, timeout=seconds, workdir=str(work)
    )
    desktop.organize = lambda folder, by, apply: files.organize(folder, by, apply)
    desktop.undo_organize = lambda: files.undo()
    approvals = []
    controller.approve = lambda payload: approvals.append(json.loads(payload)) or True
    code = (
        "from pathlib import Path\n"
        "Path('latency.csv').write_text('route,ms\\napi,120\\n', encoding='utf-8')\n"
        "print('report generated')\n"
    )
    result = PythonRunTool().execute(code=code, seconds=10)
    assert result.success and "report generated" in result.content
    assert approvals[-1]["code"] == code
    original = (work / "latency.csv").read_bytes()
    count = len(approvals)
    assert FilesOrganizeTool().execute(target=str(work)).success
    assert len(approvals) == count  # The preview has no effects to approve.
    assert (work / "latency.csv").exists()
    assert FilesOrganizeTool().execute(target=str(work), apply=True).success
    assert approvals[-1]["apply"] is True
    assert (work / "Hojas de cálculo" / "latency.csv").read_bytes() == original
    assert FilesOrganizeTool().execute(undo=True).success
    assert (work / "latency.csv").read_bytes() == original

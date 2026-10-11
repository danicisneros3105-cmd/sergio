"""Bulk documents, race collisions and interrupted exclusive moves."""

from pathlib import Path

import pytest
from sergio_escritorio import files


def test_bulk_plan_written_once_and_every_byte_restored(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "UNDO_DIR", tmp_path / "undo")
    root = tmp_path / "reports"
    root.mkdir()
    originals = {
        f"report-{n}.csv": bytes(range(256)) + str(n).encode() for n in range(100)
    }
    for name, data in originals.items():
        (root / name).write_bytes(data)
    written = []
    save = files._save_moves
    monkeypatch.setattr(
        files,
        "_save_moves",
        lambda path, moves: written.append(len(moves)) or save(path, moves),
    )
    plan = files.organize(str(root), apply=True)
    assert written == [100]
    assert files.undo(plan["undo"]) == 100
    assert {path.name: path.read_bytes() for path in root.iterdir()} == originals


def test_destination_created_during_move_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "UNDO_DIR", tmp_path / "undo")
    root = tmp_path / "reports"
    root.mkdir()
    original = root / "plan.md"
    original.write_text("original")
    move = files._move_exclusive

    def race(source, destination):
        destination.write_text("new work")
        return move(source, destination)

    monkeypatch.setattr(files, "_move_exclusive", race)
    with pytest.raises(FileExistsError):
        files.organize(str(root), apply=True)
    assert original.read_text() == "original"
    assert (root / "Documentos/plan.md").read_text() == "new work"


def test_crash_between_link_and_unlink_is_reconciled(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "UNDO_DIR", tmp_path / "undo")
    root = tmp_path / "reports"
    root.mkdir()
    (root / "plan.md").write_text("original")
    unlink = Path.unlink

    def fail_original(path, *args, **kwargs):
        if path == root / "plan.md":
            raise OSError("power loss")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_original)
    with pytest.raises(OSError, match="power loss"):
        files.organize(str(root), apply=True)
    monkeypatch.setattr(Path, "unlink", unlink)
    assert files.undo() == 1
    assert (root / "plan.md").read_text() == "original"
    assert not (root / "Documentos/plan.md").exists()

"""Recovery scenarios used during everyday document work."""

import json
from pathlib import Path

import pytest
from sergio_escritorio import files, secure
from sergio_escritorio.perfil import Profile


def test_profile_migrates_legacy_json_and_uses_encryption(tmp_path, monkeypatch):
    path = tmp_path / "perfil.json"
    path.write_text(json.dumps({"hechos": ["dato privado"]}))
    profile = Profile(path)
    monkeypatch.setattr(secure, "available", lambda: True)
    monkeypatch.setattr(
        secure, "_dpapi", lambda data, protect: bytes(b ^ 42 for b in data)
    )
    profile.save()
    assert path.read_bytes().startswith(secure.MAGIC)
    assert b"dato privado" not in path.read_bytes()
    assert Profile(path).facts == ["dato privado"]


def test_organize_same_second_preserves_both_undo_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "UNDO_DIR", tmp_path / "undo")
    monkeypatch.setattr(files.time, "strftime", lambda _: "20261010-120000")
    plans = []
    for name in ("a", "b"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "note.txt").write_text(name)
        plans.append(files.organize(str(folder), apply=True))
    assert plans[0]["undo"] != plans[1]["undo"]
    for plan in plans:
        assert files.undo(plan["undo"]) == 1


def test_partial_move_failure_is_recoverable(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "UNDO_DIR", tmp_path / "undo")
    folder = tmp_path / "docs"
    folder.mkdir()
    for name in ("a.txt", "b.txt"):
        (folder / name).write_text(name)
    move = files._move_exclusive

    def fail_second(self, target):
        if self == folder / "b.txt":
            raise OSError("disk failure")
        return move(self, target)

    monkeypatch.setattr(files, "_move_exclusive", fail_second)
    with pytest.raises(OSError, match="disk failure"):
        files.organize(str(folder), apply=True)
    assert files.undo() == 1
    assert (folder / "a.txt").read_text() == "a.txt"
    assert (folder / "b.txt").read_text() == "b.txt"


def test_undo_conflict_can_be_retried_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "UNDO_DIR", tmp_path / "undo")
    folder = tmp_path / "docs"
    folder.mkdir()
    original = folder / "note.txt"
    original.write_text("original")
    plan = files.organize(str(folder), apply=True)
    original.write_text("new work")
    assert files.undo(plan["undo"]) == 0
    assert original.read_text() == "new work"
    assert Path(plan["undo"]).exists()
    original.unlink()
    assert files.undo(plan["undo"]) == 1
    assert original.read_text() == "original"

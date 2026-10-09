"""Incremental backups and two-device sync, end to end on folder targets."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

from openjarvis.backup import sync as S
from openjarvis.backup.age import AgeError
from openjarvis.backup.archive import create, list_backups, plan, prune, restore, verify
from openjarvis.backup.targets import open_target

pytest.importorskip("cryptography")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / "skills").mkdir(parents=True)
    (h / "logs").mkdir()
    (h / "config.toml").write_text("[x]\na = 1\n")
    (h / "skills" / "uno.md").write_text("uno")
    (h / "logs" / "server.log").write_text("ruido")
    (h / "sergio.env").write_text("GEMINI_API_KEY=x")
    db = sqlite3.connect(h / "memory.db")
    db.execute("create table t(x)")
    db.execute("insert into t values (1)")
    db.commit()
    db.close()
    monkeypatch.setenv("OPENJARVIS_HOME", str(h))
    return h


def _files(root: Path):
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    )


def test_full_then_incremental_and_point_in_time_restore(home, tmp_path):
    target = open_target(str(tmp_path / "dest"))
    first = create(target, "frase de paso")
    assert first.kind == "full" and first.files == 4  # the log is left out
    time.sleep(0.01)
    (home / "skills" / "dos.md").write_text("dos")
    (home / "skills" / "uno.md").unlink()
    second = create(target, "frase de paso")
    assert (second.kind, second.files, second.deleted, second.parent) == (
        "inc",
        1,
        1,
        first.id,
    )
    assert [b.kind for b in list_backups(target)] == ["full", "inc"]
    restore(target, "frase de paso", tmp_path / "now")
    assert _files(tmp_path / "now") == [
        "config.toml",
        "memory.db",
        "sergio.env",
        "skills/dos.md",
    ]
    restore(target, "frase de paso", tmp_path / "then", backup_id=first.id)
    assert "skills/uno.md" in _files(tmp_path / "then")
    con = sqlite3.connect(tmp_path / "now" / "memory.db")
    assert con.execute("select x from t").fetchall() == [(1,)]
    assert verify(target, "frase de paso")["files"] == 4
    with pytest.raises(AgeError, match="incorrecta"):
        verify(target, "otra frase")
    nothing = create(target, "frase de paso")
    assert nothing.kind == "inc" and nothing.files == 0


def test_backups_are_opaque_and_optionally_keyless(home, tmp_path):
    target = open_target(str(tmp_path / "dest"))
    info = create(target, "frase de paso", with_secrets=False)
    blob = (tmp_path / "dest" / info.name).read_bytes()
    assert b"GEMINI_API_KEY" not in blob and b"config.toml" not in blob
    restore(target, "frase de paso", tmp_path / "out")
    assert "sergio.env" not in _files(tmp_path / "out")
    # Changing the secrets choice starts a new full chain.
    assert plan(home, target.describe(), with_secrets=True).kind == "full"


def test_full_every_eighth_and_pruning(home, tmp_path):
    target = open_target(str(tmp_path / "dest"))
    kinds = []
    for i in range(10):
        (home / "skills" / "uno.md").write_text(f"v{i}")
        kinds.append(create(target, "frase de paso").kind)
    assert kinds == ["full"] + ["inc"] * 7 + ["full", "inc"]
    gone = prune(target, keep_full=1)
    assert len(gone) == 8 and [b.kind for b in list_backups(target)] == ["full", "inc"]
    restore(target, "frase de paso", tmp_path / "out")
    assert (tmp_path / "out" / "skills" / "uno.md").read_text() == "v9"


def test_tampered_backup_is_refused(home, tmp_path):
    target = open_target(str(tmp_path / "dest"))
    info = create(target, "frase de paso")
    path = tmp_path / "dest" / info.name
    data = bytearray(path.read_bytes())
    data[-3] ^= 1
    path.write_bytes(bytes(data))
    with pytest.raises(AgeError):
        restore(target, "frase de paso", tmp_path / "out")


# -- sync -----------------------------------------------------------------------


def _device(tmp_path, monkeypatch, name):
    h = tmp_path / name
    h.mkdir(exist_ok=True)
    monkeypatch.setenv("OPENJARVIS_HOME", str(h))
    return h


def _memories(db: Path):
    return sorted(
        json.loads(line)["content"] for line in S.memory_export(db).splitlines()
    )


def test_two_devices_converge(tmp_path, monkeypatch):
    from openjarvis.tools.storage.sqlite import SQLiteMemory

    target = open_target(str(tmp_path / "cloud"))
    a = _device(tmp_path, monkeypatch, "a")
    (a / "USER.md").write_text("Prefiere respuestas cortas")
    (a / "memory_facts.jsonl").write_text('{"f": 1}\n')
    (a / "sergio.env").write_text("KEY=1")
    (a / "faces").mkdir()
    (a / "faces" / "book.json").write_text("{}")
    SQLiteMemory(db_path=str(a / "memory.db")).store("A sabe X", source="a")
    key_a = S.unlock(target, "frase de paso", create=True)
    assert len(S.sync(target, key_a).uploaded) == 3

    b = _device(tmp_path, monkeypatch, "b")
    (b / "memory_facts.jsonl").write_text('{"f": 2}\n')
    SQLiteMemory(db_path=str(b / "memory.db")).store("B sabe Y", source="b")
    with pytest.raises(S.SyncError):
        S.unlock(target, "frase equivocada")
    key_b = S.unlock(target, "frase de paso")
    assert key_b == key_a
    report = S.sync(target, key_b)
    assert report.memory_added == 1 and "memory_facts.jsonl" in report.merged
    assert (b / "USER.md").read_text() == "Prefiere respuestas cortas"
    assert not (b / "sergio.env").exists() and not (b / "faces").exists()

    _device(tmp_path, monkeypatch, "a")
    S.sync(target, key_a)
    assert (
        _memories(a / "memory.db")
        == _memories(b / "memory.db")
        == ["A sabe X", "B sabe Y"]
    )
    assert (a / "memory_facts.jsonl").read_text() == (
        b / "memory_facts.jsonl"
    ).read_text()
    _device(tmp_path, monkeypatch, "b")
    assert S.sync(target, key_b).summary() == "todo estaba al día"

    # Names and contents on the storage are opaque.
    stored = b"".join(
        p.read_bytes() for p in (tmp_path / "cloud").rglob("*") if p.is_file()
    )
    assert b"Prefiere" not in stored and b"USER.md" not in stored


def test_conflict_keeps_both_versions_newest_wins(tmp_path, monkeypatch):
    target = open_target(str(tmp_path / "cloud"))
    a = _device(tmp_path, monkeypatch, "a")
    (a / "USER.md").write_text("v1")
    key = S.unlock(target, "frase de paso", create=True)
    S.sync(target, key)
    b = _device(tmp_path, monkeypatch, "b")
    S.sync(target, key)
    _device(tmp_path, monkeypatch, "a")
    (a / "USER.md").write_text("de A")
    os.utime(a / "USER.md", (time.time() - 60, time.time() - 60))
    S.sync(target, key)
    _device(tmp_path, monkeypatch, "b")
    (b / "USER.md").write_text("de B, más nuevo")
    report = S.sync(target, key)
    assert report.conflicts == ["USER.md"]
    assert (b / "USER.md").read_text() == "de B, más nuevo"
    kept = [p for p in b.iterdir() if ".conflicto-" in p.name]
    assert len(kept) == 1 and kept[0].read_text() == "de A"
    _device(tmp_path, monkeypatch, "a")
    S.sync(target, key)
    assert (a / "USER.md").read_text() == "de B, más nuevo"


def test_deletions_propagate_but_a_lost_manifest_never_deletes(tmp_path, monkeypatch):
    target = open_target(str(tmp_path / "cloud"))
    a = _device(tmp_path, monkeypatch, "a")
    (a / "USER.md").write_text("x")
    (a / "SOUL.md").write_text("y")
    key = S.unlock(target, "frase de paso", create=True)
    S.sync(target, key)
    b = _device(tmp_path, monkeypatch, "b")
    S.sync(target, key)
    (b / "SOUL.md").unlink()
    S.sync(target, key)
    _device(tmp_path, monkeypatch, "a")
    S.sync(target, key)
    assert not (a / "SOUL.md").exists() and (a / "USER.md").exists()
    target.delete(S.MANIFEST_OBJECT)
    S.sync(target, key)
    assert (a / "USER.md").read_text() == "x"  # re-uploaded, not deleted


def test_periodic_sync_only_when_set_up(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS

    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path / "h"))
    off = NS(sync=NS(interval_minutes=0, target="x", with_secrets=False))
    assert S.start_periodic(off) is None
    locked = NS(
        sync=NS(interval_minutes=5, target=str(tmp_path / "c"), with_secrets=False)
    )
    assert S.start_periodic(locked) is None  # this device never unlocked
    S.unlock(open_target(str(tmp_path / "c")), "frase de paso", create=True)
    stop = S.start_periodic(locked)
    assert stop is not None
    stop.set()

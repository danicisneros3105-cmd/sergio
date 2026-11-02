"""The vault: what is sensitive is sealed on disk and opens only with its key."""

from __future__ import annotations

import json
import sqlite3

import pytest

from openjarvis.health.store import HealthStore
from openjarvis.pagos import cifrado
from openjarvis.security import boveda


def _raw(path, sql):
    db = sqlite3.connect(path)
    try:
        return db.execute(sql).fetchall()
    finally:
        db.close()


def test_a_sealed_value_opens_only_where_it_belongs(tmp_path):
    token = boveda.seal_text(
        "me siento mal", "notes:2026-11-02:text", "salud", tmp_path
    )
    assert boveda.is_sealed(token) and "me siento mal" not in token
    assert (
        boveda.open_text(token, "notes:2026-11-02:text", "salud", tmp_path)
        == "me siento mal"
    )
    with pytest.raises(cifrado.SealError):  # moved to another row
        boveda.open_text(token, "notes:2026-11-03:text", "salud", tmp_path)
    with pytest.raises(cifrado.SealError):  # another purpose, another key
        boveda.open_text(token, "notes:2026-11-02:text", "memoria", tmp_path)
    assert token != boveda.seal_text(
        "me siento mal", "notes:2026-11-02:text", "salud", tmp_path
    )  # fresh nonce


def test_health_notes_and_surveys_are_not_readable_on_disk(tmp_path):
    store = HealthStore(tmp_path / "health" / "salud.db")
    store.set_note("2026-11-02", "dormí fatal y estoy ansioso", ["ansiedad"])
    sid = store.add_survey("corta", {"phq2_1": 3}, {"phq2": 5}, 0.0)
    store.set_reading(sid, "Lectura muy privada", "codigo")
    dump = json.dumps(
        _raw(store.path, "SELECT text, tags FROM notes")
        + _raw(store.path, "SELECT answers, scores, reading FROM surveys")
    )
    for secret in ("ansioso", "ansiedad", "phq2_1", "muy privada"):
        assert secret not in dump
    # and the app still reads everything back
    assert store.notes()["2026-11-02"] == {
        "text": "dormí fatal y estoy ansioso",
        "tags": ["ansiedad"],
    }
    got = store.survey(sid)
    assert got["answers"] == {"phq2_1": 3} and got["scores"] == {"phq2": 5}
    assert got["reading"] == "Lectura muy privada"


def test_old_plain_rows_are_sealed_when_the_store_opens(tmp_path):
    path = tmp_path / "health" / "salud.db"
    HealthStore(path)
    db = sqlite3.connect(path)
    db.execute("INSERT INTO notes VALUES ('2026-10-01', 'nota vieja', '[]')")
    db.commit()
    db.close()
    assert _raw(path, "SELECT text FROM notes")[0][0] == "nota vieja"
    again = HealthStore(path)  # a restart after updating
    assert "nota vieja" not in json.dumps(_raw(path, "SELECT text FROM notes"))
    assert again.notes()["2026-10-01"]["text"] == "nota vieja"


def test_numbers_stay_readable_for_the_database_to_add_up(tmp_path):
    store = HealthStore(tmp_path / "health" / "salud.db")
    store.add("steps", 1234.0)
    assert (
        _raw(store.path, "SELECT value FROM samples")[0][0] == 1234.0
    )  # not sealed, by design


def test_conversation_memory_is_sealed(tmp_path):
    from openjarvis.connectome.brain import Brain

    brain = Brain(tmp_path)
    brain.engrams["e1"] = {"text": "mi cuenta del banco termina en 4421", "at": 1}
    brain._dirty_eng.add("e1")
    brain._save()
    raw = json.dumps(_raw(tmp_path / "cerebro.db", "SELECT data FROM engrams"))
    assert "banco" not in raw and "4421" not in raw
    again = Brain(tmp_path)
    assert again.engrams["e1"]["text"] == "mi cuenta del banco termina en 4421"


def test_sealing_can_be_off_for_a_test_but_not_in_the_public_edition(monkeypatch):
    monkeypatch.setenv("SERGIO_CIFRAR", "0")
    assert not boveda.enabled()
    monkeypatch.setenv("SERGIO_EDICION", "publica")
    assert boveda.enabled()

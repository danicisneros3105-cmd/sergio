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


def test_medicines_and_goals_are_sealed_on_disk(tmp_path):
    from openjarvis.reminders.store import ReminderStore

    store = ReminderStore(tmp_path / "recordatorios.db")
    item = store.add(
        "medicina",
        "Metformina 500 mg",
        detail="con la cena",
        times=["20:00"],
        extra={"dosis": "1"},
    )
    dump = json.dumps(_raw(store.path, "SELECT title, detail, extra FROM items"))
    for secret in ("Metformina", "cena", "dosis"):
        assert secret not in dump
    got = store.get(item["id"])
    assert (
        got["title"] == "Metformina 500 mg"
        and got["detail"] == "con la cena"
        and got["extra"] == {"dosis": "1"}
    )
    store.update(item["id"], title="Metformina 850 mg")
    assert "850" not in json.dumps(_raw(store.path, "SELECT title FROM items"))
    assert store.items("medicina")[0]["title"] == "Metformina 850 mg"
    # an old plain row is sealed the next time it opens
    db = sqlite3.connect(store.path)
    db.execute("UPDATE items SET title='Insulina', detail='' WHERE id=?", (item["id"],))
    db.commit()
    db.close()
    again = ReminderStore(store.path)
    assert "Insulina" not in json.dumps(_raw(store.path, "SELECT title FROM items"))
    assert again.get(item["id"])["title"] == "Insulina"


def test_node_memory_messages_and_secrets_are_sealed_on_disk(tmp_path):
    from openjarvis.nodes.store import NodeStore

    store = NodeStore(tmp_path)
    store.ensure_team()
    node = store.all()[0]
    nid = node.id
    store.set_memory(nid, "El señor tiene cita con el cardiólogo el martes")
    store.say(nid, "user", "mi clave del wifi es patata-azul-77")
    store.log(nid, "nota", "reunión sobre el divorcio")
    store.add_connection(
        nid,
        "api",
        {"name": "mi-api", "base_url": "https://x.test"},
        secret="sk-secreto-12345",
    )
    disk = "".join(
        p.read_text()
        for p in (tmp_path / nid).glob("*")
        if p.is_file() and p.name != "node.json"
    )
    for secret in ("cardiólogo", "patata-azul", "divorcio", "sk-secreto"):
        assert secret not in disk, secret
    assert "cardiólogo" in store.memory(nid)
    assert any("patata-azul-77" in m["text"] for m in store.messages(nid))
    assert any("divorcio" in a["text"] for a in store.activity(nid))
    conn = store.get(nid).connections["api"][0]
    assert store.secret(nid, conn["id"]) == "sk-secreto-12345"
    # an old plain memory still reads, and is sealed the next time it is written
    (tmp_path / nid / "memory.md").write_text("recuerdo viejo")
    assert store.memory(nid) == "recuerdo viejo"
    store.set_memory(nid, store.memory(nid) + " y nuevo")
    assert "viejo" not in (tmp_path / nid / "memory.md").read_text()

"""The week in real numbers: only what was counted, nothing when nothing."""

from __future__ import annotations

from datetime import date

from openjarvis import quota, semana


def test_week_counts_only_the_last_seven_days(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    with quota._db() as db:
        db.executemany("INSERT INTO use (day, kind, n) VALUES (?, ?, ?)", [
            ("2026-11-02", "mensajes", 30), ("2026-10-30", "mensajes", 12), ("2026-10-30", "cowork", 1),
            ("2026-10-01", "mensajes", 99), ("2026-11-02|cliente", "mensajes", 50)])  # fmt: skip
    monkeypatch.setattr(
        semana,
        "videos",
        lambda since: {
            "hechos": 2,
            "en_curso": {"titulo": "Metas", "etapa": "voz", "avance": 0.4},
        },
    )
    res = semana.resumen(today=date(2026, 11, 2))
    assert res["semana"] == [
        "42 respuestas",
        "1 tarea de Cowork",
        "2 videos terminados",
    ]
    assert res["seguir"]["titulo"] == "Metas"


def test_nothing_counted_nothing_shown(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    monkeypatch.setattr(semana, "videos", lambda since: {"hechos": 0, "en_curso": None})
    assert semana.resumen() == {"semana": [], "seguir": None, "numeros": {"videos": 0}}

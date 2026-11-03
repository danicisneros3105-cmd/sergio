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
    out = semana.resumen()
    assert (
        out["semana"] == []
        and out["seguir"] is None
        and out["numeros"] == {"videos": 0}
    )
    assert (
        out["racha"]["seguidos"] == 0
    )  # the streak is part of the answer (profile only)


def test_the_streak_counts_days_in_a_row_without_ever_shaming():
    from datetime import date

    from openjarvis import semana

    d = lambda n: date(2026, 11, n)  # noqa: E731
    run = semana.racha([d(1), d(2), d(3), d(5), d(6)], today=d(6))
    assert run == {"seguidos": 2, "mejor": 3, "este_mes": 5, "total": 5}
    # today is not over yet: yesterday's run stays alive
    assert semana.racha([d(4), d(5)], today=d(6))["seguidos"] == 2
    # a break is just a smaller number, never a message
    broken = semana.racha([d(1), d(2)], today=d(6))
    assert broken["seguidos"] == 0 and broken["mejor"] == 2
    assert set(broken) == {
        "seguidos",
        "mejor",
        "este_mes",
        "total",
    }  # no «perdiste», no countdown
    assert semana.racha([], today=d(6)) == {
        "seguidos": 0,
        "mejor": 0,
        "este_mes": 0,
        "total": 0,
    }

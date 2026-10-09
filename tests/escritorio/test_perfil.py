"""Your profile: usage schedule, key updates 2.5+ times a week, applying it."""

from __future__ import annotations

from datetime import datetime

from sergio_escritorio import brain
from sergio_escritorio.perfil import UPDATE_DAYS, Profile, Usage, slot_of

MONDAY = datetime(2026, 10, 5)


def _at(day: int, hour: int, minute: int = 0) -> float:
    return MONDAY.replace(day=5 + day, hour=hour, minute=minute).timestamp()


def test_usage_learns_your_free_hours():
    usage = Usage()
    for day in range(5):  # weekdays 19:00-21:00
        for minute in range(0, 120, 5):
            usage.record(_at(day, 19) + minute * 60)
    usage.record(_at(6, 10))  # one Sunday minute: noise
    windows = usage.free_windows()
    assert windows[:1] and all("19:00-21:00" in w for w in windows[:5])
    assert not any("domingo" in w for w in windows)
    assert usage.busy_level(datetime.fromtimestamp(_at(2, 20))) > 0.5
    nxt = datetime.fromtimestamp(usage.next_good_time(_at(1, 9), minutes=30))
    assert (nxt.weekday(), nxt.hour) == (1, 19)  # Tuesday evening


def test_old_weeks_fade():
    usage = Usage()
    usage.record(_at(0, 8))
    before = usage.grid[slot_of(datetime.fromtimestamp(_at(0, 8)))]
    usage.record(_at(0, 8) + 60 * 86400)
    assert usage.grid[slot_of(datetime.fromtimestamp(_at(0, 8)))] < before * 0.5


def test_key_update_at_least_two_and_a_half_times_a_week(tmp_path):
    clock = [_at(0, 10)]
    prof = Profile(tmp_path / "p.json", clock=lambda: clock[0])
    assert prof.due()
    calls = []

    def think(context, previous):
        calls.append((context, previous))
        return {"resumen": f"v{len(calls)}", "comunicacion": {"detalle": "breve", "humor": "mucho"},
                "gimnasio": {"prioridad": ["Atención"], "preferidos": ["matrices"], "dificultad": 3}}  # fmt: skip

    updates = 0
    for _hour in range(7 * 24):  # a week, checked every hour
        if prof.due():
            prof.update(think)
            updates += 1
        clock[0] += 3600
    assert updates >= 2.5 and 7 / UPDATE_DAYS >= 2.5
    assert calls[1][1]["resumen"] == "v1"  # each update builds on the last
    prof.remember("estudio medicina")
    again = Profile(tmp_path / "p.json", clock=lambda: clock[0])
    assert (
        again.data["resumen"] == f"v{updates}"
        and "estudio medicina" in again.context()["lo_que_me_contó"]
    )
    line = again.voice_line()
    assert "briefly" in line and "humour" in line and f"v{updates}" in line
    assert again.gym_prefs() == {
        "prioridad": ["atención"],
        "preferidos": ["matrices"],
        "dificultad": 1,
    }


def test_the_gym_varies_and_follows_the_profile():
    history = [
        {"kind": "matrices", "accuracy": 0.8, "time": 1},
        {"kind": "nback", "accuracy": 0.8, "time": 2},
    ]
    for index in range(len(brain.SCHEDULE)):
        ex, _ = brain.personal_next(index, history)
        assert ex.kind not in ("matrices", "nback") or ex.kind in ("pausa", "repaso")

    def normal(start, step):
        return next(
            i
            for i in range(start, 300, step)
            if brain.next_exercise(i)[0].kind
            not in ("pausa", "repaso", "matrices", "nback")
        )

    ex, _ = brain.personal_next(normal(2, 3), history, {"prioridad": ["atención"]})
    assert brain.SKILLS.get(ex.kind) == "atención"
    i = next(
        i
        for i in range(4, 300, 5)
        if i % 3 != 2
        and brain.next_exercise(i)[0].kind
        not in ("pausa", "repaso", "matrices", "nback")
    )
    ex, _ = brain.personal_next(i, history, {"preferidos": ["rotacion"]})
    assert ex.kind == "rotacion"


def test_profile_orders():
    from sergio_escritorio.quick import parse_quick

    assert parse_quick("¿qué sabes de mí?").kind == "profile_show"
    assert parse_quick("actualiza mi perfil").kind == "profile_update"
    q = parse_quick("recuerda que soy zurdo")
    assert (q.kind, q.arg) == ("profile_fact", "soy zurdo")
    assert parse_quick("recuérdame en 10 minutos sacar la ropa").kind == "reminder"

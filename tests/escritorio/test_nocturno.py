"""Night Shift: the evening's light, bedtime math, the diary, the orders."""

from __future__ import annotations

import datetime as dt

from sergio_escritorio import nocturno as n
from sergio_escritorio.quick import parse_quick

DAY = dt.date(2026, 10, 7)  # a Wednesday


def at(h, m=0, day=DAY):
    return dt.datetime.combine(day, dt.time(h, m))


def test_the_evening_warms_then_dims_and_sergio_goes_quiet():
    s = n.Settings(wake="07:00", need_h=8)
    assert n.bedtime(s) == dt.time(22, 45)  # 7:00 - 8 h - 15 min to fall asleep
    dusk = dt.time(18, 10)
    phases = [n.moment(at(h, m), s, dusk) for h, m in ((14, 0), (19, 0), (21, 50), (22, 40), (23, 30), (3, 0), (7, 30))]
    assert [p.phase for p in phases] == ["dia", "atardecer", "relajacion", "relajacion", "dormir", "dormir", "manana"]
    assert phases[1].kelvin < 6500 and phases[1].brightness == 1.0 and not phases[1].quiet  # warmer, not darker
    assert phases[3].kelvin < phases[2].kelvin and phases[3].brightness < 0.8 and phases[3].quiet  # darker before bed
    assert n.moment(at(23, 30), n.Settings(on=False)).phase == "dia"


def test_a_late_sleeper_after_midnight():
    s = n.Settings(wake="09:00", need_h=8)  # bed at 00:45
    assert n.moment(at(23, 0), s).phase == "atardecer"
    assert n.moment(at(0, 30), s).phase == "relajacion"
    assert n.moment(at(1, 0), s).phase == "dormir"


def test_screen_colour_ramp_and_sunset():
    r, g, b = n.kelvin_rgb(2700)
    assert r == 1.0 and 0.55 < g < 0.75 and b < 0.45  # amber: blue cut the most
    assert all(x > 0.95 for x in n.kelvin_rgb(6500))
    ramp = n.gamma_ramp(2700, 0.7)
    assert len(ramp) == 768 and ramp[255] < 65535 and ramp[767] < ramp[511] < ramp[255]
    sunset = n.sunset(DAY, -2.9, -79.0, -5)  # Cuenca, Ecuador: about 18:10 all year
    assert dt.time(17, 55) <= sunset <= dt.time(18, 25)
    assert n.sunset(dt.date(2026, 6, 21), 78.2, 15.6, 2) is None  # Svalbard, midnight sun


def test_caffeine_cutoff_and_cycle_bedtimes():
    s = n.Settings(wake="06:30", need_h=7.5)
    assert n.bedtime(s) == dt.time(22, 45) and n.caffeine_cutoff(s) == dt.time(14, 45)
    assert n.bedtimes_for("06:30", 7.5)[0] == "22:45" and "21:15" in n.bedtimes_for("06:30", 7.5)
    assert "6 horas" in n.caffeine_note(s)


def test_the_diary_scores_hours_regularity_and_social_jetlag(tmp_path):
    diary = n.Diary.load(tmp_path / "sueno.json")
    start = dt.date(2026, 9, 28)  # Monday
    for i in range(7):
        day = start + dt.timedelta(days=i)
        weekend = day.weekday() >= 5
        diary.add("01:30" if weekend else "23:00", "10:00" if weekend else "06:30", day)
    st = n.stats(diary.nights)
    assert st["noches"] == 7 and 7.3 <= st["horas"] <= 8.0
    assert st["jetlag_social_h"] >= 2.5 and st["regularidad"] < 70
    text = n.report(diary.nights, n.Settings(wake="06:30"))
    assert "jet lag social" in text and "misma hora de despertar" in text
    assert n.Diary.load(tmp_path / "sueno.json").nights == diary.nights  # kept on disk
    assert "Aún no tengo noches" in n.report([], n.Settings())


def test_what_people_say():
    assert n.parse_diary("Me dormí a las 12 y me desperté a las 7:30") == ("00:00", "07:30")
    assert n.parse_diary("anoche me acosté a las 11:40 y me levanté a las 6") == ("23:40", "06:00")
    assert parse_quick("activa el night shift").kind == "night_on"
    assert parse_quick("desactiva el modo nocturno").kind == "night_off"
    assert parse_quick("me dormí a las 12 y me desperté a las 7").kind == "night_diary"
    q = parse_quick("¿a qué hora me acuesto si me levanto a las 6:30?")
    assert q.kind == "night_bedtime" and q.arg == "06:30"
    q = parse_quick("me levanto siempre a las 6")
    assert q.kind == "night_wake" and q.arg == "06:00"
    assert parse_quick("quiero dormir 7,5 horas").arg == "7.5"
    assert parse_quick("¿cómo he dormido esta semana?").kind == "night_report"
    assert parse_quick("no puedo dormir").kind == "night_insomnia"
    assert parse_quick("¿hasta qué hora puedo tomar café?").kind == "night_caffeine"
    assert "20 minutos" in n.INSOMNIA and "médico" in n.INSOMNIA


def test_the_veil_when_the_driver_refuses_gamma():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    from sergio_escritorio.nocturno_ui import NightScreen, veil

    warm, dark = veil(2700, 0.7)
    assert warm.alpha() > 60 and 60 < dark.alpha() < 80
    assert veil(6500, 1.0)[0].alpha() == 0 and veil(6500, 1.0)[1].alpha() == 0
    screen = NightScreen()
    screen.set(3000, 0.8)
    assert screen.veils and screen.veils[0].isVisible()
    screen.set(6500, 1.0)
    assert screen.veils == []

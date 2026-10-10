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
    phases = [
        n.moment(at(h, m), s, dusk)
        for h, m in ((14, 0), (19, 0), (21, 50), (22, 40), (23, 30), (3, 0), (7, 30))
    ]
    assert [p.phase for p in phases] == [
        "dia",
        "atardecer",
        "relajacion",
        "relajacion",
        "dormir",
        "dormir",
        "manana",
    ]
    assert (
        phases[1].kelvin < 6500 and 0.9 < phases[1].brightness <= 1.0 and not phases[1].quiet
    )  # warmer, barely darker
    assert (
        phases[3].kelvin < phases[2].kelvin
        and phases[3].brightness < 0.8
        and phases[3].quiet
    )  # darker before bed
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
    assert (
        n.sunset(dt.date(2026, 6, 21), 78.2, 15.6, 2) is None
    )  # Svalbard, midnight sun


def test_caffeine_cutoff_and_cycle_bedtimes():
    s = n.Settings(wake="06:30", need_h=7.5)
    assert n.bedtime(s) == dt.time(22, 45) and n.caffeine_cutoff(s) == dt.time(14, 45)
    assert n.bedtimes_for("06:30", 7.5)[0] == "22:45" and "21:15" in n.bedtimes_for(
        "06:30", 7.5
    )
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
    assert n.parse_diary("Me dormí a las 12 y me desperté a las 7:30") == (
        "00:00",
        "07:30",
    )
    assert n.parse_diary("anoche me acosté a las 11:40 y me levanté a las 6") == (
        "23:40",
        "06:00",
    )
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
    assert 20 < warm.alpha() <= 48 and 60 < dark.alpha() < 80  # mostly black: no grey film
    assert veil(6500, 1.0)[0].alpha() == 0 and veil(6500, 1.0)[1].alpha() == 0
    screen = NightScreen()
    screen.set(3000, 0.8)
    assert screen.veils and screen.veils[0].isVisible()
    screen.set(6500, 1.0)
    assert screen.veils == []


def test_research_curve_three_hours_and_candle_at_bed():
    s = n.Settings(wake="07:00", need_h=8, intensity=1.0)
    t = n.schedule(at(20, 0), s)
    assert t["start"] == at(19, 45) and t["wind"] == at(21, 45) and t["bed"] == at(22, 45)
    bed = n.moment(at(22, 44), s)
    assert bed.kelvin < 2000 and bed.brightness < 0.65 and bed.blue < 0.05
    asleep = n.moment(at(2, 0), s)
    assert asleep.phase == "dormir" and asleep.kelvin == round(n.mix_kelvin(6500, 1900, 1.0))
    # Sunset earlier than 3 h before bed: start there, gently.
    assert n.schedule(at(20, 0), s, dt.time(18, 10))["start"] == at(18, 10)
    # The morning fades back over 20 minutes instead of jumping.
    k0, k1 = n.moment(at(7, 0), s).kelvin, n.moment(at(7, 10), s).kelvin
    assert k0 < k1 < 6500 and n.moment(at(7, 25), s).kelvin == 6500


def test_the_curve_is_continuous_no_jumps():
    s = n.Settings(wake="07:00", need_h=8)
    last = None
    for minute in range(0, 24 * 60, 1):
        m = n.moment(at(0) + dt.timedelta(minutes=minute), s, dt.time(18, 10))
        if last is not None:
            assert abs(1e6 / m.kelvin - 1e6 / last.kelvin) < 25, (minute, last, m)
            assert abs(m.brightness - last.brightness) < 0.03
        last = m


def test_intensity_is_adjustable_and_noche_ya():
    s = n.set_intensity(n.Settings(), 40)
    assert s.intensity == 0.4
    gentle = n.looks(s)["night"]
    strong = n.looks(n.set_intensity(n.Settings(), 1.0))["night"]
    assert gentle[0] > strong[0] and gentle[1] > strong[1]
    assert n.set_intensity(n.Settings(), 5).intensity == 0.2  # never off by slider
    forced = n.force_now(n.Settings(wake="07:00"), at(15, 0))
    assert forced.force_until == "2026-10-08T07:00"
    m = n.moment(at(15, 0), forced)
    assert m.phase == "ahora" and m.kelvin < 3000 and not m.quiet
    assert n.moment(at(7, 30, DAY + dt.timedelta(days=1)), forced).phase == "manana"
    text = n.describe(n.Settings(), at(21, 0), dt.time(18, 10))
    assert "se calienta desde las 18:10" in text and "azul al" in text


def test_colour_matrix_multiplies_and_keeps_black():
    assert n.IDENTITY == [1.0 if i % 6 == 0 else 0.0 for i in range(25)]
    m = n.color_matrix(1900, 0.6)
    assert m[0] == 0.6 and 0.2 < m[6] < 0.4 and m[12] == 0.0 and m[18] == m[24] == 1.0
    assert all(v == 0.0 for i, v in enumerate(m) if i % 6)  # no offsets: black stays black
    assert n.white_point(6500) == (1.0, 1.0, 1.0)


def test_gamma_ramp_is_checked_and_softened_if_refused():
    full = n.ramp_at(2700, 0.7, 1.0)
    half = n.ramp_at(2700, 0.7, 0.5)
    plain = n.gamma_ramp(6500, 1.0)
    assert full == n.gamma_ramp(2700, 0.7) and plain[767] > half[767] > full[767]
    assert n.ramp_matches(full, full) and not n.ramp_matches(full, plain)


class FakeTint:
    def __init__(self, name="fake", ok=True):
        self.name, self.fps, self.ok, self.calls, self.resets = name, 1000.0, ok, [], 0

    def apply(self, k, b):
        self.calls.append((round(k), round(b, 3)))
        return self.ok

    def reset(self):
        self.resets += 1


def test_engine_fades_in_mired_steps_and_only_when_visible():
    now = [0.0]
    tint = FakeTint()
    engine = n.NightEngine(tint, clock=lambda: now[0])
    engine.go(2700, 0.7, fade_s=2.0)
    for i in range(0, 41):
        now[0] = i * 0.05
        engine.frame()
    assert tint.calls[-1] == (2700, 0.7) and not engine.fading()
    ks = [k for k, _ in tint.calls]
    assert ks == sorted(ks, reverse=True) and 10 < len(ks) <= 41  # smooth, monotonic
    calls = len(tint.calls)
    engine.go(2700, 0.7)  # same target: nothing to do
    engine.frame()
    assert len(tint.calls) == calls


def test_engine_thread_reaches_target_and_resets_on_stop():
    tint = FakeTint()
    engine = n.NightEngine(tint)
    engine.start()
    engine.go(3000, 0.8, fade_s=0.05)
    import time as _t

    deadline = _t.monotonic() + 3
    while engine.fading() and _t.monotonic() < deadline:
        _t.sleep(0.01)
    assert tint.calls[-1] == (3000, 0.8)
    engine.stop()
    assert tint.resets == 1


def test_chain_falls_back_to_the_next_way():
    broken, good = FakeTint("magnifier", ok=False), FakeTint("gamma")
    chain = n.ChainTint([broken, good])
    assert chain.name == "magnifier"
    assert chain.apply(3000, 0.9) and chain.name == "gamma" and broken.resets == 1
    assert n.ChainTint([]).apply(3000, 0.9) is False


def test_new_night_orders():
    cases = {
        "night shift más fuerte": ("night_more", ""),
        "baja el night shift": ("night_less", ""),
        "pon el night shift al 60 %": ("night_level", "60"),
        "night shift ya": ("night_now", ""),
        "night shift normal": ("night_auto", ""),
        "abre los ajustes del night shift": ("night_settings", ""),
    }
    for text, (kind, arg) in cases.items():
        q = parse_quick(text)
        assert (q.kind, q.arg) == (kind, arg), text


def test_the_sheet_previews_and_saves(monkeypatch):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    from sergio_escritorio.nocturno_ui import NightSheet

    state = {"s": n.Settings()}
    saved, previews = [], []
    sheet = NightSheet(lambda: n.load_settings(n.dump_settings(state["s"])),
                       lambda s: (saved.append(s), state.__setitem__("s", s)),
                       lambda k, b: previews.append((k, b)))
    sheet._preview(1.0)
    assert previews and previews[-1][0] < 2000
    sheet._set_intensity(0.5)
    assert state["s"].intensity == 0.5 and "50 %" in sheet.level.text()
    sheet._toggle_now()
    assert state["s"].force_until and sheet.now_button.text() == "Volver al horario"
    sheet._toggle_now()
    assert not state["s"].force_until
    sheet._toggle(False)
    assert state["s"].on is False
    img = sheet.grab()
    assert img.width() == sheet.WIDTH

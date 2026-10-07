"""Night Shift: Sergio winds the evening down, built on sleep research.

What the studies say, and what the mode does with it:

* A warm screen alone does not improve sleep: in the BYU study (Sleep
  Health, 2021, 167 adults with wrist actigraphy) iPhone Night Shift was no
  better than the phone without it. What counted was the light's
  *intensity* and the *engagement* (scrolling, texting). So the mode does
  both: warmer AND dimmer, and less pull from the screen.
* Evening light is powerful: half of the melatonin is suppressed at about
  25-30 lux, typical indoor light (Phillips et al., PNAS 2019), and people
  differ more than 50-fold. From sunset the screen warms slowly (6500 K ->
  3400 K); in the last hour before bed it gets warmer and dimmer
  (2700 K, 70 %), like a candle-lit room rather than an office.
* Regular times matter as much as hours: in 60 977 UK Biobank adults the
  most regular sleepers had 30 % lower mortality than the least regular,
  and regularity predicted it better than duration (Windred et al., Sleep
  2023). Sergio keeps a diary, scores the regularity and plans bedtime from
  a FIXED wake time.
* Adults need 7 h or more (AASM / Sleep Research Society consensus 2015;
  7-9 h). Bedtime = wake time - sleep need - ~15 min to fall asleep.
* Caffeine: 400 mg even 6 h before bed cut sleep by more than an hour, and
  people did not notice (Drake et al., J Clin Sleep Med 2013). Sergio
  reminds the cut-off at bedtime - 8 h.
* Alcohol: even about two drinks delay and shorten REM sleep, and the body
  does not adapt (systematic review and meta-analysis, Gardiner et al.,
  Sleep Med Rev 2025).
* Cool room, about 18-19 °C (15-19 °C is the usual range); morning
  daylight in the first hour anchors the clock.
* Can't sleep? CBT-I is the first-line treatment for chronic insomnia
  (American College of Physicians). Its stimulus control: if not asleep
  after about 20 minutes, get up, do something calm in dim light, come back
  when sleepy; no clock-watching.

During the last hour Sergio stays quiet: no mental-gym pop-ups, short
answers, only what you ask. Background tasks keep running.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DAY_K, EVENING_K, NIGHT_K = 6500, 3400, 2700
NIGHT_BRIGHTNESS = 0.7
FALL_ASLEEP_MIN = 15


@dataclass
class Settings:
    on: bool = True
    wake: str = "07:00"  # the anchor: the same every day, weekends too
    need_h: float = 8.0  # sleep wanted (adults: 7-9 h)
    wind_down_min: int = 60
    caffeine_h: float = 8.0  # last coffee this long before bed (Drake 2013: 6 h still hurts)
    warmth: bool = True  # warm and dim the screen in the evening
    lat: float | None = None
    lon: float | None = None


def _hm(text: str) -> dt.time:
    h, m = (int(x) for x in text.split(":"))
    return dt.time(h % 24, m % 60)


def bedtime(s: Settings) -> dt.time:
    """Wake time - sleep need - the minutes it takes to fall asleep."""
    wake = dt.datetime.combine(dt.date(2000, 1, 2), _hm(s.wake))
    return (wake - dt.timedelta(hours=s.need_h, minutes=FALL_ASLEEP_MIN)).time()


def _at(day: dt.date, t: dt.time) -> dt.datetime:
    return dt.datetime.combine(day, t)


def sunset(day: dt.date, lat: float, lon: float, utc_offset_h: float) -> dt.time | None:
    """Local sunset (NOAA's simple formula, about ±2 min); None at polar night/day."""
    n = day.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma) - 0.006758 * math.cos(2 * gamma)
            + 0.000907 * math.sin(2 * gamma) - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(math.radians(lat)) * math.cos(decl))
              - math.tan(math.radians(lat)) * math.tan(decl))
    if not -1 <= cos_ha <= 1:
        return None
    minutes = 720 - 4 * (lon - math.degrees(math.acos(cos_ha))) - eqtime + utc_offset_h * 60
    minutes %= 1440
    return dt.time(int(minutes // 60), int(minutes % 60))


@dataclass
class Moment:
    phase: str  # dia | atardecer | relajacion | dormir | manana
    kelvin: int
    brightness: float
    quiet: bool  # Sergio keeps quiet (no pop-ups, short answers)


def moment(now: dt.datetime, s: Settings, dusk: dt.time | None = None) -> Moment:
    """Where the evening is: the screen's warmth and light, and how quiet to be."""
    bed = bedtime(s)
    wake = _hm(s.wake)
    day = now.date()
    bed_at = _at(day, bed)
    if bed < wake and now.time() >= wake:  # bed after midnight: tonight's is tomorrow
        bed_at += dt.timedelta(days=1)
    if now.time() < wake and bed > wake:  # small hours: last night's bedtime
        bed_at -= dt.timedelta(days=1)
    wind = bed_at - dt.timedelta(minutes=s.wind_down_min)
    wake_at = bed_at + dt.timedelta(hours=s.need_h, minutes=FALL_ASLEEP_MIN)
    dusk_at = _at(bed_at.date() if bed_at.time() > dt.time(12) else bed_at.date() - dt.timedelta(days=1),
                  dusk or dt.time(19, 0))
    if dusk_at >= wind:
        dusk_at = wind - dt.timedelta(hours=1)
    if not s.on:
        return Moment("dia", DAY_K, 1.0, False)
    if bed_at <= now < wake_at:
        return Moment("dormir", NIGHT_K, NIGHT_BRIGHTNESS * 0.85, True)
    if dt.timedelta(0) <= now - _at(day, wake) < dt.timedelta(hours=2):
        return Moment("manana", DAY_K, 1.0, False)
    if wind <= now < bed_at:
        f = (now - wind) / (bed_at - wind)
        return Moment("relajacion", round(EVENING_K - f * (EVENING_K - NIGHT_K)),
                      round(1 - f * (1 - NIGHT_BRIGHTNESS), 3), True)
    if dusk_at <= now < wind:
        f = (now - dusk_at) / (wind - dusk_at)
        return Moment("atardecer", round(DAY_K - f * (DAY_K - EVENING_K)), 1.0, False)
    return Moment("dia", DAY_K, 1.0, False)


def kelvin_rgb(kelvin: float) -> tuple[float, float, float]:
    """White point of a colour temperature (Tanner Helland's fit), 0-1."""
    t = kelvin / 100
    red = 1.0 if t <= 66 else min(1.0, max(0.0, 329.698727446 * (t - 60) ** -0.1332047592 / 255))
    if t <= 66:
        green = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        green = 288.1221695283 * (t - 60) ** -0.0755148492
    blue = 1.0 if t >= 66 else (0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    return red, min(1.0, max(0.0, green / 255)), min(1.0, max(0.0, blue / 255 if t < 66 else blue))


def gamma_ramp(kelvin: float, brightness: float = 1.0) -> list[int]:
    """The 3 x 256 ramp (red, green, blue) that SetDeviceGammaRamp expects."""
    r, g, b = kelvin_rgb(kelvin)
    ramp = []
    for channel in (r, g, b):
        ramp += [min(65535, int(i * 257 * channel * brightness)) for i in range(256)]
    return ramp


def caffeine_cutoff(s: Settings) -> dt.time:
    return (_at(dt.date(2000, 1, 2), bedtime(s)) - dt.timedelta(hours=s.caffeine_h)).time()


def bedtimes_for(wake: str, need_h: float = 8.0) -> list[str]:
    """Bedtimes for a wake time: the planned one, plus 6 and 5 sleep cycles
    of about 90 min (cycles vary 70-120 min, so they are estimates)."""
    w = _at(dt.date(2000, 1, 2), _hm(wake))
    lat = dt.timedelta(minutes=FALL_ASLEEP_MIN)
    times = [w - dt.timedelta(hours=need_h) - lat, w - dt.timedelta(minutes=540) - lat,
             w - dt.timedelta(minutes=450) - lat]
    return list(dict.fromkeys(t.strftime("%H:%M") for t in times))


# -- the sleep diary ----------------------------------------------------------

@dataclass
class Diary:
    path: Path
    nights: list[dict[str, str]] = field(default_factory=list)  # {"fecha", "dormir", "despertar"}

    @classmethod
    def load(cls, path: Path) -> Diary:
        try:
            return cls(path, json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return cls(path, [])

    def add(self, bed: str, wake: str, day: dt.date | None = None) -> dict[str, str]:
        day = day or dt.date.today()
        entry = {"fecha": day.isoformat(), "dormir": bed, "despertar": wake}
        self.nights = [n for n in self.nights if n["fecha"] != entry["fecha"]] + [entry]
        self.nights = sorted(self.nights, key=lambda n: n["fecha"])[-120:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.nights, ensure_ascii=False, indent=1), encoding="utf-8")
        return entry


def _minutes(t: str) -> int:
    """Minutes on a clock that runs from noon to noon (so 23:30 < 00:30)."""
    h, m = (int(x) for x in t.split(":"))
    value = h * 60 + m
    return value + 1440 if value < 720 else value


def stats(nights: list[dict[str, str]], last: int = 14) -> dict[str, Any] | None:
    recent = nights[-last:]
    if not recent:
        return None
    beds = [_minutes(n["dormir"]) for n in recent]
    wakes = [_minutes(n["despertar"]) for n in recent]
    hours = [((w - b) % 1440) / 60 for b, w in zip(beds, wakes)]
    mids = [b + ((w - b) % 1440) / 2 for b, w in zip(beds, wakes)]
    spread = statistics.pstdev(mids) if len(mids) > 1 else 0.0
    # Regularity 0-100: 100 when the middle of sleep moves < 15 min, 0 at >= 2 h.
    regular = round(max(0.0, min(100.0, 100 * (1 - (spread - 15) / 105))))
    weekday = [m for m, n in zip(mids, recent) if dt.date.fromisoformat(n["fecha"]).weekday() < 5]
    weekend = [m for m, n in zip(mids, recent) if dt.date.fromisoformat(n["fecha"]).weekday() >= 5]
    jetlag = (statistics.mean(weekend) - statistics.mean(weekday)) / 60 if weekday and weekend else 0.0
    return {"noches": len(recent), "horas": round(statistics.mean(hours), 1), "min_horas": round(min(hours), 1),
            "regularidad": regular, "desfase_min": round(spread), "jetlag_social_h": round(jetlag, 1)}


def report(nights: list[dict[str, str]], s: Settings) -> str:
    st = stats(nights)
    if st is None:
        return ("Aún no tengo noches anotadas. Dígame por la mañana «me dormí a las 12 y me desperté a las 7» "
                "y en una semana le digo cómo va.")
    parts = [f"Últimas {st['noches']} noches: duerme {st['horas']} h de media (la peor, {st['min_horas']} h)."]
    parts.append(f"Regularidad {st['regularidad']}/100 (la mitad de su sueño se mueve ±{st['desfase_min']} min).")
    if st["horas"] < 7:
        parts.append(f"Por debajo de las 7 h recomendadas: para levantarse a las {s.wake}, a la cama a las "
                     f"{bedtime(s).strftime('%H:%M')}.")
    if st["regularidad"] < 70:
        parts.append("Lo que más le ayudaría: la misma hora de despertar todos los días, fines de semana incluidos "
                     "(la regularidad predice la salud mejor que las horas).")
    if abs(st["jetlag_social_h"]) >= 1:
        parts.append(f"El fin de semana duerme {abs(st['jetlag_social_h'])} h desplazado: «jet lag social». "
                     "Acercar los horarios del finde a los de diario.")
    if st["horas"] >= 7 and st["regularidad"] >= 70:
        parts.append("Buen ritmo. Siga así.")
    return " ".join(parts)


TIME = r"(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm|de la noche|de la manana|de la madrugada)?"
DIARY = re.compile(
    r"\b(?:me dormi|me acoste|me fui a dormir|dormi)\b.*?\b(?:a las|a la)\s+" + TIME
    + r".*?\b(?:me desperte|desperte|me levante)\b.*?\b(?:a las|a la)\s+" + TIME,
    re.I,
)


def _clock(h: str, m: str | None, part: str | None, evening: bool) -> str:
    hour = int(h) % 24
    part = (part or "").lower()
    if part in ("pm", "de la noche") and hour < 12:
        hour += 12
    elif part in ("am", "de la manana", "de la madrugada") and hour == 12:
        hour = 0
    elif not part and evening and 6 <= hour <= 11:  # «me dormí a las 11» is at night
        hour += 12
    elif not part and evening and hour == 12:  # «a las 12»: midnight
        hour = 0
    return f"{hour:02d}:{int(m or 0):02d}"


def parse_diary(text: str) -> tuple[str, str] | None:
    """«me dormí a las 12 y me desperté a las 7:30» -> ('00:00', '07:30')."""
    import unicodedata

    plain = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    found = DIARY.search(plain)
    if not found:
        return None
    g = found.groups()
    return _clock(g[0], g[1], g[2], True), _clock(g[3], g[4], g[5], False)


INSOMNIA = (
    "Si lleva unos 20 minutos sin dormirse, levántese. Haga algo tranquilo con luz tenue, como leer en papel o "
    "respirar despacio: 4 segundos al inhalar y 6 al exhalar. Vuelva a la cama solo cuando tenga sueño, y no "
    "mire el reloj. Mañana, a su hora de siempre aunque haya dormido poco. Es el «control de estímulos» de la "
    "terapia cognitivo-conductual para el insomnio, el primer tratamiento recomendado. Si le pasa más de 3 "
    "noches por semana durante 3 meses, consúltelo con un médico."
)

TIPS = {
    "atardecer": "Desde ahora la pantalla se va calentando. Baje también las luces de casa: lo que más pesa es "
                 "la intensidad, y con unos 30 lux ya se frena la mitad de la melatonina.",
    "relajacion": "Queda una hora para dormir. Le bajo la luz de la pantalla y me quedo callado. Evite el "
                  "alcohol (recorta el sueño REM) y el móvil en la cama; deje el cuarto a unos 18-19 °C.",
    "dormir": "Es su hora de dormir. Las tareas siguen en segundo plano; mañana le cuento.",
    "manana": "Buenos días. Luz natural en la primera hora: es lo que más ancla el reloj interno.",
}


def caffeine_note(s: Settings) -> str:
    return (f"Último café a las {caffeine_cutoff(s).strftime('%H:%M')}: la cafeína incluso 6 horas antes de "
            "dormir quitó más de una hora de sueño en un estudio, y nadie lo notó.")


def describe(s: Settings, now: dt.datetime | None = None, dusk: dt.time | None = None) -> str:
    now = now or dt.datetime.now()
    m = moment(now, s, dusk)
    bed = bedtime(s).strftime("%H:%M")
    state = "activo" if s.on else "apagado"
    return (f"Night Shift {state}: despertar {s.wake}, a la cama {bed} ({s.need_h:g} h de sueño), "
            f"relajación desde {s.wind_down_min} min antes, último café {caffeine_cutoff(s).strftime('%H:%M')}. "
            f"Ahora: {m.phase}, pantalla a {m.kelvin} K y {round(m.brightness * 100)} %.")


def load_settings(data: dict[str, Any] | None) -> Settings:
    base = Settings()
    for key, value in (data or {}).items():
        if hasattr(base, key):
            setattr(base, key, value)
    return base


def dump_settings(s: Settings) -> dict[str, Any]:
    return asdict(s)


# -- the screen (Windows) ----------------------------------------------------

def apply_gamma(kelvin: float, brightness: float) -> bool:  # pragma: no cover — Windows GDI
    """Warm and dim the whole screen; False if the driver refuses (then the
    overlay does it)."""
    import ctypes

    try:
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        ramp = (ctypes.c_ushort * 768)(*gamma_ramp(kelvin, brightness))
        hdc = user32.GetDC(None)
        try:
            return bool(gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp)))
        finally:
            user32.ReleaseDC(None, hdc)
    except Exception:  # noqa: BLE001 — not Windows, or no GDI
        return False


def restore_gamma() -> None:  # pragma: no cover — Windows GDI
    apply_gamma(DAY_K, 1.0)


__all__ = [
    "Diary", "INSOMNIA", "Moment", "Settings", "TIPS", "apply_gamma", "bedtime", "bedtimes_for", "caffeine_cutoff",
    "caffeine_note", "describe", "dump_settings", "gamma_ramp", "kelvin_rgb", "load_settings", "moment",
    "parse_diary", "report", "restore_gamma", "stats", "sunset",
]

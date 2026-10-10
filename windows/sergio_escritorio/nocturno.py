"""Night Shift: Sergio winds the evening down, built on sleep research.

What the studies say, and what the mode does with it:

* The consensus on indoor light (Brown et al., PLOS Biology 2022, 21
  sleep and circadian scientists): from at least 3 hours before bedtime,
  at most 10 lux melanopic EDI at the eye; while sleeping, at most 1 lux
  (10 if you must see); in the day, at least 250. Melanopic light is the
  blue-cyan light the eye's clock cells (melanopsin, peak near 480 nm)
  respond to. So the screen starts warming 3 h before bed (or at sunset,
  if that comes first) and keeps going down to a candle-like 1900 K and
  60 % light at bedtime, at full intensity.
* A warm screen alone does not improve sleep: in the BYU study (Sleep
  Health, 2021, 167 adults with wrist actigraphy) iPhone Night Shift was no
  better than the phone without it. What counted was the light's
  *intensity* and the *engagement* (scrolling, texting). So the mode does
  both: warmer AND dimmer, and less pull from the screen.
* Evening light is powerful: half of the melatonin is suppressed at about
  25-30 lux, typical indoor light (Phillips et al., PNAS 2019), and people
  differ more than 50-fold. That is why the intensity is adjustable.
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

How the screen changes, without lag and without a grey film:

* Windows' own colour matrix for the desktop (the Magnification API,
  Windows 8+) multiplies each channel: blacks stay black, contrast stays,
  every monitor at once, no window on top. If that is unavailable, a gamma
  ramp per monitor, checked after setting it (the driver can refuse it in
  silence); only as a last resort, a light veil.
* A fader on its own thread moves between looks in mired steps (even to
  the eye), so nothing jumps and the interface thread never waits.

During the last hour Sergio stays quiet: no mental-gym pop-ups, short
answers, only what you ask. Background tasks keep running.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import re
import statistics
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

DAY_K, EVENING_K, NIGHT_K = 6500, 3000, 1900  # 1900 K: candlelight
EVENING_BRIGHTNESS, NIGHT_BRIGHTNESS = 0.9, 0.6  # at full intensity
EVENING_H = 3.0  # Brown et al. 2022: dim light from at least 3 h before bed
MORNING_FADE_MIN = 20
FALL_ASLEEP_MIN = 15


@dataclass
class Settings:
    on: bool = True
    wake: str = "07:00"  # the anchor: the same every day, weekends too
    need_h: float = 8.0  # sleep wanted (adults: 7-9 h)
    wind_down_min: int = 60
    caffeine_h: float = 8.0  # last coffee this long before bed (Drake 2013: 6 h still hurts)
    warmth: bool = True  # warm and dim the screen in the evening
    intensity: float = 0.85  # 0.2 gentle … 1.0 candle at bedtime
    evening_h: float = EVENING_H
    force_until: str = ""  # «night shift ahora»: the night look until this ISO time
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
    phase: str  # dia | atardecer | relajacion | dormir | manana | ahora
    kelvin: int
    brightness: float
    quiet: bool  # Sergio keeps quiet (no pop-ups, short answers)

    @property
    def blue(self) -> float:
        """How much of the screen's blue is left (0-1): blue channel x light."""
        return round(white_point(self.kelvin)[2] * self.brightness, 3)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _smooth(f: float) -> float:
    f = _clamp(f, 0.0, 1.0)
    return f * f * (3 - 2 * f)


def mix_kelvin(a: float, b: float, f: float) -> float:
    """Between two colour temperatures in mireds (1e6 / K): even steps to the eye."""
    return 1e6 / ((1e6 / a) + ((1e6 / b) - (1e6 / a)) * _clamp(f, 0.0, 1.0))


def looks(s: Settings) -> dict[str, tuple[float, float]]:
    """The evening and bedtime looks for this intensity: (kelvin, brightness)."""
    i = _clamp(float(s.intensity), 0.2, 1.0)
    evening_k = mix_kelvin(DAY_K, EVENING_K, i)
    night_k = mix_kelvin(DAY_K, NIGHT_K, i)
    return {
        "day": (DAY_K, 1.0),
        "evening": (evening_k, 1 - (1 - EVENING_BRIGHTNESS) * i),
        "night": (night_k, 1 - (1 - NIGHT_BRIGHTNESS) * i),
    }


def _between(a: tuple[float, float], b: tuple[float, float], f: float) -> tuple[int, float]:
    f = _smooth(f)
    return round(mix_kelvin(a[0], b[0], f)), round(a[1] + (b[1] - a[1]) * f, 3)


def schedule(now: dt.datetime, s: Settings, dusk: dt.time | None = None) -> dict[str, dt.datetime]:
    """Tonight's times: start of the evening, wind-down, bed, wake."""
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
    start = bed_at - dt.timedelta(hours=max(1.0, float(s.evening_h)))
    if dusk is not None:
        dusk_day = bed_at.date() if bed_at.time() > dt.time(12) else bed_at.date() - dt.timedelta(days=1)
        dusk_at = _at(dusk_day, dusk)
        if wind - dt.timedelta(hours=6) < dusk_at < start:  # sunset first: start then, more gently
            start = dusk_at
    if start >= wind:
        start = wind - dt.timedelta(hours=1)
    return {"start": start, "wind": wind, "bed": bed_at, "wake": wake_at}


def _forced(now: dt.datetime, s: Settings) -> bool:
    if not s.force_until:
        return False
    try:
        return now < dt.datetime.fromisoformat(s.force_until)
    except ValueError:
        return False


def moment(now: dt.datetime, s: Settings, dusk: dt.time | None = None) -> Moment:
    """Where the evening is: the screen's warmth and light, and how quiet to be."""
    if not s.on:
        return Moment("dia", DAY_K, 1.0, False)
    look = looks(s)
    if _forced(now, s):
        k, b = look["night"]
        return Moment("ahora", round(k), round(b, 3), False)
    t = schedule(now, s, dusk)
    if t["bed"] <= now < t["wake"]:
        k, b = look["night"]
        return Moment("dormir", round(k), round(b, 3), True)
    since_wake = now - _at(now.date(), _hm(s.wake))
    if dt.timedelta(0) <= since_wake < dt.timedelta(hours=2):
        k, b = _between(look["night"], look["day"], since_wake / dt.timedelta(minutes=MORNING_FADE_MIN))
        return Moment("manana", k, b, False)
    if t["wind"] <= now < t["bed"]:
        k, b = _between(look["evening"], look["night"], (now - t["wind"]) / (t["bed"] - t["wind"]))
        return Moment("relajacion", k, b, True)
    if t["start"] <= now < t["wind"]:
        k, b = _between(look["day"], look["evening"], (now - t["start"]) / (t["wind"] - t["start"]))
        return Moment("atardecer", k, b, False)
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


def white_point(kelvin: float) -> tuple[float, float, float]:
    """Channel gains for a colour temperature, with 6500 K (D65, the screen's
    own white) exactly neutral."""
    if kelvin >= DAY_K:
        return 1.0, 1.0, 1.0
    ref = kelvin_rgb(DAY_K)
    return tuple(min(1.0, c / r) if r else c for c, r in zip(kelvin_rgb(kelvin), ref))  # type: ignore[return-value]


def gamma_ramp(kelvin: float, brightness: float = 1.0) -> list[int]:
    """The 3 x 256 ramp (red, green, blue) that SetDeviceGammaRamp expects."""
    r, g, b = white_point(kelvin)
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


PHASE_ES = {"dia": "de día", "atardecer": "atardecer", "relajacion": "relajación", "dormir": "hora de dormir",
            "manana": "mañana", "ahora": "modo noche ya"}


def describe(s: Settings, now: dt.datetime | None = None, dusk: dt.time | None = None) -> str:
    now = now or dt.datetime.now()
    m = moment(now, s, dusk)
    t = schedule(now, s, dusk)
    bed = bedtime(s).strftime("%H:%M")
    state = "activo" if s.on else "apagado"
    return (f"Night Shift {state} al {round(s.intensity * 100)} %: se calienta desde las "
            f"{t['start'].strftime('%H:%M')}, relajación desde las {t['wind'].strftime('%H:%M')}, a la cama {bed} "
            f"({s.need_h:g} h de sueño, despertar {s.wake}), último café {caffeine_cutoff(s).strftime('%H:%M')}. "
            f"Ahora: {PHASE_ES.get(m.phase, m.phase)}, pantalla a {m.kelvin} K y {round(m.brightness * 100)} % "
            f"de luz, azul al {round(m.blue * 100)} %.")


def set_intensity(s: Settings, value: float) -> Settings:
    """0.2-1.0 (also accepts 20-100)."""
    v = float(value)
    s.intensity = round(_clamp(v / 100 if v > 1.5 else v, 0.2, 1.0), 2)
    return s


def force_now(s: Settings, now: dt.datetime | None = None) -> Settings:
    """The night look right away, until the next wake time."""
    now = now or dt.datetime.now()
    wake = _at(now.date(), _hm(s.wake))
    if wake <= now:
        wake += dt.timedelta(days=1)
    s.on = s.warmth = True
    s.force_until = wake.isoformat(timespec="minutes")
    return s


def load_settings(data: dict[str, Any] | None) -> Settings:
    base = Settings()
    for key, value in (data or {}).items():
        if hasattr(base, key):
            setattr(base, key, value)
    return base


def dump_settings(s: Settings) -> dict[str, Any]:
    return asdict(s)


# -- the screen ---------------------------------------------------------------

def color_matrix(kelvin: float, brightness: float = 1.0) -> list[float]:
    """The 5 x 5 colour matrix (row-major) that multiplies each channel:
    [r g b a 1] x M, as Windows' MAGCOLOREFFECT expects. Black stays black."""
    r, g, b = white_point(kelvin)
    light = _clamp(brightness, 0.05, 1.0)
    m = [0.0] * 25
    m[0], m[6], m[12], m[18], m[24] = r * light, g * light, b * light, 1.0, 1.0
    return m


IDENTITY = color_matrix(DAY_K, 1.0)


class Tint(Protocol):
    name: str
    fps: float

    def apply(self, kelvin: float, brightness: float) -> bool: ...

    def reset(self) -> None: ...


class ChainTint:
    """The best way this PC allows, falling back in order when one fails."""

    def __init__(self, tints: list[Tint]) -> None:
        self.tints = list(tints)

    @property
    def name(self) -> str:
        return self.tints[0].name if self.tints else "none"

    @property
    def fps(self) -> float:
        return self.tints[0].fps if self.tints else 1.0

    def apply(self, kelvin: float, brightness: float) -> bool:
        while self.tints:
            try:
                if self.tints[0].apply(kelvin, brightness):
                    return True
            except Exception:  # noqa: BLE001 — a backend that breaks is skipped
                logging.debug("night tint %s failed", self.tints[0].name, exc_info=True)
            dead = self.tints.pop(0)
            logging.info("Night Shift: %s unavailable, trying the next way", dead.name)
            try:
                dead.reset()
            except Exception:  # noqa: BLE001
                pass
        return False

    def reset(self) -> None:
        for tint in self.tints:
            try:
                tint.reset()
            except Exception:  # noqa: BLE001
                logging.debug("night tint reset failed", exc_info=True)


class NightEngine:
    """Moves the screen to its target look over a fade, on its own thread.

    The interface only says where to go (``go``); this thread does every
    Windows call, at the backend's frame rate and only when the change is
    visible (half a mired or 0.2 % of light), so nothing lags or jumps."""

    MIRED_STEP, LIGHT_STEP = 0.5, 0.002

    def __init__(self, tint: Tint, clock: Callable[[], float] = time.monotonic) -> None:
        self.tint = tint
        self.clock = clock
        self.current: tuple[float, float] = (DAY_K, 1.0)
        self.applied: tuple[float, float] | None = None
        self._from = self._to = self.current
        self._t0 = 0.0
        self._dur = 0.0
        self._cond = threading.Condition()
        self._quit = False
        self._thread: threading.Thread | None = None

    @property
    def target(self) -> tuple[float, float]:
        return self._to

    def go(self, kelvin: float, brightness: float, fade_s: float = 2.0) -> None:
        with self._cond:
            to = (float(kelvin), float(_clamp(brightness, 0.05, 1.0)))
            if to == self._to and self.applied is not None:
                return
            self._from, self._to = self.current, to
            self._t0, self._dur = self.clock(), max(0.0, fade_s)
            self._cond.notify()

    def fading(self) -> bool:
        return self.applied != self._to

    def frame(self, now: float | None = None) -> bool:
        """One step; True while still on the way."""
        if not self.fading():
            return False
        now = self.clock() if now is None else now
        f = 1.0 if self._dur <= 0 else _clamp((now - self._t0) / self._dur, 0.0, 1.0)
        e = _smooth(f)
        k = mix_kelvin(self._from[0], self._to[0], e)
        b = self._from[1] + (self._to[1] - self._from[1]) * e
        self.current = (k, b)
        last = self.applied
        visible = last is None or abs(1e6 / k - 1e6 / last[0]) >= self.MIRED_STEP or abs(b - last[1]) >= self.LIGHT_STEP
        if visible or f >= 1.0:
            if self.tint.apply(k, b):
                self.applied = (k, b) if f < 1.0 else self._to
            elif f >= 1.0:
                self.applied = self._to  # nothing can tint: don't spin
        return f < 1.0

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._quit and not self.fading():
                    self._cond.wait(5.0)
                if self._quit:
                    break
            try:
                self.frame()
            except Exception:  # noqa: BLE001 — the screen never breaks Sergio
                logging.exception("night shift frame failed")
                self.applied = self._to
            time.sleep(1.0 / max(1.0, float(self.tint.fps)))
        try:
            self.tint.reset()
        except Exception:  # noqa: BLE001
            logging.debug("night shift reset failed", exc_info=True)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="night-shift", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 1.5) -> None:
        with self._cond:
            self._quit = True
            self._cond.notify()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None


class MagnifierTint:  # pragma: no cover — Windows 8+ DWM
    """The desktop's colour matrix (Magnification API): every monitor, no
    window on top, no driver limits. Called only from the engine's thread."""

    name, fps = "magnifier", 60.0

    def __init__(self) -> None:
        self._dll: Any = None

    def _ready(self) -> bool:
        if self._dll is None:
            import ctypes

            dll = ctypes.WinDLL("Magnification")
            dll.MagInitialize.restype = ctypes.c_bool
            dll.MagSetFullscreenColorEffect.restype = ctypes.c_bool
            dll.MagSetFullscreenColorEffect.argtypes = [ctypes.c_void_p]
            if not dll.MagInitialize():
                raise OSError("MagInitialize failed")
            self._dll = dll
        return True

    def apply(self, kelvin: float, brightness: float) -> bool:
        import ctypes

        self._ready()
        effect = (ctypes.c_float * 25)(*color_matrix(kelvin, brightness))
        return bool(self._dll.MagSetFullscreenColorEffect(ctypes.byref(effect)))

    def reset(self) -> None:
        if self._dll is not None:
            import ctypes

            effect = (ctypes.c_float * 25)(*IDENTITY)
            self._dll.MagSetFullscreenColorEffect(ctypes.byref(effect))
            self._dll.MagUninitialize()
            self._dll = None


def ramp_at(kelvin: float, brightness: float, strength: float = 1.0) -> list[int]:
    """A gamma ramp blended toward the identity: strength 1 is the full look."""
    full = gamma_ramp(kelvin, brightness)
    plain = gamma_ramp(DAY_K, 1.0)
    return [round(p + (f - p) * strength) for p, f in zip(plain, full)]


def ramp_matches(wanted: list[int], got: list[int], slack: int = 384) -> bool:
    """SetDeviceGammaRamp can return TRUE and set nothing: compare what stuck."""
    return all(abs(w - g) <= slack for w, g in zip(wanted[::17], got[::17]))


class GammaTint:  # pragma: no cover — Windows GDI
    """A gamma ramp on each monitor, verified after setting; if the driver
    keeps only part of it, the strongest look it accepts."""

    name, fps = "gamma", 20.0

    def __init__(self) -> None:
        self.strength: dict[str, float] = {}

    @staticmethod
    def displays() -> list[str]:
        import ctypes
        from ctypes import wintypes

        class DisplayDevice(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                        ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                        ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]

        names, i = [], 0
        while True:
            dd = DisplayDevice()
            dd.cb = ctypes.sizeof(dd)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            if dd.StateFlags & 0x1:  # attached to the desktop
                names.append(dd.DeviceName)
            i += 1
        return names or [""]

    def _set(self, device: str, ramp: list[int]) -> bool:
        import ctypes

        gdi32 = ctypes.windll.gdi32
        hdc = gdi32.CreateDCW(None, device, None, None) if device else ctypes.windll.user32.GetDC(None)
        if not hdc:
            return False
        try:
            want = (ctypes.c_ushort * 768)(*ramp)
            if not gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(want)):
                return False
            got = (ctypes.c_ushort * 768)()
            if not gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(got)):
                return True
            return ramp_matches(ramp, list(got))
        finally:
            if device:
                gdi32.DeleteDC(hdc)
            else:
                ctypes.windll.user32.ReleaseDC(None, hdc)

    def apply(self, kelvin: float, brightness: float) -> bool:
        ok = False
        for device in self.displays():
            strength = self.strength.get(device, 1.0)
            while strength >= 0.3:
                if self._set(device, ramp_at(kelvin, brightness, strength)):
                    self.strength[device] = strength
                    ok = True
                    break
                strength = round(strength * 0.8, 3)
            else:
                self.strength[device] = 1.0
        return ok

    def reset(self) -> None:
        for device in self.displays():
            self._set(device, gamma_ramp(DAY_K, 1.0))


def windows_tints() -> list[Tint]:
    """The ways to tint, best first (only the ones this system may have)."""
    import sys

    if sys.platform != "win32":
        return []
    return [MagnifierTint(), GammaTint()]


def apply_gamma(kelvin: float, brightness: float) -> bool:  # pragma: no cover — Windows GDI
    """Old entry point: one verified gamma ramp per monitor."""
    try:
        return GammaTint().apply(kelvin, brightness)
    except Exception:  # noqa: BLE001 — not Windows, or no GDI
        return False


def restore_gamma() -> None:  # pragma: no cover — Windows GDI
    try:
        GammaTint().reset()
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "ChainTint", "Diary", "GammaTint", "IDENTITY", "INSOMNIA", "MagnifierTint", "Moment", "NightEngine", "Settings",
    "TIPS", "Tint", "apply_gamma", "bedtime", "bedtimes_for", "caffeine_cutoff", "caffeine_note", "color_matrix",
    "describe", "dump_settings", "force_now", "set_intensity", "PHASE_ES", "gamma_ramp", "kelvin_rgb", "white_point", "load_settings", "looks", "mix_kelvin", "moment",
    "parse_diary", "ramp_at", "ramp_matches", "report", "restore_gamma", "schedule", "stats", "sunset",
    "windows_tints",
]

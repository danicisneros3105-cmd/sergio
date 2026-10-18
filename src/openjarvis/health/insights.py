"""What the numbers say, computed by code from the owner's own data.

* ``overview``     — each metric: latest day, 30-day baseline, trend, range.
* ``highlights``   — a few plain sentences about what changed (Resumen).
* ``readiness``    — today's readiness from variability, resting pulse and sleep
  against the owner's own baseline (only the inputs that exist are used, and
  they are listed).
* ``longevity``    — seven areas, each against public guidance.
* ``correlations`` — what moves with what (and with the owner's day tags),
  with the number of days behind it; correlation is not cause.

Nothing is estimated from missing data: no data, no number.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from openjarvis.health.metrics import BY_KEY, CATEGORIES, METRICS, classify
from openjarvis.health.store import HealthStore, day_of

BASELINE_DAYS = 30
MIN_DAYS_FOR_CORRELATION = 14


def _mean(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _round(metric: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    decimals = BY_KEY[metric].decimals
    return round(value, decimals) if decimals else float(round(value))


def _say(metric: str, value: float) -> str:
    """A value as the owner reads it: «6933», «7,6»."""
    decimals = BY_KEY[metric].decimals
    text = f"{value:.{decimals}f}" if decimals else f"{round(value):d}"
    return text.replace(".", ",")


def metric_summary(
    store: HealthStore, metric: str, now: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    now = now or time.time()
    series = store.daily(metric, days=120, now=now)
    if not series:
        return None
    m = BY_KEY[metric]
    days = sorted(series)
    last_day = days[-1]
    latest = series[last_day]
    since = day_of(now - BASELINE_DAYS * 86400)
    base_days = [d for d in days if since <= d < last_day]
    baseline = _mean([series[d] for d in base_days]) if len(base_days) >= 5 else None
    # A day still running (today's steps at noon) is not compared or judged yet.
    partial = m.daily == "sum" and last_day == day_of(now)
    change = None
    if baseline and not partial:
        change = (latest - baseline) / baseline * 100
    goals = store.goals()
    return {
        "metric": metric,
        "label": m.label,
        "unit": m.unit,
        "category": m.category,
        "day": last_day,
        "value": _round(metric, latest),
        "baseline": _round(metric, baseline),
        "change_pct": round(change, 1) if change is not None else None,
        "status": "" if partial else classify(m, latest),
        "partial": partial,
        "goal": goals.get(metric),
        "spark": [[d, _round(metric, series[d])] for d in days[-30:]],
    }


def overview(store: HealthStore, now: Optional[float] = None) -> Dict[str, Any]:
    have = store.metrics_with_data()
    items = {k: metric_summary(store, k, now) for k in have if k in BY_KEY}
    items = {k: v for k, v in items.items() if v}
    categories = []
    for key, label in CATEGORIES:
        ms = [items[m.key] for m in METRICS if m.category == key and m.key in items]
        categories.append({"key": key, "label": label, "metrics": ms})
    return {"metrics": items, "categories": categories, "pins": store.pins()}


def _better(metric: str, change: float) -> Optional[bool]:
    direction = BY_KEY[metric].better
    if direction == "up":
        return change > 0
    if direction == "down":
        return change < 0
    return None


def highlights(
    store: HealthStore, now: Optional[float] = None, limit: int = 5
) -> List[Dict[str, Any]]:
    """The biggest real changes against the owner's own 30-day baseline."""
    out = []
    for metric, s in overview(store, now)["metrics"].items():
        if s["change_pct"] is None or abs(s["change_pct"]) < 8:
            continue
        m = BY_KEY[metric]
        good = _better(metric, s["change_pct"])
        word = "más alto" if s["change_pct"] > 0 else "más bajo"
        unit = f" {m.unit}" if m.unit and not m.unit.startswith("/") else m.unit
        text = (
            f"{m.label}: {_say(metric, s['value'])}{unit} el {s['day'][8:]}/{s['day'][5:7]}, "
            f"un {abs(s['change_pct']):.0f} % {word} que su media de {BASELINE_DAYS} días "
            f"({_say(metric, s['baseline'])}{unit})."
        )
        out.append(
            {"metric": metric, "text": text, "good": good, "size": abs(s["change_pct"])}
        )
    out.sort(key=lambda h: -h["size"])
    for h in out:
        h.pop("size")
    return out[:limit]


def readiness(store: HealthStore, now: Optional[float] = None) -> Dict[str, Any]:
    """0–100 from today's variability, resting pulse and sleep vs the baseline.

    Each input scores 0–100 (50 = your usual); missing inputs are left out and
    named. With fewer than two inputs there is no score: guessing is worse.
    """
    now = now or time.time()
    today = day_of(now)
    yesterday = day_of(now - 86400)
    parts: List[Tuple[str, float, str]] = []

    def recent(metric: str) -> Tuple[Optional[float], Optional[float]]:
        series = store.daily(metric, days=BASELINE_DAYS + 2, now=now)
        value = series.get(today, series.get(yesterday))
        base = [v for d, v in series.items() if d not in (today, yesterday)]
        return value, (_mean(base) if len(base) >= 5 else None)

    hrv, hrv_base = recent("hrv")
    if hrv is not None and hrv_base:
        parts.append(
            (
                "hrv",
                max(0.0, min(100.0, 50 + (hrv / hrv_base - 1) * 150)),
                "Variabilidad cardiaca",
            )
        )
    rhr, rhr_base = recent("resting_hr")
    if rhr is not None and rhr_base:
        parts.append(
            (
                "resting_hr",
                max(0.0, min(100.0, 50 - (rhr / rhr_base - 1) * 250)),
                "Pulso en reposo",
            )
        )
    sleep, _ = recent("sleep_h")
    if sleep is not None:
        parts.append(("sleep_h", max(0.0, min(100.0, sleep / 8.0 * 100)), "Sueño"))
    missing = [
        label
        for key, label in (
            ("hrv", "Variabilidad cardiaca"),
            ("resting_hr", "Pulso en reposo"),
            ("sleep_h", "Sueño"),
        )
        if key not in {p[0] for p in parts}
    ]
    if len(parts) < 2:
        return {"score": None, "inputs": [p[2] for p in parts], "missing": missing}
    score = round(sum(p[1] for p in parts) / len(parts))
    word = (
        "Lista para exigirse"
        if score >= 70
        else "Día normal"
        if score >= 45
        else "Mejor ir suave"
    )
    return {
        "score": score,
        "word": word,
        "inputs": [p[2] for p in parts],
        "missing": missing,
        "parts": {p[0]: round(p[1]) for p in parts},
    }


LONGEVITY_AREAS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("movimiento", "Movimiento", ("steps", "exercise_min")),
    ("forma", "Forma cardiorrespiratoria", ("vo2max",)),
    ("corazon", "Corazón", ("resting_hr", "bp_sys", "bp_dia")),
    ("sueno", "Sueño", ("sleep_h",)),
    ("cuerpo", "Composición corporal", ("bmi", "body_fat_pct")),
    ("signos", "Signos vitales", ("spo2", "resp_rate", "temp_c")),
    ("metabolismo", "Metabolismo", ("glucose",)),
)


def longevity(store: HealthStore, now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Seven areas over the last 30 days, each against public guidance."""
    now = now or time.time()
    areas = []
    for key, label, metrics in LONGEVITY_AREAS:
        checks = []
        for metric in metrics:
            series = store.daily(metric, days=BASELINE_DAYS, now=now)
            if not series:
                continue
            m = BY_KEY[metric]
            avg = sum(series.values()) / len(series)
            status = classify(m, avg)
            if not status:
                continue
            checks.append(
                {
                    "metric": metric,
                    "label": m.label,
                    "value": _round(metric, avg),
                    "unit": m.unit,
                    "status": status,
                    "guide": m.guide,
                    "days": len(series),
                }
            )
        if not checks:
            state = "sin_datos"
        elif all(c["status"] == "ok" for c in checks):
            state = "en_rango"
        else:
            state = "atencion"
        areas.append({"key": key, "label": label, "state": state, "checks": checks})
    return areas


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _shift(day: str, n: int) -> str:
    return (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def correlations(
    store: HealthStore,
    target: str = "sleep_h",
    days: int = 90,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """What goes with a better or worse ``target`` the same (or next) day.

    Metrics: Pearson correlation of the day's value with the target that night.
    Tags: the target's mean on tagged days vs untagged days. Only pairs with at
    least MIN_DAYS_FOR_CORRELATION days are reported.
    """
    if target not in BY_KEY:
        raise ValueError("Métrica desconocida.")
    now = now or time.time()
    goal = store.daily(target, days=days, now=now)
    found = []
    for metric in store.metrics_with_data():
        if metric == target or metric not in BY_KEY:
            continue
        series = store.daily(metric, days=days, now=now)
        # sleep logged on day D is the night after the activities of day D-1
        lag = 1 if BY_KEY[target].category == "sueno" else 0
        pairs = [
            (v, goal[_shift(d, lag)])
            for d, v in series.items()
            if _shift(d, lag) in goal
        ]
        if len(pairs) < MIN_DAYS_FOR_CORRELATION:
            continue
        r = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
        if r is None or abs(r) < 0.3:
            continue
        found.append(
            {
                "kind": "metric",
                "metric": metric,
                "label": BY_KEY[metric].label,
                "r": round(r, 2),
                "days": len(pairs),
            }
        )
    notes = store.notes(days)
    tags = sorted({t for n in notes.values() for t in n["tags"]})
    lag = 1 if BY_KEY[target].category == "sueno" else 0
    for tag in tags:
        with_tag = [
            goal[_shift(d, lag)]
            for d, n in notes.items()
            if tag in n["tags"] and _shift(d, lag) in goal
        ]
        tagged_days = {d for d, n in notes.items() if tag in n["tags"]}
        without = [v for d, v in goal.items() if _shift(d, -lag) not in tagged_days]
        if (
            len(with_tag) < 3
            or len(without) < 3
            or len(with_tag) + len(without) < MIN_DAYS_FOR_CORRELATION
        ):
            continue
        a, b = sum(with_tag) / len(with_tag), sum(without) / len(without)
        if not b or abs(a - b) / abs(b) < 0.05:
            continue
        found.append(
            {
                "kind": "tag",
                "tag": tag,
                "label": f"Días con «{tag}»",
                "with": _round(target, a),
                "without": _round(target, b),
                "days": len(with_tag),
            }
        )
    found.sort(
        key=lambda f: (
            -(abs(f.get("r", 0)) or abs((f.get("with") or 0) - (f.get("without") or 0)))
        )
    )
    return {
        "target": target,
        "label": BY_KEY[target].label,
        "found": found[:8],
        "min_days": MIN_DAYS_FOR_CORRELATION,
    }


def known_facts(store: HealthStore, now: Optional[float] = None) -> str:
    """The owner's real recent data as one paragraph, for the coach."""
    lines = []
    for metric, s in overview(store, now)["metrics"].items():
        m = BY_KEY[metric]
        base = f" (media 30 días {s['baseline']})" if s["baseline"] is not None else ""
        lines.append(f"{m.label}: {s['value']} {m.unit} el {s['day']}{base}")
    return "; ".join(lines)


__all__ = [
    "LONGEVITY_AREAS",
    "correlations",
    "highlights",
    "known_facts",
    "longevity",
    "metric_summary",
    "overview",
    "readiness",
]

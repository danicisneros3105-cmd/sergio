"""Health: questionnaire, daily log, your watch's data, metrics, the report.

* **Questionnaire** once (and whenever you want): age, height, weight,
  activity, sleep, food, habits, stress, conditions, goals, sexual health
  (optional, private).
* **Watch data**: Apple Health (export.zip / export.xml from the iPhone's
  Salud app, or an auto-export app), Garmin Connect, Google Fit / Health
  Connect, Samsung Health, Fitbit, Polar, Amazfit... as CSV exports. Put
  them in the «sync folder» (e.g. a folder your phone syncs to) and Sergio
  imports new files every day.
* **Daily log** at the time you chose: only what no device gave today
  (steps, sleep, resting pulse, mood, energy, stress, water, exercise).
* **Metrics** computed here (BMI, basal metabolism, daily energy, heart
  zones, 7/30-day averages and trends) and the coach's **report**
  (strengths, what to improve, alerts, 3-5 actions, a weekly routine).

All of it lives encrypted on this PC (``secure``).
"""

from __future__ import annotations

import csv
import io
import re
import threading
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from sergio_escritorio import secure


@dataclass(frozen=True)
class Question:
    key: str
    text: str
    kind: str  # number | choice | text
    options: tuple[str, ...] = ()
    unit: str = ""
    optional: bool = False
    private: bool = False


QUESTIONS: tuple[Question, ...] = (
    Question("edad", "¿Cuántos años tiene?", "number", unit="años"),
    Question("sexo", "Sexo biológico (para las fórmulas)", "choice", ("hombre", "mujer", "prefiero no decir")),
    Question("altura_cm", "Altura", "number", unit="cm"),
    Question("peso_kg", "Peso", "number", unit="kg"),
    Question("cintura_cm", "Perímetro de cintura (opcional)", "number", unit="cm", optional=True),
    Question("actividad", "Actividad física habitual", "choice", ("sedentario", "ligera", "moderada", "alta", "muy alta")),
    Question("ejercicio", "¿Qué ejercicio hace y cuántos días por semana?", "text", optional=True),
    Question("sueno_h", "Horas de sueño por noche", "number", unit="h"),
    Question("sueno_calidad", "Calidad del sueño (1 mala - 5 excelente)", "choice", ("1", "2", "3", "4", "5")),
    Question("dieta", "¿Cómo come normalmente? (comidas, verduras, comida rápida…)", "text", optional=True),
    Question("agua_l", "Agua al día", "number", unit="litros", optional=True),
    Question("alcohol", "Bebidas alcohólicas por semana", "number", unit="bebidas", optional=True),
    Question("tabaco", "¿Fuma o vapea?", "choice", ("no", "a veces", "a diario"), optional=True),
    Question("cafeina", "Cafés o bebidas con cafeína al día", "number", optional=True),
    Question("estres", "Estrés habitual (1 bajo - 5 muy alto)", "choice", ("1", "2", "3", "4", "5")),
    Question("animo", "Ánimo habitual (1 muy bajo - 5 muy bueno)", "choice", ("1", "2", "3", "4", "5")),
    Question("condiciones", "Condiciones médicas, lesiones o dolores", "text", optional=True),
    Question("medicacion", "Medicamentos que toma", "text", optional=True),
    Question("alergias", "Alergias", "text", optional=True),
    Question("objetivos", "¿Qué quiere lograr con su salud?", "text"),
    Question("sexual_activa", "Vida sexual activa (privado, opcional)", "choice", ("sí", "no", "prefiero no decir"), optional=True, private=True),
    Question("sexual_notas", "Algo que le preocupe de su salud sexual (privado, opcional)", "text", optional=True, private=True),
    Question("chequeo", "Último chequeo médico (año aproximado)", "text", optional=True),
)
DAILY: tuple[tuple[str, str, str], ...] = (
    ("pasos", "Pasos", "pasos"),
    ("sueno_h", "Horas que durmió anoche", "h"),
    ("fc_reposo", "Pulso en reposo", "lpm"),
    ("animo", "Ánimo hoy (1-5)", ""),
    ("energia", "Energía hoy (1-5)", ""),
    ("estres", "Estrés hoy (1-5)", ""),
    ("agua_l", "Agua", "litros"),
    ("ejercicio_min", "Minutos de ejercicio", "min"),
    ("peso_kg", "Peso (opcional)", "kg"),
)
FROM_DEVICES = {"pasos", "sueno_h", "fc_reposo", "ejercicio_min", "peso_kg", "hrv_ms", "calorias_activas"}
ACTIVITY_FACTOR = {"sedentario": 1.2, "ligera": 1.375, "moderada": 1.55, "alta": 1.725, "muy alta": 1.9}


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def _num(value: Any) -> float | None:
    try:
        text = str(value).strip().replace(",", ".")
        text = re.sub(r"[^\d.\-]", "", text)
        return float(text) if text not in ("", ".", "-") else None
    except ValueError:
        return None


# -- importing device data ---------------------------------------------------------------
APPLE_TYPES = {
    "HKQuantityTypeIdentifierStepCount": ("pasos", "sum"),
    "HKQuantityTypeIdentifierRestingHeartRate": ("fc_reposo", "mean"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv_ms", "mean"),
    "HKQuantityTypeIdentifierBodyMass": ("peso_kg", "last"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("calorias_activas", "sum"),
    "HKQuantityTypeIdentifierAppleExerciseTime": ("ejercicio_min", "sum"),
}
SLEEP_ASLEEP = ("Asleep", "AsleepCore", "AsleepDeep", "AsleepREM", "AsleepUnspecified")


def _day(text: str) -> str:
    return str(text).strip()[:10]


def parse_apple_health(xml: bytes | io.IOBase) -> dict[str, dict[str, float]]:
    """Apple Health export.xml -> {day: {metric: value}} (streamed: exports are big)."""
    import xml.etree.ElementTree as ET

    source = io.BytesIO(xml) if isinstance(xml, (bytes, bytearray)) else xml
    acc: dict[str, dict[str, list[float]]] = {}
    sleep: dict[str, float] = {}
    for _event, el in ET.iterparse(source, events=("end",)):
        if el.tag != "Record":
            el.clear()
            continue
        kind = el.get("type", "")
        if kind in APPLE_TYPES:
            metric, _how = APPLE_TYPES[kind]
            value = _num(el.get("value"))
            if value is not None:
                if metric == "peso_kg" and el.get("unit") == "lb":
                    value *= 0.4536
                acc.setdefault(_day(el.get("startDate", "")), {}).setdefault(metric, []).append(value)
        elif kind == "HKCategoryTypeIdentifierSleepAnalysis" and any(el.get("value", "").endswith(s) for s in SLEEP_ASLEEP):
            try:
                start = datetime.fromisoformat(el.get("startDate", "")[:19])
                end = datetime.fromisoformat(el.get("endDate", "")[:19])
                hours = (end - start).total_seconds() / 3600
                wake = end.date().isoformat()  # a night counts for the day you woke up
                sleep[wake] = sleep.get(wake, 0.0) + max(0.0, hours)
            except ValueError:
                pass
        el.clear()
    out: dict[str, dict[str, float]] = {}
    for day, metrics in acc.items():
        for metric, values in metrics.items():
            how = next(h for m, h in APPLE_TYPES.values() if m == metric)
            value = sum(values) if how == "sum" else values[-1] if how == "last" else sum(values) / len(values)
            out.setdefault(day, {})[metric] = round(value, 1)
    for day, hours in sleep.items():
        out.setdefault(day, {})["sueno_h"] = round(min(hours, 16.0), 2)
    return out


# Column names in the CSV exports of Garmin, Google Fit, Samsung Health,
# Fitbit, Polar, Amazfit... (lower case, no accents) -> our metrics.
CSV_COLUMNS = {
    "pasos": ("steps", "step count", "total steps", "pasos", "step_count", "count", "daily steps"),
    "sueno_h": ("sleep hours", "sleep (h)", "hours asleep", "horas de sueno", "sleep duration (h)", "total sleep (h)"),
    "sueno_min": ("minutes asleep", "sleep minutes", "sleep duration (min)", "total sleep (min)", "minutos de sueno", "sleep time"),
    "fc_reposo": ("resting heart rate", "resting hr", "rhr", "frecuencia cardiaca en reposo", "resting heart rate (bpm)", "pulso en reposo"),
    "hrv_ms": ("hrv", "hrv (ms)", "heart rate variability", "avg hrv", "overnight hrv", "rmssd"),
    "peso_kg": ("weight", "weight (kg)", "peso", "body weight", "peso (kg)"),
    "calorias_activas": ("active calories", "calories burned", "active energy", "calorias activas", "calories (kcal)"),
    "ejercicio_min": ("active minutes", "exercise minutes", "move minutes count", "minutos activos", "intensity minutes", "very active minutes"),
    "estres": ("stress", "avg stress", "stress level", "estres"),
}
DATE_COLUMNS = ("date", "day", "fecha", "calendar date", "start date", "start time", "timestamp", "dia")


def _parse_date(text: str) -> str | None:
    text = str(text).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[: len(datetime(2000, 1, 1).strftime(fmt))], fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else None


def parse_csv(text: str, day_hint: str = "") -> dict[str, dict[str, float]]:
    """Any daily CSV export with a date column and known metric columns.

    Google Fit's «Daily activity metrics» files have no date column but the
    date in the file name: pass it as *day_hint*."""
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    if not rows:
        return {}
    columns = {_plain(c): c for c in rows[0].keys() if c}
    date_col = next((columns[c] for c in columns if c in DATE_COLUMNS), None)
    found = {}
    for metric, names in CSV_COLUMNS.items():
        col = next((columns[n] for n in names if n in columns), None)
        if col is not None:
            found[metric] = col
    if not found:
        return {}
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        day = _parse_date(row.get(date_col, "")) if date_col else None
        from_hint = day is None and bool(day_hint)
        day = day or day_hint or None
        if not day:
            continue
        for metric, col in found.items():
            value = _num(row.get(col))
            if value is None:
                continue
            target = out.setdefault(day, {})
            if metric == "sueno_min":
                target["sueno_h"] = round(target.get("sueno_h", 0.0) + value / 60, 2)
            elif metric in ("pasos", "calorias_activas", "ejercicio_min") and from_hint:
                target[metric] = target.get(metric, 0.0) + value  # rows are intervals of one day
            else:
                target[metric] = value
    return out


def parse_file(name: str, data: bytes) -> dict[str, dict[str, float]]:
    """A file from a watch app (zip, xml or csv) -> daily metrics."""
    low = name.lower()
    if low.endswith(".zip"):
        merged: dict[str, dict[str, float]] = {}
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for inner in z.namelist():
                if inner.lower().endswith(("export.xml", ".csv")) and "cda" not in inner.lower():
                    for day, values in parse_file(inner, z.read(inner)).items():
                        merged.setdefault(day, {}).update(values)
        return merged
    if low.endswith(".xml"):
        return parse_apple_health(data)
    if low.endswith(".csv"):
        hint = _parse_date(re.search(r"\d{4}-\d{2}-\d{2}", Path(name).name).group(0)) if re.search(r"\d{4}-\d{2}-\d{2}", Path(name).name) else ""
        for encoding in ("utf-8-sig", "latin-1"):
            try:
                return parse_csv(data.decode(encoding), hint or "")
            except UnicodeDecodeError:
                continue
    return {}


# -- metrics ------------------------------------------------------------------------------------
def body_metrics(q: dict[str, Any]) -> dict[str, Any]:
    """BMI, basal metabolism (Mifflin-St Jeor), daily energy, max heart rate
    (Tanaka) and zone 2, from the questionnaire."""
    out: dict[str, Any] = {}
    h, w, age = _num(q.get("altura_cm")), _num(q.get("peso_kg")), _num(q.get("edad"))
    if h and w:
        bmi = w / (h / 100) ** 2
        out["imc"] = round(bmi, 1)
        out["imc_categoria"] = "bajo peso" if bmi < 18.5 else "normal" if bmi < 25 else "sobrepeso" if bmi < 30 else "obesidad"
    if h and w and age:
        sex = _plain(q.get("sexo", ""))
        bmr = 10 * w + 6.25 * h - 5 * age + (5 if sex == "hombre" else -161 if sex == "mujer" else -78)
        out["metabolismo_basal"] = round(bmr)
        out["gasto_diario"] = round(bmr * ACTIVITY_FACTOR.get(_plain(q.get("actividad", "")), 1.375))
        out["proteina_g"] = [round(w * 1.2), round(w * 1.6)]
        out["agua_l"] = round(w * 0.033, 1)
    if age:
        hr_max = 208 - 0.7 * age
        out["fc_max"] = round(hr_max)
        out["zona2"] = [round(hr_max * 0.6), round(hr_max * 0.7)]
    waist = _num(q.get("cintura_cm"))
    if waist:
        limit = 94 if _plain(q.get("sexo", "")) == "hombre" else 80
        out["cintura_riesgo"] = waist > limit
    return out


def trends(days: dict[str, dict[str, float]], today: date) -> dict[str, Any]:
    """7- and 30-day averages per metric, and the change between the two."""
    out: dict[str, Any] = {}
    metrics = {m for v in days.values() for m in v}
    for metric in sorted(metrics):
        def mean(span: int, metric: str = metric) -> float | None:
            vals = [days[d][metric] for d in days if metric in days[d] and 0 <= (today - date.fromisoformat(d)).days < span]
            return round(sum(vals) / len(vals), 1) if vals else None

        week, month = mean(7), mean(30)
        if week is not None or month is not None:
            out[metric] = {"7d": week, "30d": month, "cambio": round(week - month, 1) if week is not None and month is not None else None}
    return out


class Health:
    """Your health data (encrypted) and what is computed from it."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.RLock()
        data = secure.read_json(path, {}) if path is not None else {}
        data = data if isinstance(data, dict) else {}
        self.answers: dict[str, Any] = dict(data.get("cuestionario") or {})
        self.days: dict[str, dict[str, float]] = {k: dict(v) for k, v in (data.get("dias") or {}).items()}
        self.report: dict[str, Any] = dict(data.get("informe") or {})
        self.imported: dict[str, float] = dict(data.get("importados") or {})  # file -> mtime
        self.sources: list[str] = list(data.get("fuentes") or [])
        # Free-form medical timeline entries stay inside the same DPAPI-sealed file.
        saved_history = data.get("historial_medico", [])
        if not isinstance(saved_history, list):
            saved_history = []
        self.medical_history: list[dict[str, str]] = [
            item for item in saved_history
            if isinstance(item, dict)
            and all(isinstance(item.get(key), str) for key in ("id", "fecha", "tipo", "nota"))
        ]

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            payload = {
                "cuestionario": self.answers, "dias": self.days, "informe": self.report,
                "importados": self.imported, "fuentes": self.sources,
                "historial_medico": self.medical_history,
            }  # fmt: skip
            secure.write_json(self.path, payload)

    # questionnaire and log
    def answer(self, answers: dict[str, Any]) -> None:
        keys = {q.key for q in QUESTIONS}
        self.answers.update({k: v for k, v in answers.items() if k in keys and str(v).strip() != ""})
        self.save()

    def add_medical_record(self, day: str, kind: str, note: str) -> dict[str, str]:
        """Save one dated health record locally; reject malformed or oversized data."""
        parsed = date.fromisoformat(str(day))
        if parsed > date.today():
            raise ValueError("La fecha del registro no puede estar en el futuro")
        kind = str(kind).strip().lower()
        if kind not in {"consulta", "diagnóstico", "medicación", "alergia", "procedimiento", "resultado", "nota"}:
            raise ValueError("Tipo de registro médico no válido")
        note = str(note).strip()
        if not note:
            raise ValueError("Escriba una nota antes de guardarla")
        if len(note) > 5000:
            raise ValueError("La nota supera el límite de 5000 caracteres")
        record = {"id": uuid.uuid4().hex, "fecha": parsed.isoformat(), "tipo": kind, "nota": note}
        with self._lock:
            self.medical_history.append(record)
            try:
                self.save()
            except OSError:
                self.medical_history.pop()
                raise
        return record

    def missing_questions(self) -> list[Question]:
        return [q for q in QUESTIONS if not q.optional and q.key not in self.answers]

    def log(self, day: str, values: dict[str, Any], source: str = "manual") -> None:
        clean = {k: v for k, v in ((k, _num(v)) for k, v in values.items()) if v is not None}
        if clean:
            self.days.setdefault(day, {}).update(clean)
            if source != "manual" and source not in self.sources:
                self.sources.append(source)
            self.save()

    def to_ask_today(self, today: str) -> list[tuple[str, str, str]]:
        """Daily fields still empty today (what a device gave is not asked)."""
        have = self.days.get(today, {})
        return [f for f in DAILY if f[0] not in have]

    # devices
    def import_file(self, path: Path) -> int:
        """Import one export file; returns how many days it brought."""
        found = parse_file(path.name, path.read_bytes())
        for day, values in found.items():
            self.days.setdefault(day, {}).update(values)
        if found:
            self.imported[str(path)] = path.stat().st_mtime
            name = "Apple Salud" if path.suffix.lower() in (".xml", ".zip") else "reloj (CSV)"
            if name not in self.sources:
                self.sources.append(name)
            self.save()
        return len(found)

    def sync_folder(self, folder: Path) -> int:
        """Import every new or changed export in the sync folder."""
        if not folder.is_dir():
            return 0
        total = 0
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() in (".zip", ".xml", ".csv") and path.is_file():
                if self.imported.get(str(path)) != path.stat().st_mtime:
                    try:
                        total += self.import_file(path)
                    except Exception:  # noqa: BLE001 — one bad file never stops the rest
                        continue
        return total

    # analysis
    def overview(self, today: date | None = None, facts: Iterable[str] = ()) -> dict[str, Any]:
        """Everything the coach looks at for the report (private answers included
        only as given; nothing leaves the PC except for this report)."""
        today = today or date.today()
        recent = {d: v for d, v in self.days.items() if 0 <= (today - date.fromisoformat(d)).days < 30}
        return {
            "cuestionario": self.answers,
            "metricas": body_metrics(self.answers),
            "tendencias": trends(self.days, today),
            "ultimos_30_dias": recent,
            "fuentes": self.sources,
            "lo_que_conto": [f for f in facts][-30:],
        }

    def summary_for_profile(self) -> dict[str, Any]:
        rep = self.report
        return {"resumen": str(rep.get("resumen", ""))[:400], "metas": rep.get("metas", [])[:3]} if rep else {}

    def describe(self) -> str:
        if not self.answers:
            return "Aún no tengo su perfil de salud. Diga «hagamos el cuestionario de salud» y empezamos."
        m = body_metrics(self.answers)
        parts = []
        if "imc" in m:
            parts.append(f"IMC {m['imc']} ({m['imc_categoria']})")
        if "gasto_diario" in m:
            parts.append(f"gasta unas {m['gasto_diario']} kcal al día")
        t = trends(self.days, date.today())
        if t.get("pasos", {}).get("7d"):
            parts.append(f"{t['pasos']['7d']:.0f} pasos de media esta semana")
        if t.get("sueno_h", {}).get("7d"):
            parts.append(f"duerme {t['sueno_h']['7d']} h")
        head = ", ".join(parts) + "." if parts else ""
        return (head + " " + str(self.report.get("resumen", ""))).strip()


_SPOKEN = (
    (r"\bdorm[ií]\w*\s+(?:unas?\s+)?(\d+(?:[.,]\d+)?)\s*(?:h|horas?)", "sueno_h"),
    (r"(\d[\d.,]*)\s*pasos\b", "pasos"),
    (r"\b(?:pulso|frecuencia(?: card[ií]aca)?)(?: en reposo)?(?: (?:de|es|est[aá] en))?\s*(\d+)", "fc_reposo"),
    (r"\b(?:peso|pes[eé]|estoy en)\s*(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?)", "peso_kg"),
    (r"\b(?:beb[ií]|tom[eé])\s*(\d+(?:[.,]\d+)?)\s*(?:l|litros?)\s*de agua", "agua_l"),
    (r"\b(?:hice|entren[eé]|corr[ií]|camin[eé])\s*(\d+)\s*min(?:utos)?", "ejercicio_min"),
    (r"\b(?:mi )?[aá]nimo\s*(?:es|est[aá]|de|en)?\s*([1-5])\b", "animo"),
    (r"\b(?:mi )?energ[ií]a\s*(?:es|est[aá]|de|en)?\s*([1-5])\b", "energia"),
    (r"\b(?:mi )?estr[eé]s\s*(?:es|est[aá]|de|en)?\s*([1-5])\b", "estres"),
)


def parse_health_log(text: str) -> dict[str, float]:
    """Numbers said in passing: "hoy dormí 6 horas y caminé 8.000 pasos"."""
    t = text.lower()
    out = {}
    for pattern, key in _SPOKEN:
        m = re.search(pattern, t)
        if m:
            raw = m.group(1)
            value = float(raw.replace(".", "").replace(",", "")) if key == "pasos" else _num(raw)
            if value is not None:
                out[key] = value
    return out


def daily_time(config_value: str | None, usual: list[str]) -> tuple[int, int]:
    """When to ask the daily log: what you chose, else the end of your usual
    evening at the PC, else 21:30."""
    if config_value and re.fullmatch(r"\d{1,2}:\d{2}", config_value.strip()):
        h, m = config_value.strip().split(":")
        return int(h) % 24, int(m) % 60
    evenings = []
    for window in usual:
        m = re.search(r"(\d{2}):(\d{2})-(\d{2}):(\d{2})", window)
        if m and 17 <= int(m.group(1)) <= 23:
            evenings.append((int(m.group(3)), int(m.group(4))))
    if evenings:
        h, m = max(evenings)
        return (h - 1) % 24 if h else 21, m
    return 21, 30


__all__ = [
    "DAILY",
    "Health",
    "QUESTIONS",
    "Question",
    "body_metrics",
    "daily_time",
    "parse_apple_health",
    "parse_health_log",
    "parse_csv",
    "parse_file",
    "trends",
]

"""Bring data in from watches, rings, scales and phone apps.

Formats understood (all read on this computer):

* the phone's full health export (``export.zip`` or ``export.xml``);
* the JSON that phone automation apps send (a ``data.metrics`` list with
  ``name``, ``units`` and ``data`` points) — this is what the live sync link
  receives;
* Sergio's own JSON (``{"samples": [{"metric", "value", "at"}]}``);
* CSV: either one row per reading (``date, metric, value[, unit]``) or one
  column per metric (``date, steps, weight, …``) as most apps export.

Units are converted to the catalog's (lb → kg, mi → km, °F → °C, mmol/L →
mg/dL, fractions → %), so a value means the same whatever sent it.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from typing import Any, Iterator, List, Optional, Tuple
from xml.etree import ElementTree as ET

from openjarvis.health.metrics import resolve

Row = Tuple[str, float, Optional[float], str, str]  # metric, value, at, source, uid

_SLEEP_STAGES = {
    "hkcategoryvaluesleepanalysisasleep": "sleep_h",
    "hkcategoryvaluesleepanalysisasleepunspecified": "sleep_h",
    "hkcategoryvaluesleepanalysisasleepcore": "sleep_h",
    "hkcategoryvaluesleepanalysisasleepdeep": "sleep_deep_h",
    "hkcategoryvaluesleepanalysisasleeprem": "sleep_rem_h",
}


def parse_time(value: Any) -> Optional[float]:
    """Epoch seconds from the many ways apps write a time."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000 if value > 1e11 else float(value)
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ):
        try:
            dt = datetime.strptime(text.replace("Z", "+0000"), fmt)
            if fmt == "%Y-%m-%d" or fmt == "%d/%m/%Y":
                dt = dt.replace(hour=12)  # a day's total sits in the middle of the day
            return dt.timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def convert(metric: str, value: float, unit: str = "") -> float:
    """Into the catalog's unit."""
    u = (unit or "").strip().lower()
    if metric == "weight_kg" and u in ("lb", "lbs", "pound", "pounds"):
        return value * 0.45359237
    if metric == "distance_km":
        if u in ("mi", "mile", "miles"):
            return value * 1.609344
        if u in ("m", "meter", "meters"):
            return value / 1000
    if metric == "temp_c" and u in ("degf", "°f", "f", "fahrenheit"):
        return (value - 32) * 5 / 9
    if metric == "glucose" and u in ("mmol/l", "mmol<180.1558800000541>/l"):
        return value * 18.0
    if (
        metric in ("body_fat_pct", "spo2")
        and value <= 1.0
        and u in ("%", "", "count/%")
    ):
        return value * 100  # the phone stores 0.97 for 97 %
    if metric in ("active_kcal", "kcal_in") and u in ("kj", "kilojoule"):
        return value / 4.184
    if metric == "water_ml" and u in ("l", "liter", "litre"):
        return value * 1000
    if metric == "water_ml" and u in ("fl_oz_us", "floz", "oz"):
        return value * 29.5735
    if metric in ("sleep_h", "sleep_deep_h", "sleep_rem_h") and u in ("min", "minutes"):
        return value / 60
    if metric in ("sleep_h", "sleep_deep_h", "sleep_rem_h") and u in (
        "s",
        "sec",
        "seconds",
    ):
        return value / 3600
    return value


# -- the phone's full export -------------------------------------------------------
def from_phone_export(data: bytes, source: str = "telefono") -> Iterator[Row]:
    """``export.zip`` (or the ``export.xml`` inside it), streamed so a file of
    several hundred megabytes does not fill the memory."""
    stream: io.IOBase
    if data[:2] == b"PK":
        archive = zipfile.ZipFile(io.BytesIO(data))
        name = next((n for n in archive.namelist() if n.endswith("export.xml")), None)
        if not name:
            raise ValueError("El archivo .zip no trae export.xml.")
        stream = archive.open(name)
    else:
        stream = io.BytesIO(data)
    for _event, el in ET.iterparse(stream, events=("end",)):
        if el.tag != "Record":
            if el.tag not in ("HealthData",):
                el.clear()
            continue
        kind = el.get("type", "")
        start = parse_time(el.get("startDate"))
        uid_base = (
            f"{kind}|{el.get('startDate')}|{el.get('value')}|{el.get('sourceName', '')}"
        )
        if kind == "HKCategoryTypeIdentifierSleepAnalysis":
            metric = _SLEEP_STAGES.get((el.get("value") or "").lower())
            end = parse_time(el.get("endDate"))
            if metric and start and end and end > start:
                hours = (end - start) / 3600
                yield (metric, hours, end, source, f"x|{uid_base}")
                if metric != "sleep_h":  # deep and REM are also sleep
                    yield ("sleep_h", hours, end, source, f"x|{uid_base}|total")
        elif kind == "HKCategoryTypeIdentifierMindfulSession":
            end = parse_time(el.get("endDate"))
            if start and end and end > start:
                yield ("mindful_min", (end - start) / 60, end, source, f"x|{uid_base}")
        else:
            metric = resolve(kind)
            try:
                value = float(el.get("value", ""))
            except ValueError:
                value = None
            if metric and value is not None:
                yield (
                    metric,
                    convert(metric, value, el.get("unit", "")),
                    start,
                    source,
                    f"x|{uid_base}",
                )
        el.clear()


# -- JSON from phone automation apps and from Sergio -------------------------------
def from_json(payload: Any, source: str = "sincronizacion") -> Iterator[Row]:
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("JSON no reconocido.")
    for item in payload.get("samples", []) or []:
        metric = resolve(str(item.get("metric", "")))
        if not metric:
            continue
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        yield (
            metric,
            convert(metric, value, str(item.get("unit", ""))),
            parse_time(item.get("at") or item.get("date")),
            str(item.get("source") or source),
            str(item.get("id") or ""),
        )
    data = payload.get("data")
    metrics = data.get("metrics") if isinstance(data, dict) else None
    for block in metrics or []:
        name = str(block.get("name", ""))
        units = str(block.get("units", ""))
        for point in block.get("data", []) or []:
            at = parse_time(
                point.get("date") or point.get("sleepEnd") or point.get("endDate")
            )
            if name.lower() in ("sleep_analysis", "sleep"):
                total = point.get("totalSleep", point.get("asleep"))
                for metric, value in (
                    ("sleep_h", total),
                    ("sleep_deep_h", point.get("deep")),
                    ("sleep_rem_h", point.get("rem")),
                ):
                    if value not in (None, ""):
                        yield (
                            metric,
                            convert(metric, float(value), units),
                            at,
                            source,
                            f"j|{name}|{metric}|{point.get('date')}",
                        )
                continue
            if name.lower() == "blood_pressure":
                for key, metric in (("systolic", "bp_sys"), ("diastolic", "bp_dia")):
                    if point.get(key) not in (None, ""):
                        yield (
                            metric,
                            float(point[key]),
                            at,
                            source,
                            f"j|{name}|{key}|{point.get('date')}",
                        )
                continue
            metric = resolve(name)
            value = point.get("qty", point.get("Avg", point.get("avg")))
            if not metric or value in (None, ""):
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            yield (
                metric,
                convert(metric, value, units),
                at,
                source,
                f"j|{name}|{point.get('date')}|{value}",
            )


# -- CSV ---------------------------------------------------------------------------
_DATE_COLUMNS = (
    "date",
    "fecha",
    "time",
    "timestamp",
    "day",
    "dia",
    "día",
    "start",
    "startdate",
    "date/time",
)


def from_csv(data: bytes, source: str = "archivo") -> Iterator[Row]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return
    fields = {f.strip().lower(): f for f in reader.fieldnames if f}
    date_col = next((fields[c] for c in _DATE_COLUMNS if c in fields), None)
    if not date_col:
        raise ValueError("El CSV necesita una columna de fecha (date, fecha…).")
    long_form = "metric" in fields and "value" in fields
    wide: List[Tuple[str, str, str]] = []
    if not long_form:
        for low, original in fields.items():
            name, _, unit = low.partition("(")
            metric = resolve(name.strip())
            if metric:
                wide.append((original, metric, unit.rstrip(")").strip()))
        if not wide:
            raise ValueError("No reconocí ninguna medida en las columnas del CSV.")
    for i, row in enumerate(reader):
        at = parse_time(row.get(date_col))
        if at is None:
            continue
        if long_form:
            metric = resolve(row.get(fields["metric"]) or "")
            raw = (row.get(fields["value"]) or "").replace(",", ".")
            unit = row.get(fields["unit"], "") if "unit" in fields else ""
            if metric and raw:
                try:
                    yield (
                        metric,
                        convert(metric, float(raw), unit or ""),
                        at,
                        source,
                        f"c|{source}|{metric}|{at}|{raw}",
                    )
                except ValueError:
                    continue
            continue
        for column, metric, unit in wide:
            raw = (row.get(column) or "").strip().replace(",", ".")
            if not raw:
                continue
            try:
                yield (
                    metric,
                    convert(metric, float(raw), unit),
                    at,
                    source,
                    f"c|{source}|{metric}|{at}|{raw}",
                )
            except ValueError:
                continue


def detect_and_parse(name: str, data: bytes, source: str = "") -> Iterator[Row]:
    """Pick the reader from the file name and content."""
    low = (name or "").lower()
    if low.endswith(".zip") or low.endswith(".xml") or data[:5] == b"<?xml":
        return from_phone_export(data, source or "telefono")
    if low.endswith(".json") or data.lstrip()[:1] in (b"{", b"["):
        return from_json(data, source or "archivo")
    return from_csv(data, source or "archivo")


__all__ = [
    "convert",
    "detect_and_parse",
    "from_csv",
    "from_json",
    "from_phone_export",
    "parse_time",
]

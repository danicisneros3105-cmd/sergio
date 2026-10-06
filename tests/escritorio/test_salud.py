"""Health: questionnaire, watch imports, daily log, metrics, private storage."""

from __future__ import annotations

import io
import zipfile
from datetime import date

from sergio_escritorio import secure
from sergio_escritorio.salud import Health, body_metrics, daily_time, parse_apple_health, parse_file, parse_health_log, trends

APPLE = b"""<?xml version="1.0"?>
<HealthData>
 <Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="3000" startDate="2026-10-04 09:00:00 -0500" endDate="2026-10-04 10:00:00 -0500"/>
 <Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="4500" startDate="2026-10-04 18:00:00 -0500" endDate="2026-10-04 19:00:00 -0500"/>
 <Record type="HKQuantityTypeIdentifierRestingHeartRate" unit="count/min" value="58" startDate="2026-10-04 07:00:00 -0500" endDate="2026-10-04 07:00:00 -0500"/>
 <Record type="HKQuantityTypeIdentifierBodyMass" unit="lb" value="160" startDate="2026-10-04 07:00:00 -0500" endDate="2026-10-04 07:00:00 -0500"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepCore" startDate="2026-10-03 23:30:00 -0500" endDate="2026-10-04 04:30:00 -0500"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisAsleepDeep" startDate="2026-10-04 04:30:00 -0500" endDate="2026-10-04 06:30:00 -0500"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" value="HKCategoryValueSleepAnalysisInBed" startDate="2026-10-03 23:00:00 -0500" endDate="2026-10-04 07:00:00 -0500"/>
</HealthData>"""


def test_apple_health_export_becomes_days():
    days = parse_apple_health(APPLE)
    d = days["2026-10-04"]
    assert d["pasos"] == 7500 and d["fc_reposo"] == 58 and d["sueno_h"] == 7.0
    assert abs(d["peso_kg"] - 72.6) < 0.1  # pounds -> kg
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("apple_health_export/export.xml", APPLE)
    assert parse_file("export.zip", buf.getvalue())["2026-10-04"]["pasos"] == 7500


def test_csv_exports_from_other_watches():
    garmin = "Date,Steps,Resting Heart Rate,Avg Stress\n2026-10-03,9120,61,32\n2026-10-04,6400,63,40\n"
    days = parse_file("garmin.csv", garmin.encode())
    assert days["2026-10-03"] == {"pasos": 9120, "fc_reposo": 61, "estres": 32}
    google_fit = "Start time,End time,Step count,Move Minutes count\n00:00:00.000-05:00,00:15:00.000-05:00,120,3\n08:00:00.000-05:00,08:15:00.000-05:00,900,10\n"
    days = parse_file("Fit/Daily activity metrics/2026-10-04.csv", google_fit.encode())
    assert days == {"2026-10-04": {"pasos": 1020, "ejercicio_min": 13}}
    samsung = "fecha;pasos;minutos de sueno\n04/10/2026;5000;420\n"
    assert parse_file("samsung.csv", samsung.encode())["2026-10-04"] == {"pasos": 5000, "sueno_h": 7.0}
    assert parse_file("otra.csv", b"a,b\n1,2\n") == {}


def test_body_metrics_follow_the_formulas():
    m = body_metrics({"edad": "30", "sexo": "hombre", "altura_cm": "178", "peso_kg": "75", "actividad": "moderada", "cintura_cm": "96"})
    assert m["imc"] == 23.7 and m["imc_categoria"] == "normal"
    assert m["metabolismo_basal"] == round(10 * 75 + 6.25 * 178 - 5 * 30 + 5)
    assert m["gasto_diario"] == round((10 * 75 + 6.25 * 178 - 5 * 30 + 5) * 1.55)
    assert m["fc_max"] == 187 and m["zona2"] == [112, 131] and m["cintura_riesgo"]


def test_trends_and_spoken_log():
    days = {"2026-10-05": {"pasos": 10000}, "2026-10-01": {"pasos": 8000}, "2026-09-20": {"pasos": 2000}}
    t = trends(days, date(2026, 10, 5))
    assert t["pasos"]["7d"] == 9000 and t["pasos"]["30d"] == round(20000 / 3, 1)
    assert parse_health_log("hoy dormí 6 horas y caminé 8.000 pasos") == {"sueno_h": 6.0, "pasos": 8000.0}
    assert parse_health_log("mi ánimo es 2") == {"animo": 2.0}


def test_health_is_private_and_asks_only_what_is_missing(tmp_path):
    h = Health(tmp_path / "salud.json")
    h.answer({"edad": "30", "objetivos": "dormir mejor", "inventado": "x"})
    assert "inventado" not in h.answers and h.missing_questions()
    today = date.today().isoformat()
    h.log(today, {"pasos": "8.000", "animo": "4", "vacio": ""}, source="Garmin")
    asked = [k for k, _l, _u in h.to_ask_today(today)]
    assert "pasos" not in asked and "animo" not in asked and "sueno_h" in asked
    raw = (tmp_path / "salud.json").read_bytes()
    assert raw.startswith(secure.PLAIN if not secure.available() else secure.MAGIC)
    again = Health(tmp_path / "salud.json")
    assert again.answers["edad"] == "30" and "Garmin" in again.sources
    over = again.overview(facts=["me duele la rodilla"])
    assert over["lo_que_conto"] == ["me duele la rodilla"] and today in over["ultimos_30_dias"]


def test_sync_folder_imports_new_files_once(tmp_path):
    folder = tmp_path / "sync"
    folder.mkdir()
    (folder / "garmin.csv").write_text("Date,Steps\n2026-10-04,5000\n")
    h = Health(tmp_path / "s.json")
    assert h.sync_folder(folder) == 1 and h.sync_folder(folder) == 0
    assert h.days["2026-10-04"]["pasos"] == 5000


def test_daily_time_prefers_your_choice_then_your_evening():
    assert daily_time("22:15", []) == (22, 15)
    assert daily_time(None, ["lunes 19:00-21:00"]) == (20, 0)
    assert daily_time(None, []) == (21, 30)


def test_health_windows_draw(tmp_path):
    from PySide6.QtWidgets import QApplication

    from sergio_escritorio.salud_ui import DailyCard, HealthWindow, report_html

    _app = QApplication.instance() or QApplication([])
    h = Health(tmp_path / "s.json")
    h.answer({"edad": "30", "sexo": "hombre", "altura_cm": "178", "peso_kg": "75", "actividad": "moderada"})
    h.report = {"resumen": "Bien en general.", "alertas": ["Pulso alto en reposo"],
                "recomendaciones": [{"accion": "Caminar 30 min", "por_que": "OMS"}], "rutina": [{"dia": "lunes", "actividad": "fuerza", "minutos": 30}]}  # fmt: skip
    html = report_html(h)
    assert "IMC" in html and "Caminar 30 min" in html and "Consulte con un médico" in html
    w = HealthWindow(h, lambda: {}, lambda: "", lambda f: None)
    w.open(1)
    w.today_fields["pasos"].setText("7000")
    w._save_today()
    assert h.days[date.today().isoformat()]["pasos"] == 7000
    card = DailyCard(h, lambda: None)
    assert "pasos" not in card.fields
    for x in (w, card):
        x.close()

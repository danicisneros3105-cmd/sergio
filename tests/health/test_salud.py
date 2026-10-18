"""Salud: own data store, importers, insights, sync link and devices."""

from __future__ import annotations

import io
import json
import time
import zipfile
from datetime import datetime, timedelta

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.health import devices, importers, insights  # noqa: E402
from openjarvis.health.metrics import resolve  # noqa: E402
from openjarvis.health.store import HealthStore  # noqa: E402
from openjarvis.server import health_routes  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(health_routes, "_home", lambda: tmp_path)
    return tmp_path


@pytest.fixture()
def client(home):
    app = FastAPI()
    app.include_router(health_routes.router)
    return TestClient(app)


def _days_ago(n: int, hour: int = 12) -> float:
    return (datetime.now() - timedelta(days=n)).replace(hour=hour, minute=0).timestamp()


def test_names_from_any_app_map_to_one_metric():
    assert resolve("HKQuantityTypeIdentifierStepCount") == "steps"
    assert resolve("step_count") == "steps"
    assert resolve("heart_rate_variability") == "hrv"
    assert resolve("Weight") == "weight_kg"
    assert resolve("no-such-thing") is None


def test_store_dedupes_and_never_invents(tmp_path):
    store = HealthStore(tmp_path / "s.db")
    assert insights.overview(store)["metrics"] == {}
    assert insights.readiness(store)["score"] is None  # no data, no number
    assert store.add("steps", 5000, at=_days_ago(0), source="x", uid="a")
    assert not store.add(
        "steps", 5000, at=_days_ago(0), source="x", uid="a"
    )  # same reading
    assert not store.add("steps", -3)  # impossible
    assert not store.add("unknown", 3)
    store.add("steps", 2000, at=_days_ago(0, 18), source="x")
    assert store.daily("steps", days=2)[datetime.now().strftime("%Y-%m-%d")] == 7000


def test_phone_export_zip_is_read_with_units_and_sleep(tmp_path):
    def rec(kind, value, start, end, unit=""):
        return (
            f'<Record type="{kind}" unit="{unit}" value="{value}" '
            f'startDate="2026-10-10 {start} -0500" endDate="2026-10-10 {end} -0500"/>'
        )

    hk = "HKQuantityTypeIdentifier"
    xml = (
        '<?xml version="1.0"?><HealthData>'
        + rec(hk + "StepCount", 1200, "08:00:00", "09:00:00", "count")
        + rec(hk + "BodyMass", 176, "07:00:00", "07:00:00", "lb")
        + rec(hk + "OxygenSaturation", 0.97, "03:00:00", "03:00:00", "%")
        + rec(
            "HKCategoryTypeIdentifierSleepAnalysis",
            "HKCategoryValueSleepAnalysisAsleepDeep",
            "01:00:00",
            "02:30:00",
        )
        + "</HealthData>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("apple_health_export/export.xml", xml)
    rows = list(importers.detect_and_parse("export.zip", buf.getvalue()))
    got = {(r[0], round(r[1], 2)) for r in rows}
    assert ("steps", 1200) in got
    assert ("weight_kg", 79.83) in got  # 176 lb
    assert ("spo2", 97.0) in got
    assert ("sleep_deep_h", 1.5) in got and ("sleep_h", 1.5) in got  # deep is sleep too


def test_csv_wide_and_long():
    wide = b"date,Steps,Weight (lb),Resting heart rate\n2026-10-01,8000,180,58\n"
    rows = list(importers.from_csv(wide, "bascula"))
    assert {r[0] for r in rows} == {"steps", "weight_kg", "resting_hr"}
    longf = b"fecha;metric;value;unit\n01/10/2026;temperature;98.6;degF\n"
    (row,) = list(importers.from_csv(longf))
    assert row[0] == "temp_c" and round(row[1], 1) == 37.0


def test_automation_app_json():
    payload = {
        "data": {
            "metrics": [
                {
                    "name": "step_count",
                    "units": "count",
                    "data": [{"date": "2026-10-17 00:00:00 -0500", "qty": 9100}],
                },
                {
                    "name": "sleep_analysis",
                    "units": "hr",
                    "data": [
                        {
                            "date": "2026-10-17 00:00:00 -0500",
                            "totalSleep": 7.2,
                            "deep": 1.1,
                            "rem": 1.6,
                        }
                    ],
                },
                {
                    "name": "blood_pressure",
                    "units": "mmHg",
                    "data": [
                        {
                            "date": "2026-10-17 08:00:00 -0500",
                            "systolic": 118,
                            "diastolic": 76,
                        }
                    ],
                },
            ]
        }
    }
    got = {r[0]: r[1] for r in importers.from_json(payload)}
    assert got == {
        "steps": 9100,
        "sleep_h": 7.2,
        "sleep_deep_h": 1.1,
        "sleep_rem_h": 1.6,
        "bp_sys": 118,
        "bp_dia": 76,
    }


def test_insights_readiness_longevity_correlations(tmp_path):
    store = HealthStore(tmp_path / "s.db")
    for d in range(1, 31):
        store.add("hrv", 50 + (d % 3), at=_days_ago(d), source="r")
        store.add("resting_hr", 60, at=_days_ago(d), source="r")
        late_coffee = d % 2 == 0
        store.add(
            "caffeine_mg", 300 if late_coffee else 50, at=_days_ago(d), source="r"
        )
        store.add(
            "sleep_h", 6.0 if late_coffee else 8.0, at=_days_ago(d - 1, 7), source="r"
        )
        store.add("steps", 9000, at=_days_ago(d), source="r")
        if late_coffee:
            store.set_note(
                datetime.fromtimestamp(_days_ago(d)).strftime("%Y-%m-%d"),
                "",
                ["café tarde"],
            )
    store.add("hrv", 70, at=_days_ago(0), source="r")  # a great day
    store.add("resting_hr", 55, at=_days_ago(0), source="r")
    ready = insights.readiness(store)
    assert (
        ready["score"] is not None
        and ready["score"] >= 70
        and "Sueño" in ready["inputs"]
    )
    assert any(h["metric"] == "hrv" and h["good"] for h in insights.highlights(store))
    areas = {a["key"]: a for a in insights.longevity(store)}
    assert areas["movimiento"]["state"] == "en_rango"
    assert areas["metabolismo"]["state"] == "sin_datos"
    found = insights.correlations(store, "sleep_h")["found"]
    assert any(f.get("metric") == "caffeine_mg" and f["r"] < 0 for f in found)
    assert any(f.get("tag") == "café tarde" and f["with"] < f["without"] for f in found)


def test_api_manual_pins_goals_notes_export(client):
    assert client.get("/v1/healthdata/summary").json()["empty"] is True
    assert client.post(
        "/v1/healthdata/samples", json={"metric": "weight_kg", "value": 80.5}
    ).json()["ok"]
    assert (
        client.post(
            "/v1/healthdata/samples", json={"metric": "nope", "value": 1}
        ).status_code
        == 404
    )
    summary = client.get("/v1/healthdata/summary").json()
    assert (
        summary["metrics"]["weight_kg"]["value"] == 80.5
        and summary["sources"]["manual"]["count"] == 1
    )
    assert client.put(
        "/v1/healthdata/pins", json={"pins": ["weight_kg", "bogus"]}
    ).json()["pins"] == ["weight_kg"]
    assert client.put("/v1/healthdata/goals/steps", json={"value": 10000}).json()[
        "goals"
    ] == {"steps": 10000}
    day = datetime.now().strftime("%Y-%m-%d")
    note = client.put(
        f"/v1/healthdata/notes/{day}",
        json={"text": "Dormí mal", "tags": ["Alcohol", " "]},
    ).json()
    assert note["tags"] == ["alcohol"]
    csv_text = client.get("/v1/healthdata/export.csv").text
    assert "weight_kg" in csv_text and "manual" in csv_text
    detail = client.get("/v1/healthdata/metric/weight_kg").json()
    uid = detail["readings"][0]["uid"]
    assert client.delete(f"/v1/healthdata/samples/{uid}").json()["ok"]


def test_import_endpoint(client):
    data = b"date,steps\n2026-10-01,8000\n2026-10-02,9000\n"
    res = client.post(
        "/v1/healthdata/import",
        files={"file": ("garmin.csv", data, "text/csv")},
        params={"source": "garmin"},
    )
    assert res.json() == {"ok": True, "read": 2, "added": 2}
    again = client.post(
        "/v1/healthdata/import",
        files={"file": ("garmin.csv", data, "text/csv")},
        params={"source": "garmin"},
    )
    assert again.json()["added"] == 0  # importing twice changes nothing
    bad = client.post(
        "/v1/healthdata/import", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}
    )
    assert bad.status_code == 400
    assert client.delete("/v1/healthdata/sources/garmin").json()["removed"] == 2


def test_sync_link_needs_its_key(client):
    info = client.get("/v1/healthdata/sync").json()
    body = {
        "samples": [{"metric": "steps", "value": 4321, "at": "2026-10-18T10:00:00"}]
    }
    assert client.post("/v1/healthdata/ingest", json=body).status_code == 401
    assert (
        client.post(
            "/v1/healthdata/ingest",
            json=body,
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )
    ok = client.post(
        "/v1/healthdata/ingest",
        json=body,
        headers={"Authorization": f"Bearer {info['key']}"},
    )
    assert ok.json() == {"ok": True, "read": 1, "added": 1}
    new = client.post("/v1/healthdata/sync/rotate").json()["key"]
    assert new != info["key"]
    assert (
        client.post(
            "/v1/healthdata/ingest", json=body, params={"key": info["key"]}
        ).status_code
        == 401
    )


def test_ring_sync_with_personal_token(client, home, monkeypatch):
    calls = []

    def fake_get(token, endpoint, params):
        calls.append(endpoint)
        assert token == "personal-token-123"
        return {
            "sleep": {
                "data": [
                    {
                        "id": "s1",
                        "type": "long_sleep",
                        "day": "2026-10-17",
                        "bedtime_end": "2026-10-17T07:00:00+00:00",
                        "total_sleep_duration": 27000,
                        "deep_sleep_duration": 5400,
                        "average_hrv": 48,
                        "lowest_heart_rate": 52,
                    }
                ]
            },
            "daily_activity": {
                "data": [{"day": "2026-10-17", "steps": 10234, "active_calories": 450}]
            },
            "daily_spo2": {
                "data": [{"day": "2026-10-17", "spo2_percentage": {"average": 97.5}}]
            },
        }[endpoint]

    monkeypatch.setitem(
        devices.SYNCERS,
        "oura",
        lambda token, days=30: devices.oura_rows(token, days, get=fake_get),
    )
    res = client.post(
        "/v1/healthdata/devices/oura/key", json={"token": "personal-token-123"}
    )
    assert res.json()["added"] == 7  # 4 from the night, 2 activity, 1 oxygen
    assert (
        json.loads((home / "health" / "keys.json").read_text())["oura"]["token"]
        == "personal-token-123"
    )
    assert client.get("/v1/healthdata/summary").json()["connected"] == ["oura"]
    assert (
        client.post(
            "/v1/healthdata/devices/garmin/key", json={"token": "abcdefghij"}
        ).status_code
        == 400
    )
    client.delete("/v1/healthdata/devices/oura")
    assert client.post("/v1/healthdata/devices/oura/sync").status_code == 400


def test_ask_without_engine_uses_only_real_data(client, monkeypatch):
    import openjarvis.engine._discovery as discovery

    monkeypatch.setattr(discovery, "get_engine", lambda cfg: None)
    assert (
        "Y aún no tengo datos suyos"
        in client.post("/v1/healthdata/ask", json={"message": "¿Cómo voy?"}).json()[
            "reply"
        ]
    )
    client.post("/v1/healthdata/samples", json={"metric": "steps", "value": 6000})
    assert (
        "Pasos: 6000"
        in client.post("/v1/healthdata/ask", json={"message": "¿Cómo voy?"}).json()[
            "reply"
        ]
    )


def test_ingest_is_public_but_everything_else_is_not():
    from openjarvis.server.auth_middleware import AuthMiddleware
    from openjarvis.server.mobile import _is_public

    assert _is_public("/v1/healthdata/ingest") and not _is_public(
        "/v1/healthdata/summary"
    )
    assert not AuthMiddleware._requires_auth("/v1/healthdata/ingest")
    assert AuthMiddleware._requires_auth("/v1/healthdata/export.csv")
    assert time.time() > 0

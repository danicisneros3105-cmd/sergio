"""Tests for live world data tools and globe control."""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qs

import pytest

from openjarvis.tools.live_world import (
    GlobeViewTool,
    LiveEarthquakesTool,
    LiveFlightsTool,
    UpcomingLaunchesTool,
    read_globe_target,
)


class FakeHttp:
    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, params: dict):
        self.calls.append((url, params))
        for prefix, payload in self.responses.items():
            if url.startswith(prefix):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unexpected URL {url}")


NOMINATIM = {
    "https://nominatim.openstreetmap.org": [
        {"lat": "40.4168", "lon": "-3.7038", "display_name": "Madrid, España"}
    ]
}


def test_live_flights_sorts_by_distance_and_converts_radius():
    http = FakeHttp(
        {
            **NOMINATIM,
            "https://api.adsb.lol/v2/point/": {
                "ac": [
                    {
                        "flight": "FAR1  ",
                        "r": "EC-AAA",
                        "t": "A320",
                        "alt_baro": 30000,
                        "gs": 450.4,
                        "lat": 41.4,
                        "lon": -3.7,
                    },
                    {
                        "flight": "NEAR1",
                        "r": "EC-BBB",
                        "t": "B738",
                        "alt_baro": 5000,
                        "gs": 220,
                        "lat": 40.42,
                        "lon": -3.70,
                    },
                    {"hex": "abc123"},
                ]
            },
        }
    )
    result = LiveFlightsTool(http_get=http).execute(place="Madrid", radius_km=185)
    assert result.success, result.content
    lines = result.content.splitlines()
    assert lines[0].startswith("3 aircraft within 185 km of Madrid")
    assert lines[1].startswith("- NEAR1 (EC-BBB, B738) alt 5000 ft, 220 kt")
    assert lines[2].startswith("- FAR1 (EC-AAA, A320)")
    assert "position unknown" in lines[3]
    assert http.calls[-1][0].endswith("/40.4168/-3.7038/100")  # 185 km = 100 nm


def test_live_flights_validates_location():
    tool = LiveFlightsTool(http_get=FakeHttp({}))
    assert "place" in tool.execute().content
    assert not tool.execute(lat=91, lon=0).success
    empty = LiveFlightsTool(http_get=FakeHttp({"https://api.adsb.lol": {"ac": []}}))
    assert "No aircraft" in empty.execute(lat=1, lon=2).content


def test_live_earthquakes_near_place():
    http = FakeHttp(
        {
            **NOMINATIM,
            "https://earthquake.usgs.gov": {
                "features": [
                    {
                        "properties": {
                            "mag": 4.6,
                            "place": "10 km S of Granada",
                            "time": 1790000000000,
                        },
                        "geometry": {"coordinates": [-3.6, 37.1, 12.0]},
                    }
                ]
            },
        }
    )
    result = LiveEarthquakesTool(http_get=http).execute(
        place="Madrid", min_magnitude=4, days=7
    )
    assert result.success, result.content
    assert (
        "M4.6 10 km S of Granada" in result.content and "depth 12 km" in result.content
    )
    params = http.calls[-1][1]
    assert params["latitude"] == 40.4168 and params["maxradiuskm"] == 500
    assert params["minmagnitude"] == 4


def test_live_earthquakes_worldwide_and_provider_errors():
    http = FakeHttp({"https://earthquake.usgs.gov": {"features": []}})
    result = LiveEarthquakesTool(http_get=http).execute()
    assert "No earthquakes" in result.content and "worldwide" in result.content
    assert "latitude" not in http.calls[-1][1]
    broken = FakeHttp({"https://earthquake.usgs.gov": RuntimeError("503")})
    failed = LiveEarthquakesTool(http_get=broken).execute()
    assert not failed.success and "503" in failed.content


def test_upcoming_launches_handles_list_and_detail_shapes():
    http = FakeHttp(
        {
            "https://ll.thespacedevs.com": {
                "results": [
                    {
                        "name": "Falcon 9 | Starlink",
                        "net": "2026-10-02T10:00:00Z",
                        "status": {"name": "Go"},
                        "location": "Cape Canaveral",
                    },
                    {
                        "name": "Ariane 6",
                        "net": "2026-10-05",
                        "pad": {"location": {"name": "Kourou"}},
                    },
                ]
            }
        }
    )
    result = UpcomingLaunchesTool(http_get=http).execute(limit=2)
    assert (
        "Falcon 9 | Starlink — 2026-10-02T10:00:00Z — Cape Canaveral (Go)"
        in result.content
    )
    assert "Ariane 6 — 2026-10-05 — Kourou" in result.content


@pytest.fixture
def globe_up(monkeypatch):
    from openjarvis.tools import live_world

    monkeypatch.setattr(
        live_world, "ensure_globe", lambda wait=90.0: (True, "http://127.0.0.1:4173/")
    )


def test_globe_view_explains_when_the_globe_cannot_start(monkeypatch):
    from openjarvis.tools import live_world

    monkeypatch.setattr(
        live_world,
        "ensure_globe",
        lambda wait=90.0: (False, "El globo no arrancó: skipped: Node.js 24+"),
    )
    result = GlobeViewTool(http_get=FakeHttp(NOMINATIM)).execute(place="Madrid")
    assert not result.success and "Node.js" in result.content


def test_globe_view_writes_target_for_the_ui(globe_up):
    result = GlobeViewTool(http_get=FakeHttp(NOMINATIM)).execute(
        place="Madrid", style="night_vision", altitude_m=500_000
    )
    assert result.success, result.content
    target = read_globe_target()
    assert target["label"] == "Madrid, España"
    params = parse_qs(target["hash"])
    assert params["style"] == ["nvg"] and params["pitch"] == ["-90"]
    assert target["url"].startswith("http://127.0.0.1:4173/#lat=40.41680")
    assert json.loads(json.dumps(target)) == target

    bad = GlobeViewTool(http_get=FakeHttp({})).execute(lat=1, lon=1, style="laser")
    assert not bad.success and "Unknown style" in bad.content


# -- the plane right above you -------------------------------------------------
from openjarvis.tools import live_world  # noqa: E402

CUENCA = (-2.9001, -79.0059)


def _plane(hexid, flight, lat, lon, alt_ft, **kw):
    return {
        "hex": hexid,
        "flight": flight,
        "lat": lat,
        "lon": lon,
        "alt_geom": alt_ft,
        **kw,
    }


def _overhead_http(ac_lists, route=None, aircraft=None, fail=()):
    calls = []

    def get(url, params):
        calls.append(url)
        for name in fail:
            if name in url:
                raise RuntimeError("down")
        if "open-meteo" in url:
            return {"elevation": [2560.0]}
        if "adsbdb.com/v0/callsign" in url:
            if route is None:
                raise RuntimeError("404")
            return {"response": {"flightroute": route}}
        if "adsbdb.com/v0/aircraft" in url:
            if aircraft is None:
                raise RuntimeError("404")
            return {"response": {"aircraft": aircraft}}
        if "opensky" in url:
            return {"time": 0, "states": []}
        for key, rows in ac_lists.items():
            if key in url:
                return {"ac": rows}
        return {"ac": []}

    return get, calls


def test_overhead_picks_the_plane_highest_in_the_sky_and_names_the_flight():
    lat, lon = CUENCA
    above = _plane(
        "e8044e",
        "LAN1442 ",
        lat + 0.01,
        lon + 0.01,
        35000,
        gs=440,
        track=210,
        baro_rate=-1200,
        r="CC-BAZ",
        t="A320",
    )
    far_low = _plane("abc123", "AVA88", lat + 0.3, lon, 9000, gs=250, track=90)
    get, calls = _overhead_http(
        {"adsb.lol": [above], "airplanes.live": [far_low, dict(above, seen_pos=0.4)]},
        route={
            "callsign": "LAN1442",
            "airline": {"name": "LATAM Airlines", "iata": "LA", "icao": "LAN"},
            "origin": {"municipality": "Quito", "iata_code": "UIO"},
            "destination": {"municipality": "Guayaquil", "iata_code": "GYE"},
        },
        aircraft={
            "manufacturer": "Airbus",
            "type": "A320 214",
            "registration": "CC-BAZ",
        },
    )
    report = live_world.overhead_report(lat, lon, http_get=get)
    text = report["text"]
    assert report["callsign"] == "LAN1442" and report["elevation"] > 70
    assert text.startswith("Justo encima de usted")
    assert "LA1442 (LAN1442) de LATAM Airlines" in text
    assert (
        "Airbus A320 214, matrícula CC-BAZ" in text
        and "de Quito (UIO) a Guayaquil (GYE)" in text
    )
    assert "bajando" in text and "AVA88" in text  # the other one, as "también cerca"
    assert report["ground_m"] == 2560.0  # the ground is high in Cuenca
    assert set(report["sources"]) >= {"adsb.lol", "airplanes.live"}


def test_overhead_with_no_planes_and_with_every_network_down():
    get, _ = _overhead_http({})
    report = live_world.overhead_report(*CUENCA, http_get=get)
    assert report["count"] == 0 and "no hay aviones" in report["text"]
    dead, _ = _overhead_http(
        {}, fail=("adsb.lol", "airplanes.live", "adsb.fi", "opensky")
    )
    with pytest.raises(RuntimeError, match="Ninguna red"):
        live_world.overhead_report(*CUENCA, http_get=dead)


def test_plane_geometry_elevation_and_direction():
    lat, lon = 0.0, 0.0
    geo = live_world.plane_geometry(lat, lon, 0.0, _plane("x", "T", 0.0899, 0.0, 32808))
    assert abs(geo["ground_km"] - 10.0) < 0.1 and abs(geo["elevation"] - 45.0) < 1.0
    assert live_world.compass(geo["bearing"]) == "norte"
    assert (
        live_world.plane_geometry(
            lat, lon, 0, {"hex": "y", "lat": 1, "lon": 1, "alt_baro": "ground"}
        )
        is None
    )


def test_opensky_rows_are_converted():
    rows = live_world.opensky_rows(
        {
            "time": 100,
            "states": [
                [
                    "abc",
                    "AAL1 ",
                    "US",
                    98,
                    99,
                    -79.0,
                    -2.9,
                    9000,
                    False,
                    230,
                    180,
                    -5,
                    None,
                    9100,
                    "7700",
                ],
                [
                    "def",
                    "X",
                    "US",
                    98,
                    99,
                    -79.0,
                    -2.9,
                    0,
                    True,
                    0,
                    0,
                    0,
                    None,
                    0,
                    None,
                ],
            ],
        }
    )
    assert len(rows) == 1 and rows[0]["flight"] == "AAL1" and rows[0]["seen_pos"] == 2
    assert round(rows[0]["alt_geom"]) == 29856 and rows[0]["squawk"] == "7700"


def test_bare_place_names_prefer_the_users_country(monkeypatch):
    monkeypatch.setenv("SERGIO_COUNTRY", "ec")
    asked = []

    def get(url, params):
        asked.append(params)
        return [
            {"lat": "-2.9", "lon": "-79.0", "display_name": "Cuenca, Azuay, Ecuador"}
        ]

    lat, _lon, label = live_world.geocode("Cuenca", get)
    assert asked[0]["countrycodes"] == "ec" and lat == -2.9 and "Ecuador" in label
    live_world.geocode("Cuenca, España", get)
    assert "countrycodes" not in asked[-1]


def test_a_hanging_network_never_holds_the_answer():
    import threading

    stop = threading.Event()
    lat, lon = CUENCA
    ok = _plane("e1", "AVA1", lat + 0.01, lon, 30000)

    def get(url, params):
        if "airplanes.live" in url or "adsbdb" in url or "open-meteo" in url:
            stop.wait(30)  # a network that never answers
            return {}
        if "adsb.lol" in url:
            return {"ac": [ok]}
        return {"ac": []}

    started = time.time()
    report = live_world.overhead_report(lat, lon, http_get=get)
    stop.set()
    assert time.time() - started < 8 and report["callsign"] == "AVA1"

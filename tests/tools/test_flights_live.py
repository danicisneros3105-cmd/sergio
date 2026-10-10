"""Flights followed live: call signs, position, route, the spoken line."""

from __future__ import annotations

from openjarvis.tools import flights_live as pc


def fake(routes):
    calls = []

    def get(url, headers):
        calls.append((url, headers))
        for key, value in routes.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise RuntimeError("offline")

    return get, calls


def test_flight_numbers_become_call_signs():
    assert pc.callsigns("AV 123") == ["AV123", "AVA123"]
    assert pc.callsigns("ibe6463") == ["IBE6463"]
    assert pc.callsigns("LA2403") == ["LA2403", "LAN2403"]


def test_a_flight_is_found_live_with_its_public_map():
    ac = {
        "hex": "E8019A",
        "flight": "AVA123  ",
        "lat": -2.1,
        "lon": -79.9,
        "alt_baro": 35000,
        "gs": 450,
        "track": 182.0,
        "t": "A320",
    }
    get, calls = fake(
        {
            "adsb.lol/v2/callsign/AVA123": {"ac": [ac]},
            "adsb.lol/v2/callsign/AV123": {"ac": []},
            "adsb.fi": {"aircraft": []},
        }
    )
    found = pc.find_flight("AV 123", http_get=get)
    assert (
        found["callsign"] == "AVA123"
        and found["alt_m"] == 10668
        and found["speed_kmh"] == 833
    )
    assert found["live_map"] == "https://globe.adsb.lol/?icao=e8019a"


def test_route_from_adsbdb():
    data = {
        "response": {
            "flightroute": {
                "airline": {"name": "Avianca"},
                "origin": {"municipality": "Bogotá", "country_name": "Colombia"},
                "destination": {"municipality": "Guayaquil", "country_name": "Ecuador"},
            }
        }
    }
    get, _ = fake({"adsbdb": data})
    assert pc.flight_route("AVA123", get) == {
        "airline": "Avianca",
        "from": "Bogotá, Colombia",
        "to": "Guayaquil, Ecuador",
    }


def test_the_flight_is_said_in_words():
    text = pc.describe_flight(
        {
            "callsign": "AVA123",
            "alt_m": 10668,
            "speed_kmh": 833,
            "on_ground": False,
            "route": {"airline": "Avianca", "from": "Bogotá", "to": "Guayaquil"},
        }
    )
    assert text == "El vuelo AVA123 de Avianca (Bogotá → Guayaquil) va en el aire a 10.668 m, a 833 km/h."

"""Where the laptop is: Windows location first, then internet, then config."""

import json

from sergio_escritorio.location import Fix, Location, ip_fix, parse_fixed, windows_fix


def test_windows_location_with_accuracy_and_altitude():
    out = json.dumps(
        {
            "permission": "Granted",
            "status": "Ready",
            "lat": -2.9,
            "lon": -79.0,
            "alt": 2560.0,
            "accuracy": 35.0,
        }
    )
    fix, problem = windows_fix(run=lambda _script: out)
    assert (
        fix.lat == -2.9 and fix.alt == 2560.0 and fix.accuracy_m == 35.0 and not problem
    )
    assert "±35 m" in fix.describe()


def test_windows_location_denied_says_how_to_allow_it():
    fix, problem = windows_fix(run=lambda _s: json.dumps({"permission": "Denied"}))
    assert fix is None and "Privacidad y seguridad > Ubicación" in problem


def test_internet_guess_when_windows_cannot():
    fix = ip_fix(get=lambda url: {"latitude": -2.9, "longitude": -79.0})
    assert fix.source == "ip" and "aproximada" in fix.describe()
    assert ip_fix(get=lambda url: (_ for _ in ()).throw(RuntimeError("x"))) is None


def test_order_and_cache():
    clock = [0.0]
    asked = []

    def windows():
        asked.append(1)
        return None, "apagada"

    loc = Location(
        "-2.90,-79.00",
        windows=windows,
        ip=lambda: Fix(-2.0, -79.5, 15000, "ip"),
        clock=lambda: clock[0],
    )
    fix = loc.get()
    assert fix.source == "config"  # set by hand beats a city-level guess
    assert loc.problem == "apagada"
    loc.get()
    assert len(asked) == 1  # cached
    clock[0] += 400
    loc.get()
    assert len(asked) == 2  # refreshed after five minutes


def test_parse_fixed():
    assert parse_fixed({"lat": 1, "lon": 2}).lat == 1
    assert parse_fixed("Cuenca") is None and parse_fixed("100,2") is None

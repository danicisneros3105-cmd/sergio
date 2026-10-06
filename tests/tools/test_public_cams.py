"""Public live cameras near a place, and a flight followed live."""

from __future__ import annotations

from openjarvis.tools import public_cams as pc

TFL = [
    {"id": "JamCams_00001.01", "commonName": "Oxford St / Regent St", "lat": 51.5154, "lon": -0.1418,
     "additionalProperties": [
         {"key": "available", "value": "true"},
         {"key": "imageUrl", "value": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/00001.01.jpg"}]},
    {"id": "JamCams_off", "commonName": "Off", "lat": 51.5, "lon": -0.1,
     "additionalProperties": [{"key": "available", "value": "false"},
                              {"key": "imageUrl", "value": "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/x.jpg"}]},
    {"id": "JamCams_evil", "commonName": "Elsewhere", "lat": 51.5, "lon": -0.1,
     "additionalProperties": [{"key": "available", "value": "true"},
                              {"key": "imageUrl", "value": "https://evil.example/x.jpg"}]},
]
FIN = {"features": [{"geometry": {"coordinates": [24.94, 60.17, 0]},
                     "properties": {"id": "C01503", "name": "Helsinki Itäväylä", "collectionStatus": "GATHERING",
                                    "presets": [{"id": "C0150301", "inCollection": True},
                                                {"id": "bad", "inCollection": True}]}}]}


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


def test_london_gets_only_official_live_jamcams_nearest_first():
    get, calls = fake({"tfl.gov.uk": TFL})
    found = pc.cams_near(51.5136, -0.1365, http_get=get)
    assert [c["name"] for c in found["cams"]] == ["Oxford St / Regent St"]
    assert found["cams"][0]["km"] < 1 and found["sources"] == ["Londres"]
    assert len(calls) == 1  # only the feeds that cover the place are asked


def test_finland_presets_become_weathercam_stills_with_the_user_header():
    get, calls = fake({"digitraffic": FIN})
    found = pc.cams_near(60.17, 24.94, http_get=get)
    assert [c["url"] for c in found["cams"]] == ["https://weathercam.digitraffic.fi/C0150301.jpg"]
    assert calls[0][1]["Digitraffic-User"]


def test_windy_covers_the_rest_of_the_world_with_a_key():
    windy = {"webcams": [{"webcamId": 1, "title": "Cuenca - Parque Calderón", "status": "active",
                          "location": {"latitude": -2.897, "longitude": -79.004, "city": "Cuenca"},
                          "images": {"current": {"preview": "https://images-webcams.windy.com/1/preview.jpg"}}}]}
    get, calls = fake({"api.windy.com": windy})
    assert pc.cams_near(-2.9, -79.0, http_get=get)["cams"] == []  # no key: nothing invented
    found = pc.cams_near(-2.9, -79.0, http_get=get, windy_key="k")
    assert found["cams"][0]["name"] == "Cuenca - Parque Calderón"
    assert calls[-1][1] == {"x-windy-api-key": "k"}


def test_a_feed_that_is_down_is_reported_not_fatal():
    get, _ = fake({"tfl.gov.uk": RuntimeError("503")})
    assert pc.cams_near(51.5, -0.12, http_get=get) == {"cams": [], "sources": [], "failed": ["Londres"]}


def test_flight_numbers_become_call_signs():
    assert pc.callsigns("AV 123") == ["AV123", "AVA123"]
    assert pc.callsigns("ibe6463") == ["IBE6463"]
    assert pc.callsigns("LA2403") == ["LA2403", "LAN2403"]


def test_a_flight_is_found_live_with_its_public_map():
    ac = {"hex": "E8019A", "flight": "AVA123  ", "lat": -2.1, "lon": -79.9, "alt_baro": 35000, "gs": 450,
          "track": 182.0, "t": "A320"}
    get, calls = fake({"adsb.lol/v2/callsign/AVA123": {"ac": [ac]}, "adsb.lol/v2/callsign/AV123": {"ac": []},
                       "adsb.fi": {"aircraft": []}})
    found = pc.find_flight("AV 123", http_get=get)
    assert found["callsign"] == "AVA123" and found["alt_m"] == 10668 and found["speed_kmh"] == 833
    assert found["live_map"] == "https://globe.adsb.lol/?icao=e8019a"


def test_route_from_adsbdb():
    data = {"response": {"flightroute": {"airline": {"name": "Avianca"},
                                         "origin": {"municipality": "Bogotá", "country_name": "Colombia"},
                                         "destination": {"municipality": "Guayaquil", "country_name": "Ecuador"}}}}
    get, _ = fake({"adsbdb": data})
    assert pc.flight_route("AVA123", get) == {"airline": "Avianca", "from": "Bogotá, Colombia", "to": "Guayaquil, Ecuador"}

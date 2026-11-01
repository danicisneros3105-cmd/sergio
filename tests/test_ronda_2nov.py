"""Ronda del 1–2 nov. 2026: cine IA, Rodin, conserje (reservas, viajes, ventas,
Tesla, correo, agenda) y la honestidad de las acciones antiguas."""

from __future__ import annotations

import json
from email import message_from_bytes

import pytest


class Resp:
    def __init__(self, data=None, status=200, content=b""):
        self._data = data or {}
        self.status_code = status
        self.content = content

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# -- 3D: Rodin -------------------------------------------------------------------------


def test_rodin_submits_waits_and_downloads_the_glb(monkeypatch):
    from openjarvis.creator import nube3d

    monkeypatch.setenv("HYPER3D_API_KEY", "k")
    calls = []

    class Http:
        def post(self, url, **kw):
            calls.append(url)
            if url.endswith("/rodin"):
                return Resp({"uuid": "t1", "jobs": {"subscription_key": "s1"}})
            if url.endswith("/status"):
                return Resp({"jobs": [{"status": "Done"}]})
            return Resp({"list": [{"name": "base.glb", "url": "https://x/m.glb"}]})

        def get(self, url, **kw):
            return Resp(content=b"glTF-model")

    assert nube3d.rodin("una silla", http=Http(), sleep=lambda s: None) == b"glTF-model"
    assert [c.rsplit("/", 1)[1] for c in calls] == ["rodin", "status", "download"]
    assert "rodin" in nube3d.services()


def test_cloud_3d_compare_keeps_every_service_version(monkeypatch, tmp_path):
    from openjarvis.creator import despiece, nube3d

    monkeypatch.setattr(
        despiece,
        "register_file",
        lambda p, title, home=None: {"name": f"m{len(p)}", "titulo": title},
    )
    meta = nube3d.generate(
        "un dron",
        order=["tripo", "rodin"],
        runners={"tripo": lambda: b"glTF1", "rodin": lambda: b"glTF2"},
        compare=True,
    )
    assert [v["fuente"] for v in meta["versiones"]] == ["Tripo", "Rodin"]


# -- cine IA (Higgsfield or Sergio's AI video) -----------------------------------------


def test_cine_brief_without_a_model_still_has_four_cinematic_beats():
    from openjarvis.creator import cine_ia

    film = cine_ia.brief("un perro astronauta", ask=lambda p: "", platform="tiktok")
    assert film.aspect == "9:16"
    assert [s.beat for s in film.shots] == ["gancho", "subida", "giro", "remate"]
    assert "camera:" in film.shots[0].prompt() and "no text" in film.shots[0].prompt()


def test_cine_brief_reads_the_directors_json_and_keeps_known_moves():
    from openjarvis.creator import cine_ia

    raw = json.dumps({"look": "teal and orange", "shots": [
        {"beat": "gancho", "action": "A runner at dawn", "camera": "fpv", "seconds": 6},
        {"beat": "remate", "action": "Arms up", "camera": "spin_wild", "seconds": 99},
    ]})  # fmt: skip
    film = cine_ia.brief("correr", ask=lambda p: raw, shots=2, platform="youtube largo")
    assert film.aspect == "16:9" and film.look == "teal and orange"
    assert film.shots[0].camera == "fpv"
    assert film.shots[1].camera == "dolly_in" and film.shots[1].seconds == 8


def test_cine_render_without_higgsfield_uses_sergios_ai_video(tmp_path):
    from openjarvis.creator import cine_ia

    film = cine_ia.brief("un faro", ask=lambda p: "", shots=2)

    def provider(prompt, out, secs, aspect):
        out.write_bytes(b"mp4")
        return str(out)

    done = cine_ia.render(
        film, root=tmp_path, provider=provider, join=lambda files, out: files[0]
    )
    assert done.engine == "video IA de Sergio" and len(done.files) == 2
    assert (tmp_path / film.id / "plan.json").exists()


def test_cine_render_with_the_higgsfield_connector_waits_for_the_job(tmp_path):
    from openjarvis.creator import cine_ia

    job = "123e4567-e89b-42d3-a456-426614174000"

    class Hub:
        def __init__(self):
            self.calls = []

        def list(self):
            return [{"id": "hf", "name": "Higgsfield", "connected": True}]

        def call(self, sid, tool, args=None, approved=False):
            self.calls.append(tool)
            if tool == "generate_video":
                return {
                    "content": [{"type": "text", "text": json.dumps({"job_id": job})}]
                }
            return {"content": [{"type": "text", "text": '{"status": "completed", '
                                 '"url": "https://cdn.example/v.mp4"}'}]}  # fmt: skip

    hub = Hub()
    film = cine_ia.brief("un faro", ask=lambda p: "", shots=1)
    got = []
    done = cine_ia.render(
        film, hub=hub, root=tmp_path, sleep=lambda s: None,
        download=lambda url, out: got.append(url) or str(out),
        join=lambda files, out: files[0],
    )  # fmt: skip
    assert done.engine == "Higgsfield"
    assert hub.calls == ["generate_video", "jobs_wait"]
    assert got == ["https://cdn.example/v.mp4"]


def test_cine_catalog_asks_to_connect_when_there_is_no_connector():
    from openjarvis.creator import cine_ia

    class Hub:
        def list(self):
            return []

    with pytest.raises(cine_ia.CineError, match="Conectores"):
        cine_ia.catalog("viral", hub=Hub())


# -- restaurants -----------------------------------------------------------------------


def test_hard_restaurant_plan_quotes_when_the_book_opens():
    from openjarvis.conserje import restaurantes

    page = "https://example.com/noma - Reservations open 30 days in advance at 10 am."
    r = restaurantes.plan("Noma", city="Copenhague", date="2026-12-12", people=2,
                          search=lambda q: page)  # fmt: skip
    assert r.apertura.startswith("30 days antes") and "10 am" in r.apertura
    assert r.fuente == "https://example.com/noma"
    assert (
        "inteligencia artificial" in r.guion_llamada
        and "parte del señor" in r.guion_llamada
    )
    assert "OpenTable" in r.enlaces
    assert "DETENTE" in restaurantes.operator_goal(r)


def test_restaurant_plan_never_invents_the_opening_time():
    from openjarvis.conserje import restaurantes

    r = restaurantes.plan("Central", city="Lima", search=lambda q: "nada útil aquí")
    assert r.apertura == "" and "No encontré" in r.pasos[1]


# -- flights and trips --------------------------------------------------------------------


def test_flights_without_a_key_give_links_not_prices(monkeypatch):
    from openjarvis.conserje import viajes

    monkeypatch.delenv("DUFFEL_ACCESS_TOKEN", raising=False)
    got = viajes.search_flights("UIO", "PEK", "2026-12-01")
    assert got["ofertas"] == [] and "Google Flights" in got["enlaces"]


def test_flights_with_duffel_are_real_offers_cheapest_first(monkeypatch):
    from openjarvis.conserje import viajes

    monkeypatch.setenv("DUFFEL_ACCESS_TOKEN", "duffel_test")

    def offer(price, stops):
        seg = {
            "departing_at": "2026-12-01T08:00:00",
            "arriving_at": "2026-12-02T10:00:00",
        }
        return {"id": f"off_{price}", "total_amount": str(price), "total_currency": "USD",
                "owner": {"name": "Air"}, "slices": [{"duration": "PT26H5M",
                                                       "segments": [seg] * (stops + 1)}]}  # fmt: skip

    class Http:
        def post(self, url, **kw):
            assert kw["headers"]["Duffel-Version"] == "v2"
            return Resp({"data": {"offers": [offer(1200, 1), offer(980, 2)]}})

    got = viajes.search_flights("UIO", "PEK", "2026-12-01", http=Http())
    assert [o.precio for o in got["ofertas"]] == [980.0, 1200.0]
    assert got["ofertas"][0].duracion == "26 h 05 min" and got["fuente"] == "Duffel"


def test_trip_to_a_budget_uses_the_real_fare_and_saves_the_plan(tmp_path):
    from openjarvis.conserje import viajes

    fare = viajes.Offer(
        1000.0, "USD", "Air", "2026-12-01 08:00", "2026-12-02 10:00", 1, "26 h"
    )
    itinerary = json.dumps(
        {"dias": [{"dia": "1", "zona": "Beijing", "manana": "Ciudad Prohibida"}]}
    )
    t = viajes.plan_trip(
        "China", days=3, budget=3000, origin="UIO", start="2026-12-01",
        ask=lambda p: itinerary, flights=lambda *a, **k: {"ofertas": [fare], "enlaces": {}},
        root=tmp_path,
    )  # fmt: skip
    assert t.reparto["vuelos"] == 1000.0
    assert round(sum(t.reparto.values())) == 3000
    assert t.itinerario[0]["zona"] == "Beijing"
    assert any("consulado" in d for d in t.documentos)
    assert (tmp_path / f"{t.id}.json").exists()


# -- selling --------------------------------------------------------------------------------


def _photo(path):
    from PIL import Image

    Image.new("RGB", (40, 40), (200, 10, 10)).save(path)
    return str(path)


def test_gallery_photos_are_checked_by_looking_at_them(tmp_path):
    from openjarvis.conserje import venta

    a, b = _photo(tmp_path / "IMG_1.jpg"), _photo(tmp_path / "IMG_2.jpg")
    answers = iter(["Sí, es un iPhone", "no"])
    got = venta.find_photos(
        "iPhone 15", candidates=[a, b], look=lambda img, q: next(answers)
    )
    assert got == {"fotos": [a], "comprobadas": True}


def test_ad_uses_only_his_facts_and_never_a_made_up_price(tmp_path):
    from openjarvis.conserje import venta

    ad = venta.listing(
        "iPhone 15 Pro", "256 GB, batería 94 %", photos=[], ask=lambda p: "",
        search=lambda q: "sin precios", root=tmp_path, make_cutouts=False,
    )  # fmt: skip
    assert ad.precio == "a definir" and "dígame" in ad.precio_fuente
    assert (
        "batería 94 %" in ad.descripcion and "impecable" not in ad.descripcion.lower()
    )
    goal = venta.operator_goal(ad, "Facebook Marketplace")
    assert "marketplace/create" in goal and "DETENTE" in goal


def test_ebay_publish_does_nothing_without_his_yes(monkeypatch, tmp_path):
    from openjarvis.conserje import venta

    for k in ("EBAY_USER_TOKEN", "EBAY_FULFILLMENT_POLICY", "EBAY_PAYMENT_POLICY",
              "EBAY_RETURN_POLICY", "EBAY_LOCATION_KEY", "EBAY_CATEGORY_ID"):  # fmt: skip
        monkeypatch.setenv(k, "x")

    class Http:
        def __getattr__(self, name):
            raise AssertionError("eBay must not be called without his yes")

    ad = venta.Listing("iPhone", "iPhone 15", "desc", "800 USD", "su precio")
    got = venta.ebay_publish(ad, [], http=Http(), approver=lambda w, p: False)
    assert got["estado"].startswith("no publicado")


def test_buyer_reply_falls_back_to_the_ad_facts():
    from openjarvis.conserje import venta

    def broken(prompt):
        raise RuntimeError("no model")

    reply = venta.reply_draft("¿sigue disponible?", {"titulo": "iPhone 15", "precio": "800 USD"},
                              ask=broken)  # fmt: skip
    assert "iPhone 15" in reply and "800 USD" in reply


# -- Tesla ----------------------------------------------------------------------------------


def test_tesla_says_honestly_it_cannot_drive_the_car():
    from openjarvis.conserje import tesla

    assert tesla.do("tráelo a la puerta de entrada") == tesla.NO_SUMMON


def test_tesla_heat_and_unlock_needs_his_yes(monkeypatch):
    from openjarvis.conserje import tesla

    monkeypatch.setenv("TESLA_ACCESS_TOKEN", "t")
    monkeypatch.setenv("TESLA_VIN", "5YJ000")
    sent = []

    class Http:
        def post(self, url, **kw):
            if url.endswith("/wake_up"):
                return Resp({"response": {"state": "online"}})
            sent.append((url.rsplit("/", 1)[1], kw.get("json")))
            return Resp({"response": {"result": True}})

    said = tesla.do(
        "maneja mi tesla hasta la puerta de entrada, ponle calefacción y desbloquéalo",
        http=Http(), approver=lambda w, p: False, sleep=lambda s: None,
    )  # fmt: skip
    names = [n for n, _ in sent]
    assert said.startswith(tesla.NO_SUMMON)
    assert "auto_conditioning_start" in names and ("set_temps", {"driver_temp": 24.0,
                                                              "passenger_temp": 24.0}) in sent  # fmt: skip
    assert "door_unlock" not in names and "sin su sí" in said


# -- e-mail, agenda, links -------------------------------------------------------------------


def test_mass_email_is_personal_drafts_never_sent(tmp_path):
    from openjarvis.conserje import correo

    csv = tmp_path / "c.csv"
    csv.write_text("nombre,email,empresa\nAna,ana@x.com,Acme\nSin,,Nada\n", "utf-8")
    contacts = correo.read_contacts(str(csv))
    got = correo.drafts(
        "Hola {nombre}", "Vi lo que hace {empresa}.", contacts, tmp_path / "out"
    )
    assert got["borradores"] == 1
    msg = message_from_bytes(open(got["archivos"][0], "rb").read())
    assert msg["Subject"] == "Hola Ana" and msg["X-Unsent"] == "1"
    assert "Acme" in msg.get_payload() and "no recibir" in msg.get_payload()


def test_today_joins_calendar_reminders_and_trips(tmp_path):
    from openjarvis.conserje import agenda

    (tmp_path / "t.json").write_text(
        json.dumps({"fecha": "2026-11-02", "destino": "China"})
    )
    text = agenda.today(calendar=lambda: "10:00 Dentista", reminders=lambda: "Pastilla 8:00",
                        root=tmp_path, day="2026-11-02")  # fmt: skip
    assert "Dentista" in text and "Pastilla" in text and "China" in text
    empty = agenda.today(
        calendar=lambda: "", reminders=lambda: "", root=tmp_path, day="2026-01-01"
    )
    assert "No veo nada" in empty


def test_uber_link_opens_the_app_with_the_destination():
    from openjarvis.conserje import enlaces

    url = enlaces.uber("Aeropuerto Mariscal Lamar")
    assert url.startswith("https://m.uber.com/ul/?action=setPickup")
    assert "pickup=my_location" in url and "Aeropuerto" in url


def test_the_concierge_tool_is_registered_and_wired_to_the_brain():
    # (the registry is cleared between tests: check the tools themselves)
    from openjarvis.connectome import neurons
    from openjarvis.security.capabilities import DEFAULT_TOOL_CAPABILITIES
    from openjarvis.tools.conserje_tool import ConciergeTool
    from openjarvis.tools.creator_tools import CinematicAIVideoTool

    for tool in (ConciergeTool(), CinematicAIVideoTool()):
        assert tool.spec.name == tool.tool_id
        assert tool.tool_id in DEFAULT_TOOL_CAPABILITIES
    sel = neurons.innate(
        neurons.normalise("reserva una mesa en un restaurante con lista de espera")
    )
    assert "conserje" in sel
    assert "cine_ia" in neurons.tools_of("video")


def test_old_market_price_no_longer_invents_a_number():
    from openjarvis.tools.commerce_intel import estimate_market_price

    price, why = estimate_market_price("iPhone 15 Pro", "razonable")
    assert price == "precio a definir" and "dígame" in why.lower()


def test_instagram_story_publishes_a_photo_as_a_story(monkeypatch, tmp_path):
    from openjarvis.automatiza import canales

    monkeypatch.setattr(
        canales, "account", lambda name, home=None: {"token": "tk", "user_id": "u1"}
    )
    monkeypatch.setattr(canales, "share_once", lambda p: "https://pub/once")
    sent = []

    class Http:
        def post(self, url, data=None, **kw):
            sent.append((url.rsplit("/", 1)[1], data))
            return Resp({"id": "c1"} if url.endswith("/media") else {"id": "p1"})

        def get(self, *a, **k):
            raise AssertionError("a photo needs no processing wait")

    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"jpg")
    got = canales.instagram_story(photo, http=Http(), wait=lambda s: None)
    assert got == {"canal": "instagram", "historia": "p1"}
    assert (
        sent[0][1]["media_type"] == "STORIES"
        and sent[0][1]["image_url"] == "https://pub/once"
    )

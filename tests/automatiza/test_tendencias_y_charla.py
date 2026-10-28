"""Trends from real signals only, and Automatizar as a conversation that asks
before it changes anything."""

from __future__ import annotations

import json

from openjarvis.automatiza import charla, tendencias

RSS = """<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>eclipse solar</title><ht:approx_traffic>200K+</ht:approx_traffic>
<ht:news_item><ht:news_item_title>El eclipse se verá en Ecuador</ht:news_item_title></ht:news_item></item>
<item><title>final copa</title><ht:approx_traffic>50K+</ht:approx_traffic></item>
</channel></rss>"""


class _Resp:
    def __init__(self, text="", data=None):
        self.text, self._data = text, data

    def json(self):
        return self._data


def _get(url, **kw):
    if "trends.google" in url:
        return _Resp(RSS)
    if "wikimedia" in url:
        return _Resp(data={"mostread": {"articles": [
            {"titles": {"normalized": "Eclipse solar"}, "views": 90000, "description": "fenómeno"},
            {"titles": {"normalized": "Special:Search"}, "views": 1}]}})  # fmt: skip
    if "reddit" in url:
        return _Resp(data={"data": {"children": [
            {"data": {"title": "Photos of the solar eclipse", "ups": 40000, "subreddit": "pics"}},
            {"data": {"title": "nsfw", "ups": 9, "over_18": True}}]}})  # fmt: skip
    raise OSError("sin red")


def test_signals_are_read_ranked_and_cached(tmp_path):
    got = tendencias.read("EC", "", get=_get, home=tmp_path)
    assert set(got["fuentes"]) == {"Google Trends", "Wikipedia", "Reddit"}
    top = got["senales"][0]
    assert (
        "eclipse" in top["tema"].lower() and len(top["fuentes"]) >= 2
    )  # seen everywhere
    assert top["cifra"] in (200000, 90000, 40000)
    assert all("nsfw" not in s["tema"] for s in got["senales"])

    def broken(url, **kw):
        raise AssertionError("cached: no new reads")

    assert (
        tendencias.read("EC", "", get=broken, home=tmp_path)["senales"]
        == got["senales"]
    )


def test_an_idea_without_a_real_signal_is_dropped(tmp_path):
    def ask(prompt, **kw):
        assert "eclipse solar" in prompt and "never invent" in prompt
        return json.dumps({"ideas": [
            {"title": "Qué pasa si miras el eclipse", "hook": "Tus ojos no sienten dolor.",
             "signal": "eclipse solar", "genre": "explicado3d", "format": "short", "why": "200K búsquedas"},
            {"title": "El meme del año", "hook": "x", "signal": "un tema inventado", "genre": "pesada"},
        ]})  # fmt: skip

    got = tendencias.ideas("EC", "ciencia", ask=ask, get=_get, home=tmp_path)
    assert [i["titulo"] for i in got["ideas"]] == ["Qué pasa si miras el eclipse"]
    assert (
        got["ideas"][0]["genero"] == "explicado3d"
        and got["ideas"][0]["senal"]["fuente"]
    )


def test_no_internet_says_so(tmp_path):
    def offline(url, **kw):
        raise OSError("sin red")

    got = tendencias.ideas(
        "EC", "", ask=lambda p, **k: "{}", get=offline, home=tmp_path
    )
    assert got["ideas"] == [] and "No pude leer" in got["aviso"]


def test_a_channel_request_beyond_youtube_and_instagram():
    reply = charla.answer(
        "haz 2 shorts al día de datos curiosos de historia para TikTok y YouTube"
    )
    assert reply["intencion"] == "canal"
    card = reply["tarjetas"][0]
    body = card["boton"]["cuerpo"]
    assert body["por_dia"] == 2 and body["publicar_en"] == ["youtube"] and body["auto"]
    assert "datos curiosos de historia" in body["idea"]
    assert "TikTok" in reply["texto"] and "listo para subir" in reply["texto"]
    assert card["boton"]["ruta"] == "/canal"  # nothing created until the tap


def test_only_manual_platforms_never_post_alone():
    body = charla.answer("un video diario sobre recetas para LinkedIn")["tarjetas"][0][
        "boton"
    ]["cuerpo"]
    assert body["auto"] is False and body["publicar_en"] == [] and body["por_dia"] == 1


def test_words_pick_the_intent_and_a_model_only_when_unclear():
    asked = []
    assert charla.classify("¿de qué hago videos esta semana?") == "tendencias"
    assert charla.classify("búscame clientes freelance") == "oportunidades"
    assert charla.classify("para el trading ya") == "trading"
    assert charla.classify("¿cómo va todo?") == "estado"
    assert (
        charla.classify("hmm", ask=lambda p, **k: asked.append(p) or "estabilidad")
        == "estabilidad"
    )
    assert asked and charla.classify("hmm", ask=lambda p, **k: "borra todo") == "ayuda"


def test_trend_ideas_come_as_cards_with_a_video_button():
    ideas = {"fuentes": ["Google Trends"], "ideas": [{"titulo": "T", "gancho": "G", "por_que": "P",
                                                      "genero": "", "formato": "short", "senal": {}}]}  # fmt: skip
    reply = charla.answer(
        "ideas de videos de ciencia", readers={"ideas": lambda p, n: ideas}
    )
    assert reply["tarjetas"][0]["boton"]["ruta"] == "/tendencias/video"


def test_stopping_trading_is_a_button_not_an_action():
    reply = charla.answer(
        "detén el trading", readers={"trading": lambda: {"activo": True}}
    )
    assert reply["tarjetas"][0]["boton"]["ruta"] == "/trading/detener"
    assert "papel" in reply["texto"] and "ganancias" in reply["texto"]


def test_a_trend_idea_becomes_a_video_order_in_its_genre():
    order = charla.order({"titulo": "Qué pasa si…", "gancho": "Mira", "genero": "explicado3d",
                          "formato": "short", "senal": {"tema": "eclipse", "fuente": "Google Trends"}})  # fmt: skip
    assert order["style"] == "explicado-3d" and order["aspect"] == "9:16"
    assert "eclipse" in order["prompt"] and "hechos comprobables" in order["prompt"]

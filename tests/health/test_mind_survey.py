"""Salud mental: survey definition, scoring, crisis handling and the delayed reading."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.health import mind
from openjarvis.health.store import HealthStore


def _all(value_for=lambda item, scale: scale.first):
    answers = {p["id"]: 1 for p in mind.PICTURES}
    for s in mind.SCALES:
        for item, _ in s.items:
            answers[item] = value_for(item, s)
    return answers


def test_definition_has_pictures_first_and_every_item():
    d = mind.definition()
    first = d["sections"][0]
    assert [i["image"] for i in first["items"]] == [
        "no-suficiente",
        "pensar-demasiado",
        "encajar",
    ]
    assert all(
        i["kind"] == "picture" and len(i["options"]) == 4 for i in first["items"]
    )
    keys = [s["key"] for s in d["sections"]]
    assert keys == [
        "inicio",
        "phq9",
        "gad7",
        "rses",
        "rrsb",
        "pswq3",
        "auth",
        "ucla3",
        "abiertas",
    ]
    assert d["count"] == 3 + 9 + 7 + 10 + 5 + 3 + 12 + 3 + 4
    assert all(src["cite"] for src in d["sources"])


def test_published_cutoffs():
    low = mind.score(_all())
    by = {s["key"]: s for s in low["scales"]}
    assert by["phq9"]["score"] == 0 and by["phq9"]["band"] == "minimo"
    assert by["gad7"]["score"] == 0
    # Rosenberg: all "Muy en desacuerdo" = 5 + reversed 5x4 = 25 -> baja
    assert by["rses"]["score"] == 25 and by["rses"]["band"] == "baja"
    high = mind.score(_all(lambda item, s: s.first + len(s.options) - 1))
    hb = {s["key"]: s for s in high["scales"]}
    assert hb["phq9"]["score"] == 27 and hb["phq9"]["band"] == "grave"
    assert hb["gad7"]["score"] == 21 and hb["gad7"]["band"] == "grave"
    assert hb["ucla3"]["score"] == 9 and hb["ucla3"]["band"] == "alta"
    phq_10 = _all()
    phq_10.update({"phq9_1": 3, "phq9_2": 3, "phq9_3": 3, "phq9_4": 1})
    assert {s["key"]: s for s in mind.score(phq_10)["scales"]}["phq9"][
        "band"
    ] == "moderado"


def test_authenticity_subscales():
    answers = _all(
        lambda item, s: (
            7 if item in ("auth_3", "auth_4", "auth_7", "auth_10") else s.first
        )
    )
    auth = {s["key"]: s for s in mind.score(answers)["scales"]}["auth"]
    subs = {x["key"]: x for x in auth["subscales"]}
    assert subs["influencia"]["score"] == 28 and subs["influencia"]["band"] == "alta"
    assert subs["vivir"]["score"] == 4 and auth["band"] == "baja"


def test_incomplete_scale_is_not_scored_and_bad_values_are_dropped():
    answers = mind.clean_answers(
        {"phq9_1": 9, "gad7_1": "2", "nope": 1, "open_cambio": "  dormir  mejor "}
    )
    assert answers == {"gad7_1": 2, "open_cambio": "dormir mejor"}
    gad = {s["key"]: s for s in mind.score(answers)["scales"]}["gad7"]
    assert gad["score"] is None and gad["answered"] == 1


def test_crisis_from_item_nine_or_words():
    answers = _all()
    assert not mind.score(answers)["crisis"]
    assert mind.score({**answers, "phq9_9": 1})["crisis"]
    assert mind.score({**answers, "open_vueltas": "a veces quiero morir"})["crisis"]
    assert "911" in mind.crisis_text()


def test_reading_falls_back_to_code_and_uses_the_engine_when_there():
    answers = _all(lambda item, s: s.first + len(s.options) - 1)
    scores = mind.score(answers)
    text, by = mind.write_reading(
        scores, answers, generate=lambda **kw: (_ for _ in ()).throw(RuntimeError())
    )
    assert by == "codigo" and "profesional" in text and "Para esta semana" in text

    class Res:
        content = "**Lo que veo** " + "x" * 120

    seen = {}

    def fake(**kw):
        seen.update(kw)
        return Res()

    text, by = mind.write_reading(
        scores, {**answers, "open_cambio": "dormir mejor"}, generate=fake
    )
    assert by == "ia" and text.startswith("**Lo que veo**")
    assert "dormir mejor" in seen["messages"][1]["content"]
    assert "no eres un clínico" in seen["messages"][0]["content"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from openjarvis.server import health_routes

    store = HealthStore(tmp_path / "salud.db")
    monkeypatch.setattr(health_routes, "_store", lambda: store)
    monkeypatch.setattr(
        mind, "write_reading", lambda scores, answers: ("Lectura de prueba.", "ia")
    )
    app = FastAPI()
    app.include_router(health_routes.router)
    return TestClient(app)


def test_result_waits_then_arrives(client, monkeypatch):
    monkeypatch.setenv("SERGIO_MIND_DELAY", "1800")
    sent = client.post("/v1/healthdata/mind/surveys", json={"answers": _all()}).json()
    assert sent["status"] == "waiting" and "scores" not in sent
    assert 1790 < sent["ready_at"] - time.time() <= 1800
    early = client.get(f"/v1/healthdata/mind/surveys/{sent['id']}").json()
    assert (
        early["status"] == "waiting"
        and "reading" not in early
        and "scores" not in early
    )

    monkeypatch.setenv("SERGIO_MIND_DELAY", "0")
    now = client.post(
        "/v1/healthdata/mind/surveys",
        json={"answers": {**_all(), "open_cambio": "más calma"}},
    ).json()
    done = client.get(f"/v1/healthdata/mind/surveys/{now['id']}").json()
    assert done["status"] == "ready" and done["reading"] == "Lectura de prueba."
    assert done["answers"] == {"open_cambio": "más calma"} and done["sources"]
    listed = client.get("/v1/healthdata/mind/surveys").json()["surveys"]
    assert [s["status"] for s in listed] == ["ready", "waiting"]
    assert client.delete(f"/v1/healthdata/mind/surveys/{now['id']}").json() == {
        "ok": True
    }


def test_crisis_shows_at_once(client, monkeypatch):
    monkeypatch.setenv("SERGIO_MIND_DELAY", "1800")
    sent = client.post(
        "/v1/healthdata/mind/surveys", json={"answers": {**_all(), "phq9_9": 2}}
    ).json()
    assert sent["crisis"] and "911" in sent["crisis_text"] and sent["professional"]


def test_empty_survey_is_refused(client):
    assert (
        client.post(
            "/v1/healthdata/mind/surveys", json={"answers": {"pic_pensar": 2}}
        ).status_code
        == 400
    )


def test_short_survey_is_twelve_questions_with_the_safety_item():
    d = mind.definition("corta")
    assert d["variant"] == "corta" and d["count"] == 12
    assert [s["key"] for s in d["sections"]] == [
        "inicio",
        "phq2",
        "gad2",
        "ucla3",
        "abiertas",
    ]
    ids = [i["id"] for s in d["sections"] for i in s["items"]]
    assert "phq9_9" in ids  # the safety question is never dropped
    assert len(ids) == len(set(ids))
    assert [v["key"] for v in d["variants"]] == ["corta", "larga"]
    assert [v["count"] for v in d["variants"]] == [12, 56]
    assert mind.definition("whatever")["variant"] == "larga"


def test_two_item_screeners_use_the_published_cutoff_of_three():
    base = {p["id"]: 1 for p in mind.PICTURES}
    base.update({"ucla3_1": 1, "ucla3_2": 1, "ucla3_3": 1, "phq9_9": 0})
    low = mind.score(
        {**base, "phq9_1": 1, "phq9_2": 1, "gad7_1": 1, "gad7_2": 0}, "corta"
    )
    by = {s["key"]: s for s in low["scales"]}
    assert by["phq2"]["score"] == 2 and by["phq2"]["band"] == "minimo"
    assert by["gad2"]["score"] == 1 and not mind.needs_professional(low)
    assert low["variant"] == "corta"
    high = mind.score(
        {**base, "phq9_1": 2, "phq9_2": 1, "gad7_1": 0, "gad7_2": 0}, "corta"
    )
    assert {s["key"]: s for s in high["scales"]}["phq2"]["band"] == "positivo"
    assert mind.needs_professional(high)
    gad = mind.score(
        {**base, "phq9_1": 0, "phq9_2": 0, "gad7_1": 2, "gad7_2": 1}, "corta"
    )
    assert mind.needs_professional(gad)


def test_short_survey_still_raises_the_alarm_on_item_nine():
    answers = {p["id"]: 0 for p in mind.PICTURES}
    answers.update({"phq9_1": 0, "phq9_2": 0, "phq9_9": 1, "gad7_1": 0, "gad7_2": 0})
    assert mind.score(answers, "corta")["crisis"]


def test_the_short_reading_says_it_is_the_short_one():
    answers = {p["id"]: 1 for p in mind.PICTURES}
    answers.update({"phq9_1": 1, "phq9_2": 1, "phq9_9": 0, "gad7_1": 1, "gad7_2": 1})
    answers.update({"ucla3_1": 1, "ucla3_2": 1, "ucla3_3": 1})
    scores = mind.score(answers, "corta")
    assert "versión CORTA" in mind.reading_prompt(scores, answers)
    assert "versión CORTA" not in mind.reading_prompt(
        mind.score(_all(), "larga"), _all()
    )


def test_both_variants_travel_through_the_api(client, monkeypatch):
    monkeypatch.setenv("SERGIO_MIND_DELAY", "0")
    assert client.get("/v1/healthdata/mind/survey?variant=corta").json()["count"] == 12
    assert client.get("/v1/healthdata/mind/survey").json()["count"] == 56
    answers = {p["id"]: 1 for p in mind.PICTURES}
    answers.update({"phq9_1": 1, "phq9_2": 1, "gad7_1": 1, "gad7_2": 1})
    answers.update({"ucla3_1": 1, "ucla3_2": 1, "ucla3_3": 1})
    sent = client.post(
        "/v1/healthdata/mind/surveys", json={"answers": answers, "variant": "corta"}
    ).json()
    assert sent["variant"] == "corta"
    done = client.get(f"/v1/healthdata/mind/surveys/{sent['id']}").json()
    assert done["status"] == "ready" and done["variant"] == "corta"
    assert {s["key"] for s in done["scores"]["scales"]} == {"phq2", "gad2", "ucla3"}


def test_credits_name_institutions_but_ship_no_logo(client, tmp_path, monkeypatch):
    from openjarvis.health import credits as credits_mod

    monkeypatch.setattr(credits_mod, "logos_dir", lambda: tmp_path / "instituciones")
    mente = client.get("/v1/healthdata/credits?scope=mente").json()
    names = {i["name"] for s in mente["studies"] for i in s["institutions"]}
    assert {"Universidad de Columbia", "Universidad de Chicago"} <= names
    assert not mente["logos_added_by_owner"]
    assert (
        "no tiene relación" in mente["notice"]
        and "permiso por escrito" in mente["notice"]
    )
    assert all(
        s["url"].startswith("https://doi.org/") or not s["url"]
        for s in mente["studies"]
    )
    gym = client.get("/v1/healthdata/credits?scope=gimnasio").json()
    topics = {s["topic"] for s in gym["studies"]}
    assert "Dual N-Back" in topics and "Símbolos y dígitos" in topics
    # Harvard was wrongly credited before: it is not an institution here.
    assert "Harvard" not in str(gym) and "Harvard" not in str(mente)
    assert client.get("/v1/healthdata/credits?scope=otra").status_code == 400
    assert client.get("/v1/healthdata/instituciones/columbia/logo").status_code == 404


def test_a_logo_the_owner_added_is_shown_and_nothing_else_is_served(
    client, tmp_path, monkeypatch
):
    from openjarvis.health import credits as credits_mod

    folder = tmp_path / "instituciones"
    folder.mkdir()
    (folder / "columbia.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    (folder / "secreto.png").write_bytes(b"x")
    monkeypatch.setattr(credits_mod, "logos_dir", lambda: folder)
    mente = client.get("/v1/healthdata/credits?scope=mente").json()
    assert mente["logos_added_by_owner"]
    shown = {i["key"]: i["logo"] for s in mente["studies"] for i in s["institutions"]}
    assert shown["columbia"] and not shown["michigan"]
    assert (
        client.get("/v1/healthdata/instituciones/columbia/logo").headers["content-type"]
        == "image/png"
    )
    assert client.get("/v1/healthdata/instituciones/secreto/logo").status_code == 404
    assert client.get(
        "/v1/healthdata/instituciones/..%2F..%2Fetc/logo"
    ).status_code in (404, 422)


def test_the_real_reading_goes_through_gemini_not_a_broken_engine_call(monkeypatch):
    # The default path used to call an engine with chat dicts and no model:
    # it always failed and every reading was the code template.
    import openjarvis.coach.brain as brain

    answers = _all(lambda item, s: s.first)
    scores = mind.score(answers)
    seen = {}

    def ask(prompt, **kw):
        seen.update(prompt=prompt, **kw)
        return kw["check"]({"lectura": "**Lo que veo** " + "y" * 120})

    monkeypatch.setattr(brain, "ask", ask)
    text, by = mind.write_reading(scores, answers)
    assert by == "ia" and text.startswith("**Lo que veo**")
    assert "no eres un clínico" in seen["system"] and '"lectura"' in seen["prompt"]
    import pytest as _pytest

    with _pytest.raises(ValueError):
        seen["check"]({"lectura": "corto"})

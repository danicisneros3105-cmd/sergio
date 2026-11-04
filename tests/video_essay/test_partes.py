"""A video made in parts (owner, 4 Nov 2026: «más esfuerzo… más interesantes…
que divida la creación de videos por partes»)."""

from __future__ import annotations

import json

from openjarvis.video_essay import job as J
from openjarvis.video_essay import modes, partes

GOOD_HOOK = "En 1998 un becario borró el 40 % de los datos de la NASA."
DRY = (
    "Hoy en día muchas cosas cambian. Es importante destacar que todo evoluciona. "
    "Las personas piensan de formas distintas. Las ideas se mueven con el tiempo. "
    "Cada época tiene su estilo propio."
)
FIRM = (
    "Marta Ruiz tenía 3 días para recuperar el archivo. Probó con el respaldo de 1997, "
    "pero estaba vacío. Entonces llamó a Pedro Díaz, que guardaba una copia en casa. "
    "¿Qué había en esa copia? Lo sabrá al final."
)


SAFE_REWRITE = (
    "Nada cambia igual para todos. Las personas ven las cosas de formas distintas, "
    "pero las ideas siguen moviéndose con el tiempo. ¿por qué importa? "
    "Cada época tiene su propio estilo y obliga a mirar lo conocido desde otro ángulo."
)


def script(*texts):
    return {
        "title": "t",
        "narration": "voice",
        "beats": [
            {"beat": f"b{i}", "text": t, "delivery": {}} for i, t in enumerate(texts)
        ],
    }


def test_a_hook_must_fit_a_breath_and_promise_something():
    assert partes.hook_problems(GOOD_HOOK) == []
    long = "Hoy vamos a hablar de un tema muy interesante que lleva años dando que hablar a mucha gente"
    found = partes.hook_problems(long)
    assert any("palabras" in p for p in found) and any("concreto" in p for p in found)


def test_dry_stock_text_scores_low_and_concrete_text_scores_high():
    assert partes.score(DRY) < partes.WEAK_BELOW <= partes.score(FIRM)
    problems = partes.part_problems(DRY)
    assert any("relleno" in p for p in problems)
    assert any("sin un dato" in p for p in problems)
    # the same text always gets the same score (rules, not a model)
    assert partes.score(DRY) == partes.score(DRY)


def test_the_script_is_split_at_the_directors_beats():
    sc = script(GOOD_HOOK, FIRM, FIRM, DRY, "Ese día aprendió una cosa: guarde copias.")
    parts = partes.split(sc, 60)
    assert parts[0].name == "Gancho" and parts[0].beats == [0]
    assert parts[-1].name == "Remate" and parts[-1].beats == [4]
    assert sorted(i for p in parts for i in p.beats) == [0, 1, 2, 3, 4]  # nothing lost
    long = partes.split(script(*([FIRM] * 30)), 600)
    assert len(long) > 3  # a long video has several development parts


def test_only_a_better_rewrite_of_a_weak_part_is_kept():
    sc = script(GOOD_HOOK, DRY, "Guarde copias: Marta lo aprendió en 1998.")
    asked = []

    def good(prompt, **kw):
        asked.append(prompt)
        return json.dumps({"beats": [{"text": SAFE_REWRITE}]})

    better, report = partes.improve(sc, good, passes=1, seconds=60)
    assert better["beats"][1]["text"] == SAFE_REWRITE and report["rewritten"] == 1
    assert report["after"] > report["before"]
    assert sc["beats"][1]["text"] == DRY  # the input is untouched
    assert "Keep EVERY name, number" in asked[0] and "stock phrases" in asked[0]
    assert better["text"].startswith(GOOD_HOOK)

    def worse(prompt, **kw):
        return json.dumps({"beats": [{"text": DRY + " " + DRY}]})

    same, rep = partes.improve(sc, worse, passes=2, seconds=60)
    assert same["beats"] == sc["beats"] and rep["rewritten"] == 0

    def broken(prompt, **kw):
        raise RuntimeError("sin cuota")

    kept, rep2 = partes.improve(sc, broken, passes=1, seconds=60)
    assert kept["beats"] == sc["beats"] and rep2["rewritten"] == 0


def test_a_rewrite_that_changes_the_length_or_the_count_is_refused():
    sc = script(GOOD_HOOK, DRY, "Fin: guarde copias, Marta.")
    short = lambda p, **k: json.dumps({"beats": [{"text": "Muy corto con 7 datos."}]})  # noqa: E731
    assert partes.improve(sc, short, passes=1)[1]["rewritten"] == 0
    two = lambda p, **k: json.dumps({"beats": [{"text": FIRM}, {"text": FIRM}]})  # noqa: E731
    assert partes.improve(sc, two, passes=1)[1]["rewritten"] == 0


def test_the_effort_follows_the_mode_and_test_makes_no_calls(tmp_path):
    sc = script(GOOD_HOOK, DRY, "Fin: guarde copias, Marta.")
    calls = []

    def ask(p, **k):
        calls.append(p)
        return json.dumps({"beats": [{"text": SAFE_REWRITE}]})

    job = J.create({"topic": "x", "seconds": 60}, root=tmp_path)
    out = J._by_parts(job, sc, {"seconds": 60}, modes.get("test"), ask)
    assert out is sc and not calls and job.state()["partes"]["rewritten"] == 0
    out = J._by_parts(job, sc, {"seconds": 60}, modes.get("basic"), ask)
    assert out["beats"][1]["text"] == SAFE_REWRITE and len(calls) == 1
    # a script the owner wrote is never rewritten
    assert J._by_parts(job, sc, {"script": "mío"}, modes.get("post"), ask) is sc
    assert "interés" in partes.line(job.state()["partes"])


def test_the_summary_says_what_was_done():
    text = J.summary(
        {
            "status": "listo",
            "title": "V",
            "result": {"shots": 4, "url": "/v"},
            "partes": {
                "before": 52,
                "after": 81,
                "rewritten": 2,
                "parts": [{"name": "Gancho"}] * 4,
            },
        }
    )
    assert "4 partes" in text and "52" in text and "81" in text

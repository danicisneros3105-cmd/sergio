"""Automations that read like a careful person made them (owner, 4 Nov 2026)."""

from __future__ import annotations

import json

from openjarvis.automatiza import canales, humano


def test_review_finds_what_gives_a_machine_away():
    assert humano.review("Gracias, lo vi ayer y me encantó el segundo punto.") == []
    robot = "Espero que este mensaje le encuentre bien. ¡Gracias! ¡Genial! ¡Increíble! 🙂 #a #b #c #d #e"
    found = " | ".join(humano.review(robot))
    for needle in ("plantilla", "emojis", "exclamaciones", "etiquetas"):
        assert needle in found
    same = humano.review(
        "Gracias por pasarte por aquí", ["Gracias por pasarte y comentar"]
    )
    assert any("empieza igual" in p for p in same)
    assert any("repite" in p for p in humano.review("Es muy muy bueno"))


def test_polish_fixes_once_and_keeps_only_a_better_text():
    bad = "Espero que este mensaje le encuentre bien. No dude en contactarme."
    asked = []

    def good(prompt, **kw):
        asked.append(prompt)
        return "Vi su oferta y me interesa. Le cuento en tres líneas cómo puedo ayudar."

    out = humano.polish(bad, good, ["Hola equipo, vi su oferta"])
    assert out.startswith("Vi su oferta") and len(asked) == 1
    assert "frases de plantilla" in asked[0] and "Do not add emojis" in asked[0]
    # fine text: no call at all
    humano.polish("Lo vi ayer y me gustó.", good)
    assert len(asked) == 1
    # a rewrite that is not better, is JSON, or is absurdly long changes nothing
    assert humano.polish(bad, lambda p, **k: bad) == bad
    assert humano.polish(bad, lambda p, **k: '{"x": 1}') == bad
    assert humano.polish(bad, lambda p, **k: "x" * 500) == bad

    def boom(p, **k):
        raise RuntimeError("sin cuota")

    assert humano.polish(bad, boom) == bad
    assert humano.polish(bad, None) == bad


def test_a_due_time_drifts_a_little_and_the_same_way_every_time():
    due = 1_800_000_000.0
    a = humano.stagger(due, 3, "abc")
    assert a == humano.stagger(due, 3, "abc")  # reproducible
    assert a != humano.stagger(due, 3, "xyz")  # another schedule, another drift
    assert abs(a - due) <= 45 * 60 + 60  # never far
    assert int(a) % 60 != 0  # never on the round minute
    # a short interval drifts proportionally less
    assert abs(humano.stagger(due, 1, "abc") - due) <= 0.12 * 3600 + 60
    spread = {round(humano.stagger(due + 3600 * i, 6, "s")) % 3600 for i in range(20)}
    assert len(spread) > 10  # not clockwork


def test_ten_replies_do_not_all_open_the_same_way(tmp_path):
    comments = [{"id": str(i), "texto": f"comentario {i}"} for i in range(4)]
    batch = {
        "replies": [
            {
                "id": str(i),
                "reply": "Gracias por tu valioso comentario, me alegra mucho.",
            }
            for i in range(4)
        ]
    }
    plain_calls = []

    def ask(prompt, **kw):
        if "Rewrite this text" in prompt:
            plain_calls.append(prompt)
            opener = ("Qué bien", "Justo eso buscaba", "Pues gracias", "Me alegra")[
                len(plain_calls) - 1
            ]
            return f"{opener} que lo veas, comentario número {len(plain_calls)}."
        return json.dumps(batch)

    out = canales.draft_replies(comments, ask, home=tmp_path)
    assert len(out) == 4
    assert plain_calls  # the stock phrase was fixed
    assert not any("valioso" in d["respuesta"] for d in out)

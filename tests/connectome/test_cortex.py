"""The human brain at Sergio's base (connectome/cortex.py): it perceives,
decides how to answer, and learns from what the owner says next."""

from __future__ import annotations

import numpy as np
import pytest

from openjarvis.connectome import cortex
from openjarvis.connectome.cortex import STRATEGIES, HumanBrain


class Clock:
    def __init__(self) -> None:
        self.now = 1_700_000_000.0

    def __call__(self) -> float:
        return self.now

    def tick(self, s: float) -> None:
        self.now += s


@pytest.fixture
def brain(tmp_path):
    return HumanBrain(tmp_path / "humano", clock=Clock(), terry=False)


def turn(b: HumanBrain, text: str, answer: str = "respuesta", channel: str = "chat"):
    t = b.think(text, channel)
    b.clock.tick(3)
    b.outcome(text, answer, channel)
    b.clock.tick(30)
    return t


def test_innate_guess_before_any_learning(brain):
    assert brain.think("hola sergio", "chat").strategy == "reflejo"
    big = brain.think(
        "diseña la arquitectura completa de mi app con pagos, usuarios, notificaciones "
        "y un plan de despliegue paso a paso con presupuesto detallado",
        "chat",
    )
    assert STRATEGIES.index(big.strategy) >= 2


def test_a_plain_turn_adds_nothing_to_the_prompt(brain):
    assert brain.think("hola sergio", "chat").broadcast() == ""


def test_explain_better_moves_it_deeper_for_requests_it_never_saw(brain):
    first = turn(brain, "explícame cómo funciona la inflación")
    assert first.strategy == "reflejo"
    brain.think("explícame mejor, más a fondo", "chat")
    brain.clock.tick(30)
    later = brain.think("explícame cómo funciona la bolsa", "chat")
    assert STRATEGIES.index(later.strategy) > STRATEGIES.index(first.strategy)
    assert later.learned
    assert brain.stats_["arrepentimientos"] == 1


def test_explain_better_answers_again_deeper_on_the_same_topic(brain):
    first = turn(brain, "explícame cómo funciona la inflación")
    again = brain.think("explícame mejor", "chat")
    assert STRATEGIES.index(again.strategy) == STRATEGIES.index(first.strategy) + 1
    assert again.continuing and "inflación" in again.broadcast()


def test_internal_prompts_are_not_framed(brain):
    assert brain.think("plan " * 500, "chat").broadcast() == ""


def test_shorter_please_moves_it_toward_a_reflex(brain):
    text = "analiza y compara estrategias de inversión para mi ahorro con detalle"
    first = turn(brain, text)
    assert first.strategy != "reflejo"
    for _ in range(3):
        brain.think("más corto, al grano", "chat")
        brain.clock.tick(30)
        t = turn(brain, text)
    assert STRATEGIES.index(t.strategy) < STRATEGIES.index(first.strategy)


def test_praise_is_dopamine(brain):
    turn(brain, "qué hora es en Madrid")
    before = brain.stats_["recompensas"]
    brain.think("gracias, perfecto", "chat")
    assert brain.stats_["recompensas"] == before + 1
    assert brain.mods["dopamina"] > 0


def test_urgency_and_danger_are_felt(brain):
    hurry = brain.think("urgente: dame el número del banco ya mismo", "chat")
    assert hurry.affect.urgent and hurry.strategy == "reflejo"
    assert "prisa" in hurry.broadcast()
    danger = brain.think(
        "me duele mucho, dolor en el pecho y no puedo respirar", "chat"
    )
    assert danger.affect.danger
    assert "emergencias" in danger.broadcast()


def test_a_correction_teaches_caution_on_that_topic(brain):
    text = "cuál es la dosis de ibuprofeno para mi hijo"
    turn(brain, text)
    brain.think("no, eso no es así", "chat")
    brain.clock.tick(30)
    again = brain.think(text + " de cinco años", "chat")
    assert again.affect.caution > 0.3
    assert "Cuidado" in again.broadcast()


def test_working_memory_keeps_the_topic_for_a_follow_up(brain):
    turn(brain, "quiero abrir una cafetería en Cuenca")
    follow = brain.think("¿y cuánto cuesta el local?", "chat")
    assert follow.continuing
    assert "cafetería" in follow.broadcast()


def test_the_cerebellum_learns_how_long_it_takes(brain):
    text = "resume este artículo largo sobre economía"
    first = brain.think(text, "chat")
    a = STRATEGIES.index(first.strategy)
    for _ in range(8):
        t = brain.think(text, "chat")
        brain.clock.tick(15)
        brain.outcome(text, "ok", "chat")
        brain.clock.tick(60)
    predicted = brain.cerebellum.predict(t.x_idx, t.x_val, a)
    assert abs(predicted - 15) < abs(cortex.TYPICAL_S[first.strategy] - 15)


def test_long_internal_prompts_are_not_the_owner(brain):
    long = "contexto " * 400
    t = brain.think(long, "chat")
    assert not t.percept.owner
    assert brain.stats_["turnos"] == 0


def test_sleep_turns_repeated_episodes_into_concepts_and_downscales(brain):
    turn(brain, "explícame cómo funciona la inflación")
    brain.think("explícame mejor", "chat")
    go_before = float(np.abs(brain.ganglia.go).sum())
    episodes = [
        {"t": brain.clock(), "user": u, "channel": "chat"}
        for u in (
            "precio del café en Cuenca",
            "marca de café para la tienda",
            "café de especialidad y su marca",
        )
    ]
    night = brain.sleep(episodes)
    assert night["conceptos"] >= 1
    assert "cafe" in brain.cortex.concepts
    assert "marca" in brain.cortex.concepts["cafe"]["junto"]
    assert float(np.abs(brain.ganglia.go).sum()) < go_before
    later = brain.think("quiero una nueva marca de café", "chat")
    assert "café" in later.broadcast() or "cafe" in later.broadcast()


def test_what_it_learned_survives_a_restart(tmp_path):
    clock = Clock()
    b = HumanBrain(tmp_path / "h", clock=clock, terry=False)
    turn(b, "explícame cómo funciona la inflación")
    b.think("explícame mejor, más a fondo", "chat")
    b.save(force=True)
    again = HumanBrain(tmp_path / "h", clock=clock, terry=False)
    assert again.stats_["arrepentimientos"] == 1
    assert np.array_equal(again.ganglia.go, b.ganglia.go)
    clock.tick(60)
    t = again.think("explícame cómo funciona la bolsa", "chat")
    assert t.strategy != "reflejo"


def test_the_measured_proof_beats_the_innate_guess_on_unseen_requests():
    p = cortex.prove(rounds=3)
    first, last = p["rondas"][0]["acierto"], p["rondas"][-1]["acierto"]
    assert last > first
    assert last > p["azar"]
    assert p["dopamina"]["arrepentimientos"] > 0
    assert p["conceptos"]


def test_switched_off_with_the_rest_of_the_mind(monkeypatch):
    monkeypatch.setenv("SERGIO_CEREBRO", "0")
    assert cortex.think("hola") is None
    assert cortex.workspace("hola") == ""


def test_the_chat_route_takes_the_brains_decision(monkeypatch):
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from openjarvis.core.config import JarvisConfig
    from openjarvis.server.app import create_app

    seen = []
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["gemini-3.8-flash"]

    def generate(messages, *, model, **kw):
        seen.append(model)
        return {
            "content": "listo",
            "usage": {},
            "model": model,
            "finish_reason": "stop",
        }

    engine.generate.side_effect = generate
    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    client = TestClient(create_app(engine, "gemini-3.8-flash", config=cfg))

    def ask(text):
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini-3.8-flash",
                "messages": [{"role": "user", "content": text}],
            },
        )
        assert r.status_code == 200
        return seen[-1]

    # At birth a short «explícame…» is a quick answer (low effort)...
    assert ask("explícame cómo funciona la inflación") == "gemini-3.8-flash@low"
    ask("explícame mejor, más a fondo")
    for topic in ("una hipoteca", "el dólar", "la bolsa"):
        ask(f"explícame cómo funciona {topic}")
        ask("explícame mejor, más a fondo")
    # ...this owner wants them thought through: a new one now thinks more.
    assert ask("explícame cómo funciona el euro") == "gemini-3.8-flash@medium"
    assert cortex.get_human().stats()["arrepentimientos"] >= 4

"""The fixed team: Rihno, Manchas, Hous and Tennessee."""

from __future__ import annotations

import threading

import pytest

from openjarvis.nodes import team
from openjarvis.nodes.store import CAST_LOOK, NodeError, NodeStore
from openjarvis.nodes.worker import NodeWorker


def _worker(tmp_path, answers, prompts=None, gate=None):
    def runner(prompt, tools, budget, on_tool):
        if prompts is not None:
            prompts.append(prompt)
        if gate is not None:
            gate.wait(5)
        return (answers.pop(0) if answers else "Hecho."), 1

    store = NodeStore(tmp_path)
    store.ensure_team()
    return NodeWorker(store, runner=runner, ask=lambda p, **k: {}), store


def test_the_four_are_always_there_in_order_and_cannot_go(tmp_path):
    store = NodeStore(tmp_path)
    made = store.ensure_team()
    assert [n.name for n in made] == ["Rihno", "Manchas", "Hous", "Tennessee"]
    assert store.ensure_team() == []  # a second start creates nothing
    nodes = store.all()
    assert [n.team for n in nodes] == list(team.ORDER)
    assert [n.avatar for n in nodes] == [
        CAST_LOOK["rhino"],
        CAST_LOOK["dalmatian"],
        CAST_LOOK["glove"],
        CAST_LOOK["orb"],
    ]
    rihno = nodes[0]
    assert rihno.primary and not any(n.primary for n in nodes[1:])
    # each one greets in its own voice
    assert "Rihno" in store.messages(rihno.id)[0]["text"]
    with pytest.raises(NodeError, match="siempre está"):
        store.delete(rihno.id)
    with pytest.raises(NodeError, match="nombre no cambia"):
        store.update(rihno.id, name="Otro")
    store.update(rihno.id, tone="formal")  # its voice is its own
    assert store.get(rihno.id).tone == "cercano"


def test_every_turn_carries_the_whole_character(tmp_path):
    prompts: list[str] = []
    worker, store = _worker(tmp_path, ["Listo."], prompts)
    tennessee = store.team_node("tennessee")
    worker.send(tennessee.id, "¿Por qué pierdo dinero?")
    worker.wait(tennessee.id)
    prompt = prompts[0]
    for piece in (
        "QUIÉN ERES — Tennessee",
        "CÓMO TRABAJAS, SIEMPRE EN ESTE ORDEN",
        "LO QUE NUNCA HACES",
        "Inventar cifras",
        "Rihno (orquestador)",
        '<equipo para="Nombre">',
    ):
        assert piece in prompt


def test_rihno_hands_work_to_hous_and_gets_the_answer_back(tmp_path):
    prompts: list[str] = []
    worker, store = _worker(
        tmp_path,
        [
            'Ya lo reparto. <equipo para="Hous">Logo para la tienda, tinta y crudo.</equipo>',
            "Tres versiones en su carpeta de diseño.",
            "Señor, Hous dejó tres logos listos. ¿Aprobar?",
        ],
        prompts,
    )
    rihno, hous = store.team_node("rihno"), store.team_node("hous")
    worker.send(rihno.id, "Necesito una marca para la tienda.")
    for _ in range(3):
        worker.wait(rihno.id)
        worker.wait(hous.id)
    hous_said = [m for m in store.messages(hous.id) if m["role"] == "user"]
    assert hous_said[-1]["text"].startswith("Logo para la tienda")
    back = [m["text"] for m in store.messages(rihno.id) if m["role"] == "node"]
    assert "Tres versiones en su carpeta de diseño." in back
    assert back[-1].startswith("Señor, Hous dejó tres logos listos")
    assert "<equipo" not in " ".join(back)  # the tag never reaches the owner
    assert "Hous terminó lo que le encargaste" in prompts[-1]


def test_hand_offs_stop_bouncing(tmp_path):
    loop = '<equipo para="Manchas">Otra vuelta.</equipo>'
    worker, store = _worker(tmp_path, [loop] * 10)
    rihno = store.team_node("rihno")
    worker.send(rihno.id, "Empieza")
    for _ in range(6):
        for key in team.ORDER:
            worker.wait(store.team_node(key).id)
    turns = sum(
        1
        for key in team.ORDER
        for a in store.activity(store.team_node(key).id)
        if a["kind"] == "started"
    )
    assert turns <= 1 + team_depth_rounds()


def team_depth_rounds() -> int:
    from openjarvis.nodes.worker import TEAM_DEPTH

    return TEAM_DEPTH * 2  # a hand-off and its answer per level


def test_cancel_stops_the_action_but_keeps_the_node_available(tmp_path):
    gate = threading.Event()
    worker, store = _worker(tmp_path, ["Resultado tardío."], gate=gate)
    hous = store.team_node("hous")
    worker.send(hous.id, "Diseña algo largo")
    worker.send(hous.id, "Y luego otra cosa")
    assert worker.cancel(hous.id) is True
    gate.set()
    worker.wait(hous.id)
    node = store.get(hous.id)
    assert node.status == "idle"  # not paused, unlike «Detener»
    said = [m["text"] for m in store.messages(hous.id) if m["role"] == "node"]
    assert "Resultado tardío." not in said
    kinds = [a["kind"] for a in store.activity(hous.id)]
    assert "cancelled" in kinds and "discarded" in kinds
    # and it works again right away
    worker.send(hous.id, "Ahora sí")
    worker.wait(hous.id)
    assert store.get(hous.id).status == "idle"
    assert worker.cancel(hous.id) is False  # nothing left to cancel


def test_names_are_forgiven_one_slip():
    assert team.by_name("Tenessee") is team.TENNESSEE
    assert team.by_name("rhino") is team.RIHNO
    assert team.by_name("HOUS") is team.HOUS
    assert team.by_name("Nadie") is None


def test_characters_describe_traits_not_real_people():
    text = " ".join(team.character_block(m) for m in team.TEAM).lower()
    for name in ("tom cruise", "brad pitt", "house", "malcolm", "andrea", "sachs"):
        assert name not in text

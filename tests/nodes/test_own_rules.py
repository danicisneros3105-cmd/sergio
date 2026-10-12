"""The owner's own rules for a Node, and the automatic review of actions."""

from __future__ import annotations

import pytest

from openjarvis.nodes.own_rules import (
    blocked_categories,
    clean_rules,
    compile_rule,
    explain,
    prompt_lines,
    review,
)


@pytest.mark.parametrize(
    "text,effect,families",
    [
        ("Pídeme permiso antes de borrar archivos", "ask", ["borrar"]),
        ("Nunca publiques nada en redes sociales", "block", ["publicar"]),
        ("No compres nada sin preguntarme", "ask", ["comprar"]),
        ("No compres nada", "block", ["comprar"]),
        ("Avísame antes de enviar correos a clientes", "ask", ["enviar"]),
        ("Nunca ejecutes comandos en la terminal", "block", ["ejecutar"]),
        ("Never push to GitHub without asking", "ask", ["git"]),
    ],
)
def test_rules_in_plain_words_are_understood(text, effect, families):
    rule = compile_rule(text)
    assert rule["effect"] == effect
    assert rule["families"] == families
    assert explain(rule)


def test_a_rule_without_an_action_is_refused_with_help():
    with pytest.raises(ValueError, match="Diga el verbo"):
        compile_rule("Antes de comprobar facturas, pregúntame")


def test_review_catches_the_action_and_block_beats_ask():
    rules = [
        compile_rule("Pídeme permiso antes de borrar archivos"),
        compile_rule("Nunca publiques nada en redes sociales"),
    ]
    rm = review(
        rules, {"kind": "cli", "command": "rm -rf ./viejo"}, "Ejecutar rm -rf ./viejo"
    )
    assert rm is not None and rm["effect"] == "ask"
    post = review(
        rules, {"kind": "api", "name": "linkedin", "method": "POST", "path": "/posts"}
    )
    assert post is not None and post["effect"] == "block"
    delete = review(
        rules, {"kind": "api", "name": "drive", "method": "DELETE", "path": "/files/1"}
    )
    assert delete is not None and delete["text"].startswith("Pídeme")


def test_review_does_not_confuse_similar_words():
    rules = [
        compile_rule("No compres nada sin preguntarme"),
        compile_rule("Pídeme permiso antes de enviar mensajes"),
    ]
    assert (
        review(
            rules,
            {"kind": "cli", "command": "python comprobar.py"},
            "Comprobar facturas",
        )
        is None
    )
    assert (
        review(
            rules, {"kind": "api", "name": "x", "method": "GET", "path": "/environment"}
        )
        is None
    )
    assert (
        review(rules, {"kind": "api", "name": "x", "method": "GET", "path": "/pagina"})
        is None
    )


def test_quoted_words_are_matched_literally():
    rule = compile_rule("Nunca toques el repositorio «facturas-2026» ni hagas push")
    assert "facturas-2026" in rule["words"]
    assert (
        review([rule], {"kind": "cli", "command": "ls facturas-2026"})["effect"]
        == "block"
    )


def test_rules_reach_the_prompt_and_take_tools_away():
    rules = [compile_rule("Pídeme permiso antes de borrar archivos")]
    assert "borrar archivos" in prompt_lines(rules)
    assert blocked_categories(rules) == ["computer"]
    assert prompt_lines([]) == ""


def test_stored_rules_are_cleaned():
    raw = [
        {"text": "x" * 500, "effect": "maybe", "families": ["borrar", "hackear"]},
        {"text": ""},
        "basura",
    ]
    out = clean_rules(raw)
    assert len(out) == 1
    assert out[0]["effect"] == "ask" and out[0]["families"] == ["borrar"]
    assert len(out[0]["text"]) == 300


# -- inside a Node (the automatic review in the worker) -----------------------------


def _worker(tmp_path, answers):
    from openjarvis.nodes.store import NodeStore
    from openjarvis.nodes.worker import NodeWorker

    seen: list[tuple[str, list[str]]] = []

    def runner(prompt, tools, budget, on_tool):
        seen.append((prompt, list(tools)))
        return (answers.pop(0) if answers else "Hecho."), 1

    worker = NodeWorker(
        NodeStore(tmp_path), runner=runner, ask=lambda p, **k: {"presentacion": "Hola."}
    )
    return worker, seen


def test_a_forbidding_rule_blocks_an_allowed_action(tmp_path):
    worker, seen = _worker(tmp_path, ["<cli>python -c print(1)</cli>", "Listo."])
    node = worker.create("Dev")
    worker.store.update(node.id, rules={"cli": "allow"})
    worker.store.add_connection(node.id, "cli", {"name": "py", "command": "python"})
    worker.store.update(
        node.id, own_rules=[compile_rule("Nunca ejecutes comandos en la terminal")]
    )
    worker.send(node.id, "calcula")
    worker.wait(node.id)
    kinds = [a["kind"] for a in worker.store.activity(node.id)]
    assert "review" in kinds and "blocked" in kinds
    assert "Nunca ejecutes comandos" in seen[0][0]  # the Node was told too
    assert not worker.store.approvals(node.id)


def test_an_asking_rule_turns_an_allowed_action_into_an_approval(tmp_path):
    worker, _ = _worker(tmp_path, ["<cli>python borrar_viejos.py</cli>"])
    node = worker.create("Dev")
    worker.store.update(node.id, rules={"cli": "allow"})
    worker.store.add_connection(node.id, "cli", {"name": "py", "command": "python"})
    worker.store.update(
        node.id, own_rules=[compile_rule("Pídeme permiso antes de borrar archivos")]
    )
    worker.send(node.id, "limpia")
    worker.wait(node.id)
    items = worker.store.approvals(node.id)
    assert items and items[0]["action"]["command"] == "python borrar_viejos.py"
    assert worker.store.get(node.id).status == "waiting_approval"


def test_a_file_rule_takes_file_tools_out_of_the_nodes_own_hands(tmp_path):
    worker, seen = _worker(tmp_path, ["Hecho."])
    node = worker.create("Dev")  # computer: allow by default
    worker.store.update(
        node.id, own_rules=[compile_rule("Pídeme permiso antes de borrar archivos")]
    )
    worker.send(node.id, "ordena la carpeta")
    worker.wait(node.id)
    assert "file_write" not in seen[0][1]


def test_the_node_suggests_next_steps(tmp_path):
    worker, _ = _worker(
        tmp_path,
        [
            "Informe listo. <siguiente>Resume el informe en 5 puntos</siguiente>"
            "<siguiente>Prepara un borrador para el equipo</siguiente>"
        ],
    )
    node = worker.create("Analista")
    worker.send(node.id, "haz el informe")
    worker.wait(node.id)
    last = worker.store.messages(node.id)[-1]
    assert last["text"] == "Informe listo."
    assert last["suggestions"] == [
        "Resume el informe en 5 puntos",
        "Prepara un borrador para el equipo",
    ]

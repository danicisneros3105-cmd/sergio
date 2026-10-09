"""Cowork runs end to end with a fake planner and a fake step runner."""

from __future__ import annotations

import json
import threading

import pytest

from openjarvis.cowork.audit import AuditTrail
from openjarvis.cowork.scrutiny import TrustStore
from openjarvis.cowork.session import (
    ActionBudget,
    BudgetExhausted,
    CoworkEngine,
    step_status,
    steps_from_plan,
)

GOAL = "Comparar los 3 mejores portátiles para Blender y hacer una tabla"


def _plan(*steps):
    def planner(goal):
        return {"titulo": "Portátiles", "pasos": list(steps)}

    return planner


def _step(text, tools=("web_search",), where="fondo", check="comprobado", **extra):
    return {
        "paso": text,
        "herramientas": list(tools),
        "donde": where,
        "comprobar": check,
        **extra,
    }


class FakeRunner:
    def __init__(self, answers=None, cost=2):
        self.prompts = []
        self.answers = list(answers or [])
        self.cost = cost

    def __call__(self, prompt, tools, budget):
        self.prompts.append((prompt, tools, budget))
        answer = self.answers.pop(0) if self.answers else "TERMINADO: hecho"
        return answer, self.cost


@pytest.fixture()
def engine_factory(tmp_path):
    def make(planner, runner, **kw):
        sent = []
        engine = CoworkEngine(
            planner=planner,
            runner=runner,
            send_owner=lambda text: sent.append(text) or True,
            root=tmp_path / "cowork",
            trust=TrustStore(tmp_path / "trust.json"),
            **kw,
        )
        engine.sent = sent
        return engine

    return make


def test_budget_hard_cap():
    budget = ActionBudget(3)
    assert budget.spend(2) == 1
    with pytest.raises(BudgetExhausted):
        budget.spend(1)
    assert ActionBudget(10_000).limit == 500 and ActionBudget(0).limit == 1


def test_step_status_parsing():
    assert step_status("bla\nTERMINADO: tabla en C:\\x.xlsx") == (
        "done",
        "tabla en C:\\x.xlsx",
    )
    assert step_status("FALTA: precios")[0] == "more"
    assert step_status("NO POSIBLE: sin red")[0] == "impossible"
    assert step_status("algo")[0] == "unknown"


def test_plan_steps_with_dependencies():
    steps = steps_from_plan(
        {"pasos": [_step("a"), _step("b"), _step("c", depende_de=[1, 2]), {"paso": ""}]}
    )
    assert [s.text for s in steps] == ["a", "b", "c"] and steps[2].needs == [0, 1]


def test_run_completes_and_audits(engine_factory):
    runner = FakeRunner(["TERMINADO: 3 modelos", "TERMINADO: tabla.xlsx"])
    engine = engine_factory(
        _plan(
            _step("Buscar los mejores portátiles para Blender"),
            _step("Hacer una tabla de portátiles", ["file_write"]),
        ),
        runner,
    )
    run = engine.start(GOAL, wait=True)
    assert run.status == "done", run.to_dict()
    assert run.actions_used == 4 and run.summary == "tabla.xlsx"
    assert "modo Cowork" in runner.prompts[0][0] and "Ya hecho" in runner.prompts[1][0]
    trail = engine.audit(run.id)
    events = [e["event"] for e in trail.entries()]
    assert (
        events[0] == "started"
        and "planned" in events
        and events[-1] in ("finished", "notified")
    )
    assert trail.verify() == (True, None)
    assert any("empiezo" in m for m in engine.sent) and any(
        "tabla.xlsx" in m for m in engine.sent
    )
    saved = json.loads((engine.root / run.id / "run.json").read_text())
    assert saved["status"] == "done" and saved["progress"] == 1.0


def test_hard_cap_stops_the_run(engine_factory):
    runner = FakeRunner(cost=30)
    engine = engine_factory(
        _plan(*(_step(f"Buscar portátiles para Blender {i}") for i in range(4))), runner
    )
    run = engine.start(GOAL, max_actions=50, wait=True)
    assert run.status == "capped" and run.actions_used == 60
    assert [s.status for s in run.steps] == ["done", "done", "pending", "pending"]
    assert "tope de 50" in run.summary
    assert runner.prompts[1][2] == 20  # the second step only got what was left


def test_blocked_step_and_dependents_are_skipped(engine_factory):
    runner = FakeRunner()
    engine = engine_factory(
        _plan(
            _step("Hacer la tabla de portátiles", ["file_write"]),
            _step("Envía la tabla por WhatsApp a Juan", ["whatsapp_send"]),
            _step("Confirmar que Juan la recibió", ["web_search"], depende_de=[2]),
        ),
        runner,
    )
    run = engine.start(GOAL, wait=True)
    assert [s.status for s in run.steps] == ["done", "blocked", "skipped"]
    assert run.status == "partial" and len(runner.prompts) == 1


def test_screen_steps_are_left_for_the_desktop(engine_factory):
    engine = engine_factory(
        _plan(_step("Abrir la tabla en Excel", ["desktop_action"], where="pantalla")),
        FakeRunner(),
    )
    run = engine.start(GOAL, autonomy="autonomo", wait=True)
    assert (
        run.steps[0].status == "skipped" and "Sergio Escritorio" in run.steps[0].result
    )


def test_owner_approval_flow(engine_factory):
    runner = FakeRunner()
    engine = engine_factory(
        _plan(_step("Compra el portátil más barato", ["web_search"])), runner
    )
    import queue

    box = queue.Queue()
    run = engine.start(GOAL, listener=box)
    for _ in range(1000):
        if run.status == "waiting_approval":
            break
        threading.Event().wait(0.01)
    assert run.status == "waiting_approval" and run.to_dict()["waiting"] == [0]
    assert any("visto bueno" in m for m in engine.sent)
    assert engine.decide(run.id, 0, True)
    for _ in range(1000):
        if run.status in ("done", "partial", "failed"):
            break
        threading.Event().wait(0.01)
    kinds = []
    while "finished" not in kinds:
        kinds.append(box.get(timeout=10)["type"])
    assert run.status == "done" and len(runner.prompts) == 1
    assert kinds[:2] == ["planned", "approval"]


def test_denied_or_unanswered_steps_are_skipped(engine_factory):
    engine = engine_factory(
        _plan(_step("Compra el portátil más barato", ["web_search"])),
        FakeRunner(),
        approval_timeout=0.05,
    )
    run = engine.start(GOAL, wait=True)
    assert run.steps[0].status == "skipped" and run.status == "failed"


def test_cancel_wakes_a_waiting_run(engine_factory):
    engine = engine_factory(
        _plan(_step("Compra el portátil más barato", ["web_search"])), FakeRunner()
    )
    run = engine.start(GOAL)
    for _ in range(1000):
        if run.status == "waiting_approval":
            break
        threading.Event().wait(0.01)
    assert engine.cancel(run.id)
    for _ in range(1000):
        if run.status == "cancelled":
            break
        threading.Event().wait(0.01)
    assert run.status == "cancelled"


def test_planner_crash_is_reported(engine_factory):
    def broken(goal):
        raise RuntimeError("sin modelo")

    engine = engine_factory(broken, FakeRunner())
    run = engine.start(GOAL, wait=True)
    assert run.status == "failed" and "sin modelo" in run.summary


def test_runs_survive_a_restart(engine_factory, tmp_path):
    engine = engine_factory(
        _plan(_step("Buscar portátiles para Blender")), FakeRunner()
    )
    run = engine.start(GOAL, wait=True)
    again = CoworkEngine(root=engine.root, trust=engine.trust)
    assert again.get(run.id).status == "done"


def test_audit_detects_tampering(tmp_path):
    trail = AuditTrail(tmp_path / "a.jsonl")
    trail.record("one", key="sk-abcdefghijklmnopqrstuvwxyz123456")
    trail.record("two")
    trail.record("three")
    assert trail.verify() == (True, None)
    assert "[oculto]" in trail.path.read_text()
    lines = trail.path.read_text().splitlines()
    entry = json.loads(lines[1])
    entry["data"] = {"forged": True}
    lines[1] = json.dumps(entry)
    trail.path.write_text("\n".join(lines) + "\n")
    assert trail.verify() == (False, 2)
    assert AuditTrail(trail.path)._seq == 3  # appending continues after the last line

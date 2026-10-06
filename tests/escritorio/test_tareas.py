"""Live Activities, the dúo island and multitasking (foreground/background)."""

from __future__ import annotations

import threading
import time

from sergio_escritorio.activities import Activities, Spring
from sergio_escritorio.tareas import Orchestrator, parse_background, parse_together, step_status


def test_activities_run_finish_and_linger():
    now = [0.0]
    acts = Activities(clock=lambda: now[0])
    a = acts.start("Blender Pro", "blender")
    b = acts.start("Vuelos", "search")
    acts.update(a, progress=0.5, detail="revisión 2")
    assert [x.title for x in acts.snapshot()] == ["Blender Pro", "Vuelos"]
    assert "2 cosas en marcha" in acts.describe() and "50 %" in acts.describe()
    acts.finish(a, ok=True)
    assert acts.snapshot()[0].state == "done"  # the check is the news: shown first
    now[0] = 10.0
    assert [x.title for x in acts.snapshot()] == ["Vuelos"]  # gone after it lingered


def test_springs_overshoot_softly_and_settle():
    spring = Spring(0.0)
    spring.target = 1.0
    peak = 0.0
    for _ in range(240):
        peak = max(peak, spring.step(1 / 60))
    assert 1.0 < peak < 1.2 and spring.settled()


def test_the_duo_island_appears_with_two_activities(tmp_path):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    from sergio_escritorio.notch import Notch

    acts = Activities()
    notch = Notch()
    notch.activities = acts
    acts.start("Uno", "task")
    for _ in range(60):
        notch._tick()
        notch._last_tick -= 1 / 60  # simulate 60 fps
    assert notch.bubble() is None and notch.pill().width() > 200  # live pill, no dúo yet
    acts.start("Dos", "search")
    for _ in range(90):
        notch._tick()
        notch._last_tick -= 1 / 60
    bubble = notch.bubble()
    assert bubble is not None and bubble.left() > notch.pill().right()  # split in two


def test_voice_orders_for_tasks():
    assert parse_background("En segundo plano, busca vuelos a Madrid") == "busca vuelos a Madrid"
    assert parse_background("in the background, summarise this PDF") == "summarise this PDF"
    assert parse_background("busca vuelos a Madrid") is None
    assert parse_together("haz a la vez busca vuelos a Madrid y ordena mis descargas") == [
        "busca vuelos a Madrid", "ordena mis descargas"]
    assert step_status("hecho\nTERMINADO: tabla en Documentos") == ("done", "tabla en Documentos")
    assert step_status("FALTA: abrir Excel")[0] == "more"


def make(plan, answers, approve=lambda _w: True):
    told, calls = [], []
    lock = threading.Lock()

    def new_asker():
        def ask(prompt):
            with lock:
                calls.append(prompt)
            time.sleep(0.05)
            return answers(prompt)

        return ask

    acts = Activities()
    orch = Orchestrator(plan, new_asker, acts, approve=approve, told=told.append)
    return orch, acts, told, calls


def wait(orch):
    for _ in range(400):
        if not orch.running():
            return
        time.sleep(0.01)
    raise AssertionError("tasks did not finish")


def test_background_tasks_run_in_parallel_and_report():
    plan = lambda r: {"titulo": r, "pasos": [{"paso": f"{r}: buscar", "donde": "fondo"},  # noqa: E731
                                              {"paso": f"{r}: tabla", "donde": "fondo"}]}
    orch, acts, told, calls = make(plan, lambda p: "TERMINADO: listo")
    start = time.time()
    orch.submit("A")
    orch.submit("B")
    wait(orch)
    assert time.time() - start < 0.4  # 4 steps of 0.05 s, two tasks side by side
    assert all(t.status == "done" for t in orch.tasks) and len(told) == 2
    assert "NO uses desktop_action" in calls[0]  # background steps keep off the screen


def test_screen_steps_take_turns():
    inside, worst = [0], [0]

    def answers(prompt):
        if "usa la pantalla" in prompt:
            inside[0] += 1
            worst[0] = max(worst[0], inside[0])
            time.sleep(0.05)
            inside[0] -= 1
        return "TERMINADO: ok"

    plan = lambda r: {"pasos": [{"paso": "abrir Excel", "donde": "pantalla"}]}  # noqa: E731
    orch, *_ = make(plan, answers)
    for name in "ABC":
        orch.submit(name)
    wait(orch)
    assert worst[0] == 1  # never two tasks on the mouse at once


def test_a_failed_step_gets_a_new_approach_once():
    replies = iter(["FALTA: guardar", "FALTA: no encuentro la carpeta", "TERMINADO: guardado en Documentos"])
    plans = []

    def plan(r):
        plans.append(r)
        return {"pasos": [{"paso": "hacer la tabla" if len(plans) == 1 else "guardarla en Documentos", "donde": "fondo"}]}

    orch, acts, told, calls = make(plan, lambda p: next(replies))
    orch.submit("tabla")
    wait(orch)
    assert len(plans) == 2 and "no encuentro la carpeta" in plans[1] and "enfoque distinto" in plans[1]
    assert orch.tasks[0].status == "done" and "Documentos" in told[0]


def test_when_the_new_approach_also_fails_it_says_where_it_stopped():
    plan = lambda r: {"pasos": [{"paso": "hacer la tabla", "donde": "fondo"}]}  # noqa: E731
    orch, acts, told, calls = make(plan, lambda p: "FALTA: no encuentro la carpeta")
    orch.submit("tabla")
    wait(orch)
    assert orch.tasks[0].status == "failed" and "no encuentro la carpeta" in told[0]


def test_an_agent_works_with_its_role_and_its_tools():
    seen = []
    agent = {"nombre": "Investigador", "instrucciones": "Busca con fuentes.", "herramientas": ["web_search"]}

    def plan(r, a=None):
        seen.append(a)
        return {"pasos": [{"paso": "buscar", "donde": "fondo"}]}

    orch, acts, told, calls = make(plan, lambda p: "TERMINADO: 3 fuentes")
    orch.submit("precios de GPUs", agent=agent)
    wait(orch)
    assert seen == [agent] and "Eres el agente «Investigador»" in calls[0]


def test_risky_steps_wait_for_the_owner():
    plan = lambda r: {"pasos": [{"paso": "borra los duplicados", "donde": "fondo", "importante": True}]}  # noqa: E731
    orch, acts, told, calls = make(plan, lambda p: "TERMINADO: borrados", approve=lambda _w: False)
    orch.submit("limpia fotos")
    wait(orch)
    assert calls == [] and "aprobación" in told[0]


def test_without_a_planner_the_request_is_one_careful_step():
    def broken(_r):
        raise RuntimeError("offline")

    orch, acts, told, calls = make(broken, lambda p: "TERMINADO: hecho")
    orch.submit("abre la calculadora")
    wait(orch)
    assert orch.tasks[0].steps[0].where == "pantalla" and orch.tasks[0].status == "done"

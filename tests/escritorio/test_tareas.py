"""Live Activities, the dúo island and multitasking (foreground/background)."""

from __future__ import annotations

import threading
import time

from sergio_escritorio.activities import Activities, Spring
from sergio_escritorio.tareas import (
    Orchestrator,
    parse_background,
    parse_together,
    step_status,
)


def test_activities_run_finish_and_linger():
    now = [0.0]
    acts = Activities(clock=lambda: now[0])
    a = acts.start("Blender Pro", "blender")
    acts.start("Vuelos", "search")
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
    assert (
        notch.bubble() is None and notch.pill().width() > 200
    )  # live pill, no dúo yet
    acts.start("Dos", "search")
    for _ in range(90):
        notch._tick()
        notch._last_tick -= 1 / 60
    assert notch.bubble() is None  # two tasks alone don't split it: «+1» instead
    notch.set_multitasking(True)  # «Sergio, activa multitasking»
    for _ in range(90):
        notch._tick()
        notch._last_tick -= 1 / 60
    bubble = notch.bubble()
    assert bubble is not None and bubble.left() > notch.pill().right()  # split in two
    notch.set_multitasking(False)
    for _ in range(90):
        notch._tick()
        notch._last_tick -= 1 / 60
    assert notch.bubble() is None  # folded back


def test_island_voice_orders():
    from sergio_escritorio.quick import parse_quick

    assert parse_quick("Sergio, activa multitasking").kind == "multitask_on"
    assert parse_quick("activa el modo multitarea por favor").kind == "multitask_on"
    assert parse_quick("Sergio desactiva multitasking").kind == "multitask_off"
    assert parse_quick("Sergio, esconde el notch").kind == "notch_hide"
    assert parse_quick("oculta la isla").kind == "notch_hide"
    assert parse_quick("Sergio, muestra el notch").kind == "notch_show"
    assert parse_quick("vuelve a poner el notch").kind == "notch_show"


def test_the_notch_falls_into_a_black_hole_and_comes_back():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    from sergio_escritorio.activities import Vanish
    from sergio_escritorio.notch import Notch

    v = Vanish()
    v.hide()
    v.step(Vanish.DURATION * Vanish.COLLAPSE)
    assert v.collapse() == 1.0 and v.rise() == 0.0  # a ball, not yet risen
    v.step(Vanish.DURATION)
    assert v.hidden and v.rise() == 1.0 and v.glow() == 0.0
    notch = Notch()
    notch.show()
    notch.hide_notch()
    for _ in range(80):
        notch._tick()
        notch._last_tick -= 1 / 60
        notch.repaint()  # every frame of the film draws
    assert notch.hidden and not notch.isVisible()
    notch.show_notch()
    assert notch.isVisible()
    for _ in range(80):
        notch._tick()
        notch._last_tick -= 1 / 60
    assert not notch.hidden and not notch._vanish.active


def test_voice_orders_for_tasks():
    assert (
        parse_background("En segundo plano, busca vuelos a Madrid")
        == "busca vuelos a Madrid"
    )
    assert (
        parse_background("in the background, summarise this PDF")
        == "summarise this PDF"
    )
    assert parse_background("busca vuelos a Madrid") is None
    assert parse_together(
        "haz a la vez busca vuelos a Madrid y ordena mis descargas"
    ) == ["busca vuelos a Madrid", "ordena mis descargas"]
    assert step_status("hecho\nTERMINADO: tabla en Documentos") == (
        "done",
        "tabla en Documentos",
    )
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
    plan = lambda r: {
        "titulo": r,
        "pasos": [
            {"paso": f"{r}: buscar", "donde": "fondo"},  # noqa: E731
            {"paso": f"{r}: tabla", "donde": "fondo"},
        ],
    }
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
    replies = iter(
        [
            "FALTA: guardar",
            "FALTA: no encuentro la carpeta",
            "TERMINADO: guardado en Documentos",
        ]
    )
    plans = []

    def plan(r):
        plans.append(r)
        return {
            "pasos": [
                {
                    "paso": "hacer la tabla"
                    if len(plans) == 1
                    else "guardarla en Documentos",
                    "donde": "fondo",
                }
            ]
        }

    orch, acts, told, calls = make(plan, lambda p: next(replies))
    orch.submit("tabla")
    wait(orch)
    assert (
        len(plans) == 2
        and "no encuentro la carpeta" in plans[1]
        and "enfoque distinto" in plans[1]
    )
    assert orch.tasks[0].status == "done" and "Documentos" in told[0]


def test_when_the_new_approach_also_fails_it_says_where_it_stopped():
    plan = lambda r: {"pasos": [{"paso": "hacer la tabla", "donde": "fondo"}]}  # noqa: E731
    orch, acts, told, calls = make(plan, lambda p: "FALTA: no encuentro la carpeta")
    orch.submit("tabla")
    wait(orch)
    assert orch.tasks[0].status == "failed" and "no encuentro la carpeta" in told[0]


def test_an_agent_works_with_its_role_and_its_tools():
    seen = []
    agent = {
        "nombre": "Investigador",
        "instrucciones": "Busca con fuentes.",
        "herramientas": ["web_search"],
    }

    def plan(r, a=None):
        seen.append(a)
        return {"pasos": [{"paso": "buscar", "donde": "fondo"}]}

    orch, acts, told, calls = make(plan, lambda p: "TERMINADO: 3 fuentes")
    orch.submit("precios de GPUs", agent=agent)
    wait(orch)
    assert seen == [agent] and "Eres el agente «Investigador»" in calls[0]


def test_risky_steps_wait_for_the_owner():
    plan = lambda r: {
        "pasos": [
            {"paso": "borra los duplicados", "donde": "fondo", "importante": True}
        ]
    }  # noqa: E731
    orch, acts, told, calls = make(
        plan, lambda p: "TERMINADO: borrados", approve=lambda _w: False
    )
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


def test_a_screen_plan_can_be_stopped_before_it_starts():
    plan = lambda r: {"pasos": [{"paso": "abrir Excel", "donde": "pantalla"}]}  # noqa: E731
    orch, acts, told, calls = make(plan, lambda p: "TERMINADO: ok")
    orch.plan_grace = 0.5
    orch.submit("tabla")
    time.sleep(0.1)
    orch.cancel_last()
    wait(orch)
    assert (
        calls == [] and orch.tasks[0].status == "cancelled" and "Cancelada" in told[0]
    )


def test_a_file_that_is_said_to_exist_is_checked():
    from sergio_escritorio.tareas import claimed_paths

    assert claimed_paths(
        "TERMINADO: tabla guardada en C:\\Users\\dani\\Documents\\tabla.xlsx."
    ) == ["C:\\Users\\dani\\Documents\\tabla.xlsx"]
    replies = iter(
        [
            "TERMINADO: guardado en C:\\x\\tabla.xlsx",
            "TERMINADO: ahora sí en C:\\x\\tabla.xlsx",
        ]
    )
    files = {"C:\\x\\tabla.xlsx": False}
    plan = lambda r: {"pasos": [{"paso": "hacer la tabla", "donde": "fondo"}]}  # noqa: E731

    def answers(prompt):
        reply = next(replies)
        if "no existe" in prompt:
            files["C:\\x\\tabla.xlsx"] = True  # the second time it really wrote it
        return reply

    orch, acts, told, calls = make(plan, answers)
    orch.exists = lambda p: files.get(p)
    orch.submit("tabla")
    wait(orch)
    assert "no existe" in calls[1] and orch.tasks[0].status == "done"


def test_a_file_that_never_appears_is_not_reported_as_done():
    plan = lambda r: {"pasos": [{"paso": "hacer la tabla", "donde": "fondo"}]}  # noqa: E731
    orch, acts, told, calls = make(
        plan, lambda p: "TERMINADO: guardado en C:\\x\\t.xlsx"
    )
    orch.exists = lambda p: False
    orch.submit("tabla")
    wait(orch)
    assert orch.tasks[0].status == "failed"


def test_independent_steps_run_at_the_same_time_then_the_one_that_needs_them():
    order = []

    def answers(prompt):
        order.append(prompt.split("Paso actual (web): ")[1].split("\n")[0])
        return "TERMINADO: ok"

    plan = lambda r: {
        "pasos": [  # noqa: E731
            {"paso": "buscar A", "depende_de": []},
            {"paso": "buscar B", "depende_de": []},
            {"paso": "buscar C", "depende_de": []},
            {"paso": "tabla", "depende_de": [1, 2, 3]},
        ]
    }
    orch, *_ = make(plan, answers)
    start = time.time()
    orch.submit("comparar")
    wait(orch)
    assert (
        time.time() - start < 0.2
    )  # three searches side by side (0.05 s each), then the table
    assert order[-1] == "tabla" and orch.tasks[0].status == "done"


def test_a_step_never_runs_before_what_it_needs():
    from sergio_escritorio.tareas import Orchestrator as O

    steps = O._steps(
        {
            "pasos": [
                {"paso": "a"},
                {"paso": "b", "depende_de": [3, 1, 2]},
                {"paso": "c"},
            ]
        }
    )
    assert steps[1].after == [0]  # later or self references dropped: no cycles
    assert steps[2].after == [1]  # not said: after the previous one


def test_the_revisor_checks_the_result_and_one_fix_step_runs():
    def answers(prompt):
        if "Eres el Revisor" in prompt:
            return "FALTA: la tabla no tiene precios"
        return "TERMINADO: hecho"

    plan = lambda r: {"pasos": [{"paso": "buscar"}, {"paso": "tabla"}]}  # noqa: E731
    orch, acts, told, calls = make(plan, answers)
    orch.review = True
    orch.submit("tabla de portátiles")
    wait(orch)
    task = orch.tasks[0]
    assert task.status == "done" and task.steps[-1].text.startswith(
        "Corrige lo que falta: la tabla no tiene precios"
    )
    assert any("Eres el Revisor" in c for c in calls)


def test_a_step_for_each_element_becomes_a_swarm_and_the_next_waits_for_all():
    items = [f"producto {n}" for n in range(40)]
    plan = lambda r: {
        "reglas": "Skill «Enjambre»: cita la fuente",
        "pasos": [  # noqa: E731
            {"paso": "busca el precio", "para_cada": items, "depende_de": []},
            {"paso": "haz la tabla", "depende_de": [1]},
        ],
    }
    orch, acts, told, calls = make(plan, lambda p: "TERMINADO: ok")
    orch.swarm = threading.BoundedSemaphore(20)
    start = time.time()
    task = orch.submit("precios")
    wait(orch)
    took = time.time() - start
    assert len(task.steps) == 41 and task.steps[-1].after == list(range(40))
    assert (
        took < 0.6
    )  # 40 sub-agents of 0.05 s, 20 at a time, then the table (2 s if one by one)
    assert task.status == "done" and task.calls == 41
    assert "cita la fuente" in calls[0] and "solo para: producto" in calls[0]
    from sergio_escritorio.tareas import plan_line

    assert "×40 subagentes a la vez" in plan_line(task)


def test_the_swarm_never_exceeds_its_limit():
    inside, worst = [0], [0]
    lock = threading.Lock()

    def answers(prompt):
        with lock:
            inside[0] += 1
            worst[0] = max(worst[0], inside[0])
        time.sleep(0.03)
        with lock:
            inside[0] -= 1
        return "TERMINADO: ok"

    plan = lambda r: {
        "pasos": [{"paso": "x", "para_cada": [str(n) for n in range(30)]}]
    }  # noqa: E731
    orch, *_ = make(plan, answers)
    orch.swarm = threading.BoundedSemaphore(5)
    orch.submit("x")
    wait(orch)
    assert worst[0] == 5


def test_the_duo_unfolds_like_the_iphone_duo():
    from sergio_escritorio.activities import Fold

    fold = Fold()
    assert fold.angle == 0 and fold.reach() == -1.0 and fold.effect() == 1.0
    fold.open(True)
    fold.step(Fold.DURATION / 2)
    assert 80 < fold.angle < 100 and fold.darken() == 1.0  # edge-on, still dark
    fold.step(Fold.DURATION / 2)
    assert fold.angle == 180 and fold.settled() and fold.facing()
    assert fold.effect() == 0.0 and fold.darken() == 0.0 and fold.reach() == 1.0
    fold.open(False)
    fold.step(0.3)
    fold.open(True)  # a change of mind reverses from where it is
    assert 0 < fold.angle < 180 and fold.step(Fold.DURATION) == 180

"""Actual scheduling, error propagation and fail-closed review boundaries."""

import threading
import time

import pytest
from sergio_escritorio.activities import Activities
from sergio_escritorio.tareas import Orchestrator, Step, Task


def test_three_hundred_steps_use_only_four_concurrent_workers():
    active = peak = 0
    lock = threading.Lock()

    def ask(_):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)
        time.sleep(0.001)
        with lock:
            active -= 1
        return "TERMINADO: salida real de prueba"

    def plan(_):
        return {"pasos": [{"paso": "Busca cada fuente", "para_cada": list(range(300))}]}

    orch = Orchestrator(plan, lambda: ask, Activities(), swarm=4)
    try:
        task = orch.submit("Investiga 300 fuentes")
        deadline = time.monotonic() + 5
        while orch.running() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert task.status == "done" and len(task.steps) == 300
        assert 1 < peak <= 4
    finally:
        orch.close()


def test_missing_review_verdict_does_not_become_success():
    orch = Orchestrator(
        lambda _: {}, lambda: lambda _: "No puedo comprobarlo", Activities()
    )
    task = Task(
        1,
        "Verifica el informe",
        steps=[Step("one", "fondo", status="done", result="model claim")],
    )
    try:
        assert orch._review(task) is False
    finally:
        orch.close()


def test_budget_and_invented_tools_are_blocked_before_execution():
    calls = []
    orch = Orchestrator(
        lambda _: {}, lambda: lambda p: calls.append(p) or "ok", Activities()
    )
    try:
        with pytest.raises(ValueError, match="herramientas"):
            orch._steps({"pasos": [{"paso": "Do something", "bloqueado": True}]})
        task = Task(1, "task", calls=4000)
        with pytest.raises(RuntimeError, match="4000"):
            orch._limited(task, lambda p: calls.append(p))("next")
        assert not calls
    finally:
        orch.close()


def test_pool_exception_marks_step_failed():
    orch = Orchestrator(lambda _: {}, lambda: lambda _: "", Activities(), swarm=2)
    task = Task(1, "job", steps=[Step("a", "fondo"), Step("b", "fondo")])
    task.activity = orch.activities.start("job", "task")

    def broken(*args):
        raise ValueError("Internal sensitive message")

    orch._do = broken
    try:
        orch._wave(task, task.steps)
        assert all(s.status == "failed" for s in task.steps)
        assert all("sensitive" not in s.result for s in task.steps)
    finally:
        orch.close()


def test_unknown_file_existence_is_not_proof_of_delivery():
    orch = Orchestrator(
        lambda _: {}, lambda: lambda _: "", Activities(), exists=lambda _: None
    )
    try:
        assert orch._missing_files(r"Guardado en C:\\work\\report.xlsx")
    finally:
        orch.close()

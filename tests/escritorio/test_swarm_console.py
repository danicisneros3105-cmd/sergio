"""Console data comes from actual tasks, and cancellation targets one task."""

from sergio_escritorio.activities import Activities
from sergio_escritorio.tareas import Orchestrator, Step, Task


def test_snapshot_is_bounded_and_cancellation_does_not_hit_another_task():
    swarm = Orchestrator(lambda goal: {}, lambda: lambda text: "", Activities())
    try:
        first = Task(
            1,
            "Research",
            status="running",
            steps=[Step("Search", status="done", result="source")],
        )
        second = Task(
            2, "Review", status="running", steps=[Step("Test", status="running")]
        )
        swarm.tasks = [first, second]
        snapshot = swarm.snapshot()
        assert snapshot[0]["progress"] == 1
        assert swarm.task_details(2)["steps"][0]["status"] == "running"
        selected = swarm.task_details(1)
        selected["steps"][0]["result"] = "edited"
        assert first.steps[0].result == "source"
        assert "steps" not in snapshot[0]
        assert swarm.task_details(99) == {}
        assert swarm.cancel_task(2)
        assert second.cancel.is_set() and not first.cancel.is_set()
        assert not swarm.cancel_task(99)
        first.status = "done"
        assert not swarm.cancel_task(1)
        first.steps = [Step("x" * 1000, result="r" * 10000)] * 4000
        assert len(swarm.task_details(1)["steps"]) == 80
        assert swarm.task_details(1)["total_steps"] == 4000
    finally:
        swarm.close()

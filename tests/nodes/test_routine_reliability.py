import httpx

from openjarvis.nodes.store import NodeStore
from openjarvis.nodes.worker import NodeWorker


def worker_with_watch(tmp_path, fetch):
    worker = NodeWorker(
        NodeStore(tmp_path),
        fetch=fetch,
        ask=lambda *a, **k: {},
        runner=lambda *a: ("Hecho.", 0),
    )
    node = worker.create("Scout")
    routine = worker.store.add_routine(
        node.id,
        {
            "kind": "web",
            "url": "https://example.test",
            "task": "Avisar si cambia",
            "every_minutes": 15,
        },
    )
    return worker, node, routine


def test_three_real_failures_pause_and_a_user_can_resume(tmp_path):
    def fail(url):
        raise ValueError("Contenido inválido")

    worker, node, routine = worker_with_watch(tmp_path, fail)
    for _ in range(3):
        assert worker.check_now(node.id, routine.id)["error"]
    paused = worker.store.get(node.id).routines[0]
    assert not paused.enabled and paused.failures == 3
    assert worker.tick(10**10) == 0
    worker.store.mark_routine(
        node.id, routine.id, 0, enabled=True, failures=0, last_error=""
    )
    assert worker.store.get(node.id).routines[0].enabled


def test_an_offline_connection_does_not_exhaust_the_routine(tmp_path):
    def offline(url):
        raise httpx.ConnectError("Sin conexión")

    worker, node, routine = worker_with_watch(tmp_path, offline)
    for _ in range(5):
        worker.check_now(node.id, routine.id)
    current = worker.store.get(node.id).routines[0]
    assert current.enabled and current.failures == 0

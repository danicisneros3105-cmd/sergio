"""The owner sees what a Node has waiting and can drop a task or move it first."""

from openjarvis.nodes.store import NodeStore
from openjarvis.nodes.worker import NodeWorker


def test_queue_list_drop_and_first(tmp_path):
    worker = NodeWorker(NodeStore(tmp_path), ask=lambda *a, **k: {}, runner=lambda *a: ("Hecho.", 0))
    node = worker.create("Scout")
    # put jobs straight in the queue (no turn running), as if the Node were busy
    worker._queues[node.id] = [{"request": t, "source": "Usted"} for t in ("uno", "dos", "tres")]
    assert [q["request"] for q in worker.queued(node.id)] == ["uno", "dos", "tres"]
    assert worker.first_queued(node.id, 2)
    assert [q["request"] for q in worker.queued(node.id)] == ["tres", "uno", "dos"]
    assert worker.drop_queued(node.id, 1)
    assert [q["request"] for q in worker.queued(node.id)] == ["tres", "dos"]
    assert not worker.drop_queued(node.id, 9) and not worker.first_queued(node.id, -1)

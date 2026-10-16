import os
import time

from openjarvis.workspace.store import WorkspaceStore


def test_old_page_gets_full_retention_after_delete(tmp_path, monkeypatch):
    store = WorkspaceStore(tmp_path)
    store.put({"id": "p_audit12345", "title": "Keep", "blocks": []})
    old = time.time() - 60 * 86400
    os.utime(store.pages_dir / "p_audit12345.json", (old, old))
    assert store.delete("p_audit12345")
    assert store.empty_trash() == 0
    deleted = time.time()
    monkeypatch.setattr(
        "openjarvis.workspace.store.time.time", lambda: deleted + 31 * 86400
    )
    assert store.empty_trash() == 1

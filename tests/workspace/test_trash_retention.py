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


def test_legacy_trash_uses_deletion_date_from_filename(tmp_path):
    store = WorkspaceStore(tmp_path)
    store.trash_dir.mkdir(parents=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    legacy = store.trash_dir / f"p_audit12345.{stamp}.json"
    legacy.write_text("{}")
    old = time.time() - 60 * 86400
    os.utime(legacy, (old, old))
    assert store.empty_trash() == 0 and legacy.exists()

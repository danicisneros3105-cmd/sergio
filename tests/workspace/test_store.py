"""The Workspace store: pages + Markdown twins, revisions, conflicts, files,
search, export, shares, and the tool Sergio uses."""

from __future__ import annotations

import io
import json
import time
import zipfile

import pytest

from openjarvis.workspace.markdown import page_markdown
from openjarvis.workspace.shares import Shares, render_html, scoped_blocks
from openjarvis.workspace.store import Conflict, WorkspaceError, WorkspaceStore


def page(pid="p_abc123def", title="Compras", blocks=None, **extra):
    now = int(time.time() * 1000)
    return {
        "id": pid,
        "title": title,
        "icon": "",
        "parent": None,
        "blocks": blocks
        if blocks is not None
        else [{"id": "b_1", "type": "text", "text": "leche y pan"}],
        "createdAt": now,
        "updatedAt": now,
        "rev": 0,
        **extra,
    }


def table_block():
    return {
        "id": "b_t",
        "type": "table",
        "text": "",
        "table": {
            "columns": [
                {"id": "c1", "name": "Tarea", "type": "text"},
                {"id": "c2", "name": "Estado", "type": "select"},
            ],
            "rows": [
                {"id": "r1", "cells": {"c1": "Diseño", "c2": "Hecho"}},
                {"id": "r2", "cells": {"c1": "Presupuesto", "c2": "En curso"}},
                {"id": "r3", "cells": {"c1": "Secreto", "c2": "Por hacer"}},
            ],
            "views": [
                {"id": "v1", "name": "Tabla", "kind": "table"},
                {
                    "id": "v2",
                    "name": "Cliente",
                    "kind": "table",
                    "filter": {"column": "c2", "op": "not", "value": "Por hacer"},
                },
            ],
            "view": "v1",
        },
    }


@pytest.fixture()
def store(tmp_path):
    changes = []
    s = WorkspaceStore(tmp_path / "ws", on_change=lambda: changes.append(1))
    s.changes = changes
    return s


def test_save_read_list_and_markdown_twin(store):
    saved = store.put(page())
    assert saved["rev"] == 1 and store.changes
    again = store.put({**saved, "title": "Compras del lunes"}, base_rev=1)
    assert again["rev"] == 2
    assert store.get("p_abc123def")["title"] == "Compras del lunes"
    assert [p["title"] for p in store.list()] == ["Compras del lunes"]
    md = (store.pages_dir / "p_abc123def.md").read_text(encoding="utf-8")
    assert (
        md.startswith('---\nid: "p_abc123def"')
        and "# Compras del lunes" in md
        and "leche y pan" in md
    )


def test_a_stale_copy_never_overwrites_it_is_kept_aside(store):
    store.put(page())
    store.put(page(title="Editado en el móvil"), base_rev=1)  # rev 2
    with pytest.raises(Conflict) as err:
        store.put(page(title="Editado en el PC"), base_rev=1)
    assert err.value.current["title"] == "Editado en el móvil"
    copy = store.get(err.value.copy_id)
    assert copy["title"] == "Editado en el PC (copia en conflicto)"
    assert {p["title"] for p in store.list()} == {
        "Editado en el móvil",
        "Editado en el PC (copia en conflicto)",
    }


def test_bad_input_is_refused_and_paths_cannot_escape(store):
    for bad in (
        {"id": "../x", "blocks": []},
        {"id": "p_abc123def", "blocks": "no"},
        "texto",
        page(blocks=[{"type": "text"}], title="x" * 301),
        page(parent="../../etc"),
    ):
        with pytest.raises(WorkspaceError):
            store.put(bad)
    with pytest.raises(WorkspaceError):
        store.get("../../secret")
    with pytest.raises(WorkspaceError):
        store.put(
            page(blocks=[{"id": "b", "type": "text", "text": "x"}], sealed={"v": 1})
        )
    assert store.file_path("../../etc/passwd") is None


def test_sealed_pages_stay_unreadable(store):
    store.put(
        page(blocks=[], sealed={"v": 1, "salt": "s", "iv": "i", "data": "CIFRADO"})
    )
    md = (store.pages_dir / "p_abc123def.md").read_text(encoding="utf-8")
    assert "cifrada de extremo a extremo" in md and "CIFRADO" not in md
    assert store.search("Compras") == []  # not indexed


def test_files_search_delete_and_export(store):
    store.put(page())
    store.put(
        page(
            "p_meet00001",
            "Reunión con Ana",
            [
                {"id": "b", "type": "h2", "text": "Decisiones"},
                {"id": "c", "type": "bullet", "text": "Lanzamos en noviembre"},
            ],
        )
    )
    file_id = store.save_file(b"OggS-audio", "ogg")
    assert store.file_path(file_id).read_bytes() == b"OggS-audio"
    with pytest.raises(WorkspaceError):
        store.save_file(b"x", "exe")
    hits = store.search("noviembre reunion")
    assert [h["id"] for h in hits] == ["p_meet00001"] and "noviembre" in hits[0][
        "snippet"
    ]
    data = store.export_zip()
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "pages/p_meet00001.json" in names and f"markdown/files/{file_id}" in names
    assert any(n.startswith("markdown/reunion-con-ana-") for n in names)
    assert store.delete("p_meet00001") and store.get("p_meet00001") is None
    assert list(store.trash_dir.iterdir())
    assert not store.delete("p_meet00001")


def test_markdown_covers_every_block_kind():
    blocks = [
        {"type": "h1", "text": "Uno"},
        {"type": "todo", "text": "hecho", "checked": True},
        {"type": "number", "text": "a"},
        {"type": "number", "text": "b"},
        table_block(),
        {
            "type": "mindmap",
            "mind": [
                {"id": "n1", "text": "Centro", "parent": None},
                {"id": "n2", "text": "Rama", "parent": "n1"},
            ],
        },
        {"type": "chart", "chart": {"kind": "bar"}},
        {"type": "page", "pageId": "p_x", "text": ""},
    ]
    md = page_markdown(page(blocks=blocks), lambda _i: "Otra página")
    for want in (
        "## Uno",
        "- [x] hecho",
        "1. a",
        "2. b",
        "| Tarea | Estado |",
        "| Diseño | Hecho |",
        "- Centro",
        "  - Rama",
        "```sergio-chart",
        "[[Otra página]]",
    ):
        assert want in md, want


def test_shares_expose_only_the_chosen_part(store):
    store.put(
        page(
            blocks=[
                {"id": "b_note", "type": "text", "text": "Privado"},
                table_block(),
                {"id": "b_sub", "type": "page", "pageId": "p_other0001", "text": "Sub"},
            ]
        )
    )
    shares = Shares(store)
    whole = shares.create("p_abc123def", "page")
    assert [b["id"] for b in scoped_blocks(store.get("p_abc123def"), whole)] == [
        "b_note",
        "b_t",
    ]  # no sub-pages
    rows = shares.create("p_abc123def", "rows", block_id="b_t", row_ids=["r1"])
    only = scoped_blocks(store.get("p_abc123def"), rows)
    assert [r["id"] for r in only[0]["table"]["rows"]] == ["r1"]
    view = shares.create("p_abc123def", "view", block_id="b_t", view_id="v2")
    seen = scoped_blocks(store.get("p_abc123def"), view)[0]["table"]["rows"]
    assert [r["id"] for r in seen] == [
        "r1",
        "r2",
    ]  # the filtered view, «Secreto» stays out
    html = render_html(
        store.get("p_abc123def"),
        scoped_blocks(store.get("p_abc123def"), view),
        view["token"],
    )
    assert "Presupuesto" in html and "Secreto" not in html and "Privado" not in html
    assert (
        store.get("p_abc123def")["blocks"][1]["table"]["rows"][2]["cells"]["c1"]
        == "Secreto"
    )  # untouched
    for bad in (
        dict(scope="rows", block_id="b_t", row_ids=[]),
        dict(scope="view", block_id="b_t", view_id="zz"),
        dict(scope="block", block_id="nope"),
        dict(scope="rows", block_id="b_note", row_ids=["r1"]),
    ):
        with pytest.raises(WorkspaceError):
            shares.create("p_abc123def", **bad)
    short = shares.create("p_abc123def", "page", days=1, now=time.time() - 2 * 86400)
    assert shares.resolve(short["token"]) is None  # expired
    assert shares.resolve(whole["token"])["scope"] == "page"
    assert shares.revoke(whole["token"]) and shares.resolve(whole["token"]) is None
    assert shares.resolve("../x") is None


def test_html_escapes_everything(store):
    nasty = page(
        blocks=[
            {"id": "b", "type": "text", "text": "<script>alert(1)</script> **ok**"}
        ],
        title="<img onerror=x>",
    )
    out = render_html(nasty, nasty["blocks"], "tok")
    assert (
        "<script>" not in out
        and "&lt;script&gt;" in out
        and "<strong>ok</strong>" in out
    )
    assert "<img onerror" not in out


def test_encrypted_pages_cannot_be_shared(store):
    store.put(page(blocks=[], sealed={"v": 1, "salt": "s", "iv": "i", "data": "x"}))
    with pytest.raises(WorkspaceError, match="cifrada"):
        Shares(store).create("p_abc123def")


def test_sergio_tool_finds_reads_and_writes(store):
    from openjarvis.tools.workspace_tool import WorkspaceTool

    tool = WorkspaceTool(store)
    made = tool.execute(
        action="create", title="Viaje a Madrid", lines=["Reservar hotel"], kind="todo"
    )
    assert made.success and "Viaje a Madrid" in made.content
    assert tool.execute(
        action="task", page="viaje a madrid", text="Comprar billete"
    ).success
    read = tool.execute(action="read", page="Viaje a Madrid")
    assert "Reservar hotel" in read.content and "Comprar billete" in read.content
    found = tool.execute(action="search", query="billete")
    assert "Viaje a Madrid" in found.content
    assert not tool.execute(action="read", page="no existe nada").success
    assert "Viaje a Madrid" in tool.execute(action="list").content
    store.put(
        page(
            blocks=[],
            sealed={"v": 1, "salt": "s", "iv": "i", "data": "x"},
            title="Diario",
        )
    )
    assert "cifrada" in tool.execute(action="read", page="p_abc123def").content
    assert json.dumps(tool.spec.parameters)


def test_page_history_keeps_old_versions_without_one_per_keystroke(store, monkeypatch):
    from openjarvis.workspace import store as store_mod

    store.put(page(blocks=[{"id": "b1", "type": "text", "text": "versión uno"}]))
    first = store.get("p_abc123def")
    store.put(
        page(blocks=[{"id": "b1", "type": "text", "text": "versión dos"}]),
        base_rev=first["rev"],
    )
    # typing again a second later: no new version kept
    second = store.get("p_abc123def")
    store.put(
        page(blocks=[{"id": "b1", "type": "text", "text": "versión tres"}]),
        base_rev=second["rev"],
    )
    versions = store.history("p_abc123def")
    assert [v["rev"] for v in versions] == [1]
    assert "versión uno" in versions[0]["preview"]
    old = store.version("p_abc123def", 1)
    assert old["blocks"][0]["text"] == "versión uno"
    # after the pause, the next save keeps another version; only the last N stay
    monkeypatch.setattr(store_mod, "HISTORY_EVERY", 0.0)
    monkeypatch.setattr(store_mod, "HISTORY_KEEP", 2)
    for text in ("cuatro", "cinco", "seis"):
        cur = store.get("p_abc123def")
        store.put(
            page(blocks=[{"id": "b1", "type": "text", "text": text}]),
            base_rev=cur["rev"],
        )
        time.sleep(0.01)
    assert len(store.history("p_abc123def")) == 2
    assert store.version("p_abc123def", 999) is None
    with pytest.raises(WorkspaceError):
        store.history("../etc")

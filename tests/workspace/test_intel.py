"""Workspace beyond Notion: clipper, two-way Markdown, Word, merges, agenda."""

from __future__ import annotations

import io
import os
import time
import zipfile

import pytest

from openjarvis.workspace import intel
from openjarvis.workspace.store import WorkspaceStore


def b(i, text, kind="text", **extra):
    return {"id": f"b{i}", "type": kind, "text": text, **extra}


@pytest.fixture()
def store(tmp_path):
    return WorkspaceStore(root=tmp_path / "ws")


def test_simultaneous_edits_are_merged_not_copied(store):
    base = {
        "id": "p_merge0001",
        "title": "Plan",
        "blocks": [b(1, "uno"), b(2, "dos"), b(3, "tres")],
    }
    store.put(base)
    store.put(
        {**base, "blocks": [b(1, "uno"), b(2, "DOS"), b(3, "tres")]}, base_rev=1
    )  # phone
    merged = store.put(
        {**base, "blocks": [b(1, "UNO"), b(2, "dos"), b(3, "tres"), b(4, "nuevo")]},
        base_rev=1,
    )  # PC, from the same rev 1
    assert [x["text"] for x in merged["blocks"]] == ["UNO", "DOS", "tres", "nuevo"]
    assert merged["merged"]["conflicts"] == 0
    assert len(store.list()) == 1  # no conflict copy


def test_the_same_block_changed_twice_keeps_both(store):
    base = {"id": "p_merge0002", "title": "Plan", "blocks": [b(1, "uno")]}
    store.put(base)
    store.put({**base, "blocks": [b(1, "de ellos")]}, base_rev=1)
    merged = store.put({**base, "blocks": [b(1, "mío")]}, base_rev=1)
    assert [x["text"] for x in merged["blocks"]] == ["de ellos", "mío"]
    assert merged["blocks"][1]["conflict"] is True


def test_markdown_edited_elsewhere_comes_back(store):
    store.put(
        {
            "id": "p_mdsync001",
            "title": "Compras",
            "blocks": [b(1, "Leche", "todo", checked=False), b(2, "Notas", "h1")],
        }
    )
    md = store.pages_dir / "p_mdsync001.md"
    text = md.read_text(encoding="utf-8").replace(
        "- [ ] Leche", "- [x] Leche\n- [ ] Pan"
    )
    md.write_text(text, encoding="utf-8")
    future = time.time() + 5
    os.utime(md, (future, future))
    page = next(p for p in store.all() if p["id"] == "p_mdsync001")
    todos = [
        (x["text"], x.get("checked")) for x in page["blocks"] if x["type"] == "todo"
    ]
    assert todos == [("Leche", True), ("Pan", False)]
    assert page["blocks"][0]["id"] == "b1"  # the edited block kept its id
    assert page["rev"] == 2


def test_markdown_round_trip_keeps_structure():
    md = (
        "# Viaje\n\n## Plan\n\n- [x] Billetes\n- Mochila\n1. Primero\n\n> **Nota:** ojo\n\n"
        "| Día | Ciudad |\n| --- | --- |\n| 1 | Lima |\n\n```py\nprint(1)\n```\n\n---\n"
    )
    out = intel.markdown_blocks(md)
    assert out["title"] == "Viaje"
    kinds = [x["type"] for x in out["blocks"]]
    assert kinds == [
        "h1",
        "todo",
        "bullet",
        "number",
        "callout",
        "table",
        "code",
        "divider",
    ]
    table = out["blocks"][5]["table"]
    assert [c["name"] for c in table["columns"]] == ["Día", "Ciudad"]
    assert list(table["rows"][0]["cells"].values()) == ["1", "Lima"]


def test_clipper_keeps_the_article_not_the_menus():
    html = """<html><head><title>Sitio</title><meta property="og:title" content="Cómo hacer pan"></head>
    <body><nav><a href="/">Inicio</a><a href="/x">Tienda</a></nav>
    <div class="sidebar"><p>Suscríbase ya a nuestro boletín semanal de ofertas</p></div>
    <article><h1>Cómo hacer pan</h1><h2>Ingredientes</h2><ul><li>Harina</li><li>Agua</li></ul>
    <p>Mezcle la harina con el agua y deje reposar la masa durante una hora entera.</p>
    <img src="/pan.jpg"><pre>receta()</pre></article>
    <footer><p>© 2026 Todos los derechos</p></footer></body></html>"""
    out = intel.clip("https://pan.example/receta", fetch=lambda url: html)
    assert out["title"] == "Cómo hacer pan"
    texts = [x["text"] for x in out["blocks"]]
    assert texts[0] == "https://pan.example/receta"
    assert "Ingredientes" in texts and "Harina" in texts and "receta()" in texts
    assert "https://pan.example/pan.jpg" in texts
    assert not any("Suscríbase" in t or "Tienda" in t or "©" in t for t in texts)
    with pytest.raises(ValueError):
        intel.clip("file:///etc/passwd")


def test_clipper_refuses_private_addresses():
    with pytest.raises(ValueError):
        intel._fetch("http://127.0.0.1:8000/v1/workspace/export")


def test_word_document_is_valid():
    data = intel.docx_bytes(
        {
            "title": "Informe",
            "blocks": [
                b(1, "Resumen", "h1"),
                b(2, "Todo bien & claro <ok>"),
                b(3, "Hecho", "todo", checked=True),
                {
                    "id": "t",
                    "type": "table",
                    "text": "",
                    "table": {
                        "columns": [{"id": "c", "name": "A"}],
                        "rows": [{"id": "r", "cells": {"c": "1"}}],
                    },
                },
            ],
        }
    )
    z = zipfile.ZipFile(io.BytesIO(data))
    assert {"[Content_Types].xml", "word/document.xml", "word/styles.xml"} <= set(
        z.namelist()
    )
    doc = z.read("word/document.xml").decode()
    assert (
        "Todo bien &amp; claro &lt;ok&gt;" in doc
        and "<w:tbl>" in doc
        and "Heading1" in doc
    )


def test_agenda_collects_dates_from_pages():
    pages = [
        {
            "id": "p1",
            "title": "Proyecto",
            "blocks": [
                b(1, "Entregar 2026-10-20"),
                {
                    "id": "t",
                    "type": "table",
                    "table": {
                        "columns": [
                            {"id": "n", "name": "Tarea", "type": "text"},
                            {"id": "d", "name": "Fecha", "type": "date"},
                        ],
                        "rows": [
                            {"id": "r", "cells": {"n": "Logo", "d": "2026-10-15"}}
                        ],
                    },
                },
            ],
        }
    ]
    dates = sorted(intel.page_dates(pages), key=lambda d: d["date"])
    assert [(d["date"], d["title"]) for d in dates] == [
        ("2026-10-15", "Logo"),
        ("2026-10-20", "Entregar"),
    ]


def test_public_form_adds_validated_rows_and_site_mode(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.server import workspace_routes
    from openjarvis.workspace import store as store_mod
    from openjarvis.workspace.shares import Shares

    ws = WorkspaceStore(root=tmp_path / "ws2")
    monkeypatch.setattr(workspace_routes, "default_store", lambda: ws)
    monkeypatch.setattr(store_mod, "default_store", lambda: ws)
    table = {
        "columns": [
            {"id": "n", "name": "Nombre", "type": "text"},
            {
                "id": "k",
                "name": "Tipo",
                "type": "select",
                "options": ["Persona", "Empresa"],
            },
            {"id": "e", "name": "Empresa", "type": "text"},
            {"id": "m", "name": "Correo", "type": "email"},
        ],
        "rows": [],
        "views": [{"id": "v", "name": "Tabla", "kind": "table"}],
        "view": "v",
    }
    form = {
        "table": "tb",
        "title": "Alta",
        "fields": [
            {"column": "n", "required": True},
            {"column": "k"},
            {
                "column": "e",
                "required": True,
                "showIf": {"column": "k", "op": "is", "value": "Empresa"},
            },
            {"column": "m"},
        ],
    }
    ws.put(
        {
            "id": "p_form00001",
            "title": "Contactos",
            "site": {
                "on": True,
                "theme": "claro",
                "accent": "#ff0000",
                "font": "marca",
                "nav": True,
            },
            "blocks": [
                {"id": "h", "type": "h1", "text": "Bienvenida"},
                {"id": "tb", "type": "table", "text": "", "table": table},
                {"id": "fm", "type": "form", "text": "Alta", "form": form},
            ],
        }
    )
    token = Shares(ws).create("p_form00001", "page")["token"]
    app = FastAPI()
    app.include_router(workspace_routes.router)
    client = TestClient(app)
    page = client.get(f"/s/{token}")
    assert page.status_code == 200
    assert "nonce-" in page.headers["content-security-policy"]
    assert (
        "Josefin" in page.text and "#ff0000" in page.text and 'href="#s0"' in page.text
    )
    assert "<form class='form'" in page.text and "data-if='k'" in page.text
    bad = client.post(f"/s/{token}/form/fm", data={"k": "Empresa", "m": "mal"})
    assert bad.status_code == 400 and "Obligatorio" in bad.text
    ok = client.post(
        f"/s/{token}/form/fm",
        data={"n": "Ana", "k": "Persona", "e": "oculto", "m": "a@b.co"},
    )
    assert ok.status_code == 200
    rows = ws.get("p_form00001")["blocks"][1]["table"]["rows"]
    assert len(rows) == 1 and rows[0]["cells"] == {
        "n": "Ana",
        "k": "Persona",
        "e": "",
        "m": "a@b.co",
    }
    assert client.post(f"/s/{token}/form/tb", data={}).status_code == 404

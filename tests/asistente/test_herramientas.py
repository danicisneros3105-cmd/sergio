"""The assistant tools as the model calls them."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openjarvis.creator import routes, studio
from openjarvis.server.auth_middleware import _OPEN_MEDIA
from openjarvis.tools import asistente_tools as t


def test_an_excel_is_made_saved_and_downloadable(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "projects_root", lambda root=None: tmp_path)
    monkeypatch.setattr(t, "_documents", lambda: tmp_path / "Documents" / "Sergio")
    res = t.HojaCalculoTool().execute(
        action="crear",
        titulo="Gastos de octubre",
        hojas=[
            {
                "nombre": "Gastos",
                "columnas": ["Concepto", "Monto"],
                "filas": [["Taxi", 5]],
                "totales": ["Monto"],
            }
        ],
    )
    out = json.loads(res.content)
    assert res.success and out["en_documentos"].endswith("gastos-de-octubre.xlsx")
    assert _OPEN_MEDIA.fullmatch(out["descargar"])
    app = FastAPI()
    app.include_router(routes.router)
    r = TestClient(app).get(out["descargar"])
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert 'filename="gastos-de-octubre.xlsx"' in r.headers["content-disposition"]
    back = t.HojaCalculoTool().execute(action="leer", ruta=out["archivo"])
    assert "Taxi" in back.content


def test_background_tool_explains_what_is_missing(tmp_path, monkeypatch):
    from openjarvis.asistente import navegador

    monkeypatch.setattr(navegador, "home", lambda: tmp_path)
    res = t.SegundoPlanoTool().execute(action="revisar", sitio="mi banco")
    assert not res.success and "Dígame su dirección" in res.content
    ok = t.SegundoPlanoTool().execute(
        action="guardar_sitio", nombre="banco", url="https://banco.test"
    )
    assert (
        ok.success
        and "banco.test" in t.SegundoPlanoTool().execute(action="sitios").content
    )

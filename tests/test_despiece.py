"""Models that take apart in the chat (creator/despiece.py)."""

from __future__ import annotations

import json

import httpx
import pytest

from openjarvis.creator import despiece
from openjarvis.creator.llm import CreatorError

CAR = {
    "titulo": "Auto deportivo",
    "descripcion": "Un coupé de dos puertas.",
    "grupos": [
        {"id": "carroceria", "nombre": "Carrocería", "direccion": [0, 1, 0]},
        {"id": "ruedas", "nombre": "Ruedas", "direccion": [1, 0, 0]},
    ],
    "piezas": [
        {"id": "capo", "nombre": "Capó", "grupo": "carroceria", "forma": "caja",
         "medidas": [160, 4, 120], "redondeo": 3, "posicion": [0, 95, 150],
         "color": "#c0392b", "material": "pintura", "que_hace": "Tapa el motor."},
        {"id": "neumatico-izq", "nombre": "Neumático delantero izquierdo", "grupo": "ruedas",
         "forma": "toro", "medidas": [30, 10, 0], "posicion": [-80, 33, 140],
         "rotacion": [0, 0, 90], "color": "#111111", "material": "goma", "espejo_x": True},
        {"id": "tuerca", "nombre": "Tuerca", "grupo": "ruedas", "forma": "cilindro",
         "medidas": [1, 2, 0], "posicion": [-90, 38, 140],
         "repetir": {"n": 5, "eje": "x", "centro": [-90, 33, 140]}},
        {"id": "faro", "nombre": "Faro", "grupo": "luces", "forma": "perfil",
         "puntos": [[0, 0], [8, 2], [9, 6]], "posicion": [60, 80, 220], "material": "luz"},
        {"id": "raro", "forma": "dragon", "medidas": [1e9, -5, "x"], "color": "rojo", "material": "oro"},
    ],
}  # fmt: skip


def test_clean_expands_mirrors_and_circles_and_keeps_numbers_sane():
    model = despiece.clean(CAR)
    ids = [p["id"] for p in model["piezas"]]
    assert len(ids) == len(set(ids))  # every piece has its own id
    tyres = [p for p in model["piezas"] if p["nombre"].startswith("Neumático")]
    assert {t["posicion"][0] for t in tyres} == {-80, 80}
    assert any("derech" in t["nombre"] for t in tyres)
    nuts = [p for p in model["piezas"] if p["id"].startswith("tuerca")]
    assert len(nuts) == 5 and len({tuple(n["posicion"]) for n in nuts}) == 5
    odd = model["piezas"][-1]
    assert (
        odd["forma"] == "caja"
        and odd["color"] == "#9a9a9a"
        and odd["material"] == "plastico"
    )
    assert odd["medidas"][0] == despiece.MAX_CM and odd["medidas"][1] == 0.01
    assert next(p for p in model["piezas"] if p["id"] == "faro")["puntos"][1] == [
        8.0,
        2.0,
    ]
    # A group named only by a piece is created on the fly.
    assert {g["id"] for g in model["grupos"]} >= {"carroceria", "ruedas", "luces"}
    with pytest.raises(CreatorError):
        despiece.clean({"piezas": []})


def test_create_saves_the_model_and_reaches_the_chat(tmp_path):
    asked = []

    def ask(prompt, **kw):
        asked.append(prompt)
        kw["check"](json.dumps(CAR))
        return "```json\n" + json.dumps(CAR) + "\n```"

    meta = despiece.create("un auto deportivo muy detallado", ask=ask, home=tmp_path)
    assert "auto deportivo muy detallado" in asked[0] and "espejo_x" in asked[0]
    assert meta["name"] == "auto-deportivo" and meta["piezas"] >= 8
    assert despiece.meta("auto-deportivo", tmp_path)["tipo"] == "piezas"
    saved = json.loads(
        despiece.file_path("auto-deportivo", "piezas.json", tmp_path).read_text()
    )
    assert saved["titulo"] == "Auto deportivo"
    again = despiece.create("otro", ask=ask, home=tmp_path)
    assert again["name"] == "auto-deportivo-2"  # never overwrites
    assert [m["name"] for m in despiece.models(tmp_path)][0] in {
        "auto-deportivo",
        "auto-deportivo-2",
    }


def test_files_cannot_escape_their_folder(tmp_path):
    glb = tmp_path / "coche.glb"
    glb.write_bytes(b"glTF....")
    meta = despiece.register_file(str(glb), home=tmp_path)
    assert (
        despiece.file_path(meta["name"], "coche.glb", tmp_path).read_bytes()
        == b"glTF...."
    )
    for bad in ("../meta.json", "/etc/passwd", "..\\x"):
        with pytest.raises(CreatorError):
            despiece.file_path(meta["name"], bad, tmp_path)
    with pytest.raises(CreatorError):
        despiece.meta("../../etc", tmp_path)
    with pytest.raises(CreatorError):
        despiece.register_file(str(tmp_path / "nada.obj"), home=tmp_path)


def test_free_models_are_cc0_from_poly_haven_only(tmp_path):
    def server(request):
        path = request.url.path
        if path == "/assets":
            return httpx.Response(200, json={
                "vintage_car": {"name": "Vintage Car", "tags": ["car", "vehicle"], "categories": ["vehicles"]},
                "wooden_chair": {"name": "Wooden Chair", "tags": ["chair"], "categories": ["furniture"]},
            })  # fmt: skip
        if path == "/files/vintage_car":
            return httpx.Response(200, json={"gltf": {"1k": {"gltf": {
                "url": "https://dl.test/vintage_car_1k.gltf",
                "include": {"vintage_car.bin": {"url": "https://dl.test/bin"},
                            "../escape.txt": {"url": "https://dl.test/evil"}}}}}})  # fmt: skip
        if path == "/info/vintage_car":
            return httpx.Response(
                200, json={"name": "Vintage Car", "authors": {"Ana": "All"}}
            )
        return httpx.Response(200, content=b"data")

    http = httpx.Client(transport=httpx.MockTransport(server))
    assert [h["id"] for h in despiece.search_cc0("auto car", http)] == ["vintage_car"]
    meta = despiece.download("vintage_car", http, home=tmp_path)
    assert meta["licencia"] == "CC0" and "Ana" in meta["fuente"]
    folder = despiece.root(tmp_path) / meta["name"]
    assert (folder / "vintage_car_1k.gltf").exists() and (
        folder / "vintage_car.bin"
    ).exists()
    assert not (folder.parent / "escape.txt").exists()
    with pytest.raises(CreatorError):
        despiece.download("../x", http, home=tmp_path)


def test_routes(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.creator.routes import router

    monkeypatch.setattr(despiece, "root", lambda home=None: tmp_path / "despiece")
    glb = tmp_path / "motor.glb"
    glb.write_bytes(b"glTF")
    meta = despiece.register_file(str(glb))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    view = client.get(despiece.view(meta["name"])).json()
    assert view["url"] == f"/v1/creator/despiece/file/{meta['name']}/motor.glb"
    file = client.get(view["url"])
    assert (
        file.status_code == 200 and file.headers["content-type"] == "model/gltf-binary"
    )
    assert client.get("/v1/creator/despiece/view/nada").status_code == 404
    assert (
        client.get(
            f"/v1/creator/despiece/file/{meta['name']}/..%2Fmeta.json"
        ).status_code
        == 404
    )
    assert (
        client.get("/v1/creator/despiece").json()["modelos"][0]["name"] == meta["name"]
    )


def test_tool_answers_with_the_chat_link(tmp_path, monkeypatch):
    from openjarvis.tools.creator_tools import TakeApartModelTool

    monkeypatch.setattr(despiece, "root", lambda home=None: tmp_path / "d")
    glb = tmp_path / "rueda.glb"
    glb.write_bytes(b"glTF")
    out = TakeApartModelTool().execute(action="abrir", path=str(glb))
    assert out.success and "/v1/creator/despiece/view/rueda" in out.content
    bad = TakeApartModelTool().execute(action="abrir", path=str(tmp_path / "x.txt"))
    assert not bad.success

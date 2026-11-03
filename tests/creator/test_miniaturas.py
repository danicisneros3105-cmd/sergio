"""The gallery shows small pictures, not the 5 MB originals."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from openjarvis.creator import routes, studio


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "projects_root", lambda root=None: tmp_path)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_the_gallery_lists_a_small_version_and_serves_it(tmp_path, monkeypatch):
    folder = tmp_path / "imagenes"
    folder.mkdir()
    name = "imagen-" + "c3" * 12 + ".png"
    Image.new("RGB", (3000, 4000), (200, 30, 60)).save(folder / name)
    c = _client(tmp_path, monkeypatch)
    rows = c.get("/v1/creator/galeria").json()["elementos"]
    assert rows[0]["mini"] == f"/v1/creator/miniatura/{name}" and rows[0][
        "url"
    ].endswith(name)
    r = c.get(rows[0]["mini"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert len(r.content) < (folder / name).stat().st_size  # smaller than the original
    with Image.open(__import__("io").BytesIO(r.content)) as im:
        assert im.width <= 480
    assert (
        tmp_path / ".miniaturas" / ("imagen-" + "c3" * 12 + ".jpg")
    ).is_file()  # kept for next time


def test_odd_or_missing_names_are_refused(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/v1/creator/miniatura/no-existe.png").status_code == 404
    assert c.get("/v1/creator/miniatura/a%20b.png").status_code == 400

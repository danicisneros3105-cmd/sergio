"""Pictures from the internet: free sources, checked, credited."""

from __future__ import annotations

import io

from PIL import Image

from openjarvis.tools import imagenes_web as W


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2400, 1200), (120, 30, 60)).save(buf, "PNG")
    return buf.getvalue()


class R:
    def __init__(self, data=None, content=b""):
        self._d, self.content = data, content

    def json(self):
        return self._d


def fake_get(url, params=None, headers=None, **kw):
    if "openverse" in url:
        return R({"results": [{"url": "https://img/1.jpg", "title": "Torre", "creator": "Ana", "license": "by",
                               "license_version": "4.0", "foreign_landing_url": "https://flickr/1"},
                              {"url": "https://img/bad.jpg", "title": "Rota", "license": "cc0"}]})  # fmt: skip
    if "wikimedia" in url:
        return R({"query": {"pages": {}}})
    if url == "https://img/1.jpg":
        return R(content=_png())
    return R(content=b"not an image")


def test_finds_saves_and_credits(tmp_path, monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    res = W.buscar("torre eiffel", 2, get=fake_get, folder=tmp_path)
    assert len(res["imagenes"]) == 1  # the broken one is dropped
    im = res["imagenes"][0]
    assert im["licencia"] == "CC BY 4.0" and im["autor"] == "Ana"
    saved = Image.open(tmp_path / im["archivo"])
    assert max(saved.size) == 1600 and im["archivo"].startswith("imagen-web-")
    text = W.texto(res)
    assert (
        text.startswith("![Torre](/v1/creator/media/imagen-web-")
        and "Ana · CC BY 4.0 · Openverse" in text
    )


def test_nothing_found_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    res = W.buscar(
        "x", get=lambda *a, **k: R({"results": [], "query": {}}), folder=tmp_path
    )
    assert res["imagenes"] == [] and "No encontré" in W.texto(res)


def test_empty_request():
    assert "Dígame" in W.buscar("")["aviso"]

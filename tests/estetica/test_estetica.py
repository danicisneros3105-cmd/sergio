"""The 25 superskills, measuring images and the owner's Pinterest profile."""

from __future__ import annotations

import json
import re

import numpy as np
import pytest
from PIL import Image

from openjarvis.estetica import medir, pinterest, superskills


def test_there_are_25_superskills_each_complete_and_long_enough():
    text = superskills.FILE.read_text("utf-8")
    assert text.startswith("## Superskill 1:")  # no introduction
    blocks = re.split(r"(?m)^(?=## Superskill )", text)[1:]
    assert len(blocks) == 25
    for b in blocks:
        body = "\n".join(b.splitlines()[1:])
        words = [w for w in body.split() if re.search(r"\w", w)]
        assert len(words) >= 689, b.splitlines()[0]
        for part in ("Definición teórica", "Taxonomía visual", "Patrón de rechazo",
                     "Prompting / Parámetros de ejecución", "Matriz de evaluación (1–100)"):  # fmt: skip
            assert f"**{part}" in b, (b.splitlines()[0], part)
    skills = superskills.all_skills()
    assert sorted(skills) == list(range(1, 26)) and all(
        s["matriz"] for s in skills.values()
    )


def test_picks_few_that_fit_and_always_the_curation():
    got = superskills.pick("foto de un frasco de perfume de vidrio en penumbra")
    assert got[0] == 11 and 7 in got and got[-1] == 25 and len(got) <= 4
    assert superskills.brief_for_images("un meme de un gato") == ""
    note = superskills.brief_for_images("cartel minimalista para una lámpara")
    assert note and "text" in note or "minimal" in note


def _product(empty_left=True):
    im = np.full((200, 300, 3), 225, dtype="uint8")  # calm warm-grey field
    im[40:170, 170:250] = (60, 40, 30)  # a dark bottle on the right, ~17 % of the frame
    return Image.fromarray(im)


def test_measures_negative_space_mass_and_palette():
    m = medir.measure(_product())
    assert m["espacio_negativo"] > 0.75 and m["masa_dx"] > 0.1
    assert m["saturacion_media"] < 0.2 and m["tonos"] <= 2
    sc = medir.score(m)
    assert sc["1"]["puntos"] == 100 and sc["2"]["puntos"] == 100
    busy = Image.fromarray(
        (np.random.default_rng(1).random((200, 300, 3)) * 255).astype("uint8")
    )
    mb = medir.measure(busy)
    assert (
        mb["saturacion_media"] > m["saturacion_media"]
        and medir.score(mb)["9"]["puntos"] < 100
    )


def test_pinterest_needs_his_token(monkeypatch):
    monkeypatch.delenv("PINTEREST_TOKEN", raising=False)
    with pytest.raises(pinterest.PinterestError, match="PINTEREST_TOKEN"):
        pinterest.token()


class _Resp:
    def __init__(self, data=None, content=b"", status=200):
        self._data, self.content, self.status_code, self.headers = (
            data,
            content,
            status,
            {},
        )

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_ingest_reads_boards_measures_and_writes_his_profile(tmp_path, monkeypatch):
    import io

    monkeypatch.setenv("PINTEREST_TOKEN", "tok")
    monkeypatch.setattr(pinterest, "home", lambda: tmp_path)
    buf = io.BytesIO()
    _product().save(buf, "JPEG")
    calls = []

    class Http:
        def get(self, url, params=None, headers=None, timeout=0):
            calls.append(url)
            if url.endswith("/boards"):
                assert headers["Authorization"] == "Bearer tok"
                return _Resp(
                    {
                        "items": [
                            {"id": "b1", "name": "Perfumería"},
                            {"id": "b2", "name": "Otros"},
                        ]
                    }
                )
            if "/boards/b1/pins" in url:
                if (params or {}).get("bookmark"):
                    return _Resp(
                        {
                            "items": [
                                {
                                    "id": "p3",
                                    "media": {
                                        "images": {"600x": {"url": "https://i/3.jpg"}}
                                    },
                                }
                            ]
                        }
                    )
                return _Resp({"items": [{"id": "p1", "media": {"images": {"1200x": {"url": "https://i/1.jpg"}}}},
                                        {"id": "p2", "media": {}}], "bookmark": "x"})  # fmt: skip
            if url.startswith("https://i/"):
                return _Resp(content=buf.getvalue())
            raise AssertionError(url)

    res = pinterest.ingest(boards=["perfumería"], http=Http())
    assert res["imagenes"] == 2 and res["tableros"] == ["Perfumería"]
    assert not any("/boards/b2/" in c for c in calls)  # only the board asked for
    prof = json.loads((tmp_path / "perfil.json").read_text())
    assert prof["imagenes"] == 2 and "p10" in prof["general"]["espacio_negativo"]
    ranges = pinterest.owner_ranges(tmp_path / "perfil.json")
    lo, hi = ranges["1"]["espacio_negativo"]
    assert lo <= hi and lo > 0.5


def test_the_tool_guides_and_evaluates(tmp_path, monkeypatch):
    from openjarvis.tools.estetica_tool import CriterioEsteticoTool

    monkeypatch.setattr(pinterest, "home", lambda: tmp_path)
    t = CriterioEsteticoTool()
    g = t.execute(action="guia", encargo="caja de packaging de lujo")
    assert g.success and "Superskill 13" in g.content and "Superskill 25" in g.content
    path = tmp_path / "x.png"
    _product().save(path)
    e = json.loads(t.execute(action="evaluar", ruta=str(path)).content)
    assert (
        e["puntos_medibles"]["1"]["puntos"] == 100 and "sin sus tableros" in e["rangos"]
    )
    assert "Todavía no hay perfil" in t.execute(action="estado").content

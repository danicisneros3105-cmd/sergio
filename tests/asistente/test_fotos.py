"""Finding the person's photos by what the files say and, if asked, what they show."""

from __future__ import annotations

import datetime as dt
import os

from PIL import Image

from openjarvis.asistente import fotos


def _photo(path, size, taken=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, (120, 80, 60))
    if taken:
        ex = Image.Exif()
        ex[306] = taken.strftime("%Y:%m:%d %H:%M:%S")
        im.save(path, exif=ex)
    else:
        im.save(path)
    return path


def test_by_date_kind_and_shape(tmp_path):
    _photo(
        tmp_path / "Pictures" / "playa" / "IMG_1.jpg",
        (400, 300),
        dt.datetime(2026, 8, 10, 12),
    )
    _photo(tmp_path / "Pictures" / "IMG_2.jpg", (300, 400), dt.datetime(2026, 9, 1, 9))
    old = _photo(tmp_path / "Pictures" / "Screenshot 2026-10-02.png", (800, 450))
    os.utime(old, (dt.datetime(2026, 10, 2).timestamp(),) * 2)
    (tmp_path / "Pictures" / "nota.txt").write_text("x")
    places = fotos.roots(tmp_path)
    assert places == [tmp_path / "Pictures"]
    got = fotos.find(since="2026-08-01", until="2026-08-31", folders=places)
    assert [p["ruta"].endswith("IMG_1.jpg") for p in got["fotos"]] == [True]
    assert fotos.find(screenshots=True, folders=places)["total"] == 1
    assert fotos.find(orientation="vertical", folders=places)["fotos"][0][
        "ruta"
    ].endswith("IMG_2.jpg")
    assert fotos.find(name="playa", folders=places)["total"] == 1


def test_what_they_show_asks_the_model_with_numbered_sheets(tmp_path):
    for i in range(3):
        _photo(
            tmp_path / "Pictures" / f"f{i}.jpg", (200, 200), dt.datetime(2026, 1, 1 + i)
        )
    seen = []

    def ask(prompt, **kw):
        seen.append(prompt)
        assert isinstance(prompt[0], bytes) and "perro" in prompt[1]
        return "2"

    got = fotos.find(what="un perro", folders=[tmp_path / "Pictures"], ask=ask)
    assert len(seen) == 1 and got["total"] == 1 and got["revisadas_por_imagen"] == 3
    # newest first: number 2 is the middle one
    assert got["fotos"][0]["ruta"].endswith("f1.jpg")

"""Everyday jobs: slow PC and duplicate photos (``tools/daily_tools.py``)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

from openjarvis.tools.daily_tools import (
    DUPLICATES_FOLDER,
    PcCheckupTool,
    PhotosDuplicatesTool,
    describe_photos,
    photos_script,
    startup_script,
)


def _run(code: str, home: Path) -> dict:
    env = {"HOME": str(home), "USERPROFILE": str(home), "PATH": ""}
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def _photo(path: Path, size: tuple[int, int], seed: int, quality: int = 90) -> None:
    import random

    rnd = random.Random(seed)
    base = Image.new("RGB", (16, 12))
    base.putdata([tuple(rnd.randrange(256) for _ in range(3)) for _ in range(16 * 12)])
    path.parent.mkdir(parents=True, exist_ok=True)
    base.resize(size, Image.BICUBIC).save(path, quality=quality)


def test_finds_resized_copies_and_keeps_the_best(tmp_path: Path) -> None:
    gallery = tmp_path / "Pictures"
    _photo(gallery / "playa.jpg", (800, 600), 1)
    _photo(gallery / "copias" / "playa (1).jpg", (400, 300), 1, quality=60)
    _photo(gallery / "otra.png", (800, 600), 2)

    preview = _run(photos_script(""), tmp_path)
    assert preview["photos"] == 3 and preview["duplicates"] == 1
    assert preview["examples"][0]["keep"].endswith("playa.jpg")
    assert not preview["applied"]
    assert (gallery / "copias" / "playa (1).jpg").exists()  # preview moves nothing

    done = _run(photos_script("", apply=True), tmp_path)
    assert done["applied"]
    assert (gallery / DUPLICATES_FOLDER / "playa (1).jpg").exists()
    assert (gallery / "playa.jpg").exists() and (gallery / "otra.png").exists()

    again = _run(photos_script(""), tmp_path)  # the parked copies are not counted
    assert again["duplicates"] == 0

    back = _run(photos_script("", undo=True), tmp_path)
    assert back["undone"] == 1
    assert (gallery / "copias" / "playa (1).jpg").exists()


def test_plain_words() -> None:
    raw = "exit code 0 (script x)\nstdout:\n" + json.dumps(
        {
            "folder": "C:/Fotos",
            "photos": 10,
            "groups": 1,
            "duplicates": 2,
            "mb": 3.5,
            "applied": False,
            "examples": [{"keep": "a.jpg", "extra": ["b.jpg", "c.jpg"]}],
            "moved_to": "C:/Fotos/Duplicados (Sergio)",
        }
    )
    text = describe_photos(raw)
    assert "2 duplicadas" in text and "no moví nada" in text


def test_startup_script_quotes_names() -> None:
    script = startup_script(["Spotify", "x'; rm", "a"], on=False)
    assert '["Spotify", "x; rm"]' in script and "$false" in script
    assert "$true" in startup_script(["Spotify"], on=True)


class _Fake:
    def __init__(self, result: str) -> None:
        self.sent: list[dict] = []
        self.result = result

    def __call__(self, method: str, path: str, **kw):
        self.sent.append(kw["json"])
        return {"result": self.result}


def test_tools_send_the_right_action(monkeypatch) -> None:
    fake = _Fake("exit code 0\noutput:\nMemoria: 2 GB libres")
    tool = PcCheckupTool()
    monkeypatch.setattr(tool, "_call", fake)
    assert tool.execute(mode="diagnose").success
    assert fake.sent[0]["action"] == "terminal"
    assert "Win32_StartupCommand" in fake.sent[0]["command"]
    assert not tool.execute(mode="startup_off").success  # names are needed

    photos = PhotosDuplicatesTool()
    fake = _Fake('exit code 0\nstdout:\n{"undone": 3, "folder": "C:/F"}')
    monkeypatch.setattr(photos, "_call", fake)
    result = photos.execute(undo=True)
    assert result.success and "3 fotos" in result.content
    assert fake.sent[0]["action"] == "python"


def test_registered() -> None:
    import openjarvis.tools as tools

    assert tools.daily_tools.PcCheckupTool().spec.name == "pc_checkup"
    assert PhotosDuplicatesTool().spec.name == "photos_duplicates"

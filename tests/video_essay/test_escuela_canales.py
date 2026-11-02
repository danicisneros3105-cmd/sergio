"""The school on channels: latest videos, 30 fps, light, camera and script."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from openjarvis.video_essay import escuela

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sin ffmpeg")


def test_the_four_channels_are_styles_with_their_latest_20_at_30_fps():
    refs = escuela.references()
    want = {
        "shorts-animados": ("@RicksClips3000", "shorts"),
        "explicativo-tipografico": (
            "@your.nextcore",
            "videos",
        ),  # its Shorts tab is empty
        "ensayo-documental": ("@johnnyharris", "videos"),
        "reto-narrado": ("@ryan", "videos"),
    }
    for key, (handle, tab) in want.items():
        cat = refs[key]
        assert cat["fps"] == 30
        (ch,) = cat["canales"]
        assert (
            ch["url"].endswith(handle) and ch["pestana"] == tab and ch["ultimos"] == 20
        )
        # the style's own name never says who it comes from
        assert handle.strip("@").lower() not in cat["nombre"].lower()
    assert escuela.status()["categorias"]["ensayo-documental"]["videos"] == 20


def test_channel_links_asks_the_tab_then_the_other_and_keeps_a_day(tmp_path):
    asked = []

    def run(args):
        asked.append(args[-1])
        if args[-1].endswith("/shorts"):
            return ""  # no shorts: the videos tab is used
        return "\n".join(f"abcdefghij{i} 600" for i in range(10)) + "\nnot-an-id 5\n"

    ch = {"url": "https://www.youtube.com/@canal", "pestana": "shorts", "ultimos": 5}
    links = escuela.channel_links(ch, root=tmp_path, run=run)
    assert asked == [
        "https://www.youtube.com/@canal/shorts",
        "https://www.youtube.com/@canal/videos",
    ]
    assert links == [f"https://www.youtube.com/watch?v=abcdefghij{i}" for i in range(5)]
    assert (
        escuela.channel_links(ch, root=tmp_path, run=lambda a: 1 / 0) == links
    )  # cached
    with pytest.raises(ValueError):
        escuela.channel_links(
            {"url": "https://evil.example/@x"}, root=tmp_path, run=run
        )


def test_links_of_joins_links_and_channels_without_repeats(tmp_path):
    cat = {
        "links": ["https://www.youtube.com/shorts/abcdefghij0"],
        "canales": [
            {"url": "https://www.youtube.com/@c", "pestana": "videos", "ultimos": 2}
        ],
    }
    got = escuela.links_of(
        cat, root=tmp_path, run=lambda a: "abcdefghij0\nabcdefghij1\n"
    )
    assert got == [
        "https://www.youtube.com/watch?v=abcdefghij0",
        "https://www.youtube.com/watch?v=abcdefghij1",
    ]


def test_the_public_edition_never_downloads_other_peoples_videos(tmp_path, monkeypatch):
    monkeypatch.setenv("SERGIO_EDICION", "publica")
    with pytest.raises(RuntimeError, match="edición pública"):
        escuela.download(
            "https://www.youtube.com/watch?v=abcdefghij0", tmp_path, runner=lambda a: 0
        )


def test_light_reads_contrast_shadows_highlights_warmth_and_vignette():
    dark = np.zeros((40, 60, 3), np.uint8)
    flat = escuela.light_of(dark)
    assert flat["brillo"] == 0 and flat["contraste"] == 0 and flat["sombras"] == 1.0
    half = dark.copy()
    half[:, 30:] = 255
    assert (
        escuela.light_of(half)["contraste"] > 0.9
        and escuela.light_of(half)["luces"] == 0.5
    )
    warm = np.zeros((40, 60, 3), np.uint8)
    warm[..., 0] = 200
    warm[..., 2] = 60
    assert escuela.light_of(warm)["calidez"] > 0.5
    spot = np.full((40, 60, 3), 30, np.uint8)
    spot[13:27, 20:40] = 220  # lit in the middle, dark corners
    assert escuela.light_of(spot)["vineta"] > 3


def test_the_script_is_read_for_its_shape():
    words = [
        {"t": 0.0, "w": "This"}, {"t": 0.3, "w": "man"}, {"t": 0.6, "w": "lost"}, {"t": 0.9, "w": "everything."},
        {"t": 1.4, "w": "But"}, {"t": 1.7, "w": "you"}, {"t": 2.0, "w": "won't"}, {"t": 2.3, "w": "believe"},
        {"t": 2.6, "w": "why?"}, {"t": 5.0, "w": "Here's"}, {"t": 5.3, "w": "the"}, {"t": 5.6, "w": "thing:"},
        {"t": 5.9, "w": "3"}, {"t": 6.2, "w": "days."},
    ]  # fmt: skip
    g = escuela.script_of(words, 60.0)
    assert g["palabras_por_minuto"] == 14.0 and g["frases"] == 3
    assert (
        g["primera_frase"] == "This man lost everything."
        and g["primera_frase_palabras"] == 4
    )
    assert (
        g["preguntas_por_min"] == 1.0
        and g["giros_por_min"] >= 1
        and g["lazos_por_min"] >= 1
    )
    assert g["numeros_por_min"] >= 1 and g["tu_por_frase"] > 0
    assert g["partes"] == 2 and g["pausas_por_min"] >= 1  # the 2.4 s silence
    assert escuela.script_of([], 10) == {}


def _panning(path: Path) -> Path:
    """2 s at 30 fps: a test pattern that slides right, then a hard cut to black."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=s=640x360:r=30:d=1.5",
         "-f", "lavfi", "-i", "color=black:s=320x180:r=30:d=0.5",
         "-filter_complex", "[0]crop=320:180:x='t*120':y=60[a];[a][1]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path


@needs_ffmpeg
def test_measured_at_30_fps_one_second_at_a_time(tmp_path, monkeypatch):
    seen = []
    real = escuela._chunks

    def spy(*a, **k):
        for chunk in real(*a, **k):
            seen.append(len(chunk))
            yield chunk

    monkeypatch.setattr(escuela, "_chunks", spy)
    m = escuela.measure(_panning(tmp_path / "p.mp4"), words=[], fps=30)
    assert seen and max(seen) == 30  # never more than one second in memory
    assert m["cortes"] == [1.5]  # exact to the frame, not to a quarter second
    first = m["segundos"][0]
    assert first["camara"] > 0.1  # the picture slides
    r = m["resumen"]
    assert r["fps_medido"] == 30 and r["negro"] > 0 and r["contraste"] > 0.2
    json.dumps(m)  # all of it can be saved


@needs_ffmpeg
def test_study_uses_the_styles_fps(tmp_path, monkeypatch):
    got = {}
    monkeypatch.setattr(
        escuela,
        "measure",
        lambda path, fps=4: got.setdefault("fps", fps) and {"resumen": {}},
    )
    escuela.study("https://www.youtube.com/watch?v=abcdefghij0", "reto-narrado", root=tmp_path,
                  watcher=lambda p: {}, fetch=lambda u, d: tmp_path / "x.mp4", fps=30)  # fmt: skip
    assert got["fps"] == 30


def test_a_channel_can_be_added_by_its_link(tmp_path, monkeypatch):
    monkeypatch.setattr(escuela, "home", lambda: tmp_path)
    r = escuela.add(
        [
            "https://www.youtube.com/@otro.canal/shorts",
            "https://www.youtube.com/shorts/abcdefghij0",
        ],
        "Mis shorts",
    )
    assert r == {"categoria": "mis-shorts", "agregados": 2}
    cat = escuela.references()["mis-shorts"]
    assert cat["canales"] == [
        {
            "url": "https://www.youtube.com/@otro.canal",
            "pestana": "shorts",
            "ultimos": 20,
        }
    ]
    assert cat["fps"] == 30 and cat["links"] == [
        "https://www.youtube.com/watch?v=abcdefghij0"
    ]
    escuela.add(
        ["https://www.youtube.com/@otro.canal"], "Mis shorts"
    )  # the same channel twice
    assert len(escuela.references()["mis-shorts"]["canales"]) == 1


def test_videos_longer_than_the_limit_are_not_studied(tmp_path):
    out = "\n".join(
        ["shortvideo1 1800", "compile0001 10800", "livestream1 NA", "shortvideo2 3000"]
    )
    ch = {
        "url": "https://www.youtube.com/@canal",
        "pestana": "videos",
        "ultimos": 3,
        "max_minutos": 60,
    }
    links = escuela.channel_links(ch, root=tmp_path, run=lambda a: out)
    ids = [x.rsplit("=", 1)[1] for x in links]
    assert ids == ["shortvideo1", "livestream1", "shortvideo2"]  # the 3-hour one is out
    ch2 = {**ch, "max_minutos": 0}
    assert (
        len(escuela.channel_links(ch2, root=tmp_path, run=lambda a: out)) == 3
    )  # no limit: first 3 asked


def test_the_hand_written_script_rules_join_the_superskill(tmp_path, monkeypatch):
    monkeypatch.setattr(escuela, "home", lambda: tmp_path / "escuela")
    monkeypatch.setattr(
        "openjarvis.video_essay.style.learned_dir", lambda: tmp_path / "estilos"
    )
    folder = tmp_path / "escuela" / "shorts-animados"
    folder.mkdir(parents=True)
    summary = {"duracion_s": 60, "toma_mediana_s": 2.0, "cortes_por_segundo": 0.5, "cortes_primeros_3s": 1,
               "texto_en_pantalla": 0.1, "caras": 0.0, "movimiento_medio": 0.1, "vertical": True,
               "colores": ["#112233"], "gancho": "x"}  # fmt: skip
    (folder / "a.json").write_text(
        json.dumps({"url": "u", "medido": {"resumen": summary, "tomas": [2.0]}})
    )
    res = escuela.synthesize(
        "shorts-animados",
        ask=lambda p: "\n".join(
            f"{i}. Rule {i} from the data here." for i in range(1, 7)
        ),
    )
    assert any("middle of the strangest moment" in r for r in res["reglas"])
    assert (
        "cliffhanger"
        in (
            tmp_path / "escuela" / "superskills" / "shorts-animados" / "SKILL.md"
        ).read_text()
    )

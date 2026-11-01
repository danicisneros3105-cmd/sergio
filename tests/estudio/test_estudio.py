"""The four studio programs: each does its one job and never invents."""

from __future__ import annotations

import json

from PIL import Image, ImageDraw

from openjarvis.estudio import clips_cine, miniaturas, radar, titulos


def _yt(lines):
    return lambda args: "\n".join(json.dumps(x) for x in lines)


def test_clips_only_real_years_and_named_film(monkeypatch):
    monkeypatch.setattr("openjarvis.video_essay.sources.web_allowed", lambda: True)
    monkeypatch.setattr(
        "openjarvis.video_essay.sources.search_archive", lambda q, n: []
    )
    ask = lambda p: json.dumps({"scenes": [  # noqa: E731
        {"film": "Rocky", "year": 1976, "scene": "running up the steps", "why": "no rendirse"},
        {"film": "Inventada", "year": "pronto", "scene": "x"},
        {"film": "Rocky", "year": 1976, "scene": "otra"}]})  # fmt: skip
    runner = _yt([
        {"id": "a1", "title": "Rocky (1976) - Running up the steps scene | Movieclips", "channel": "Movieclips",
         "duration": 120},
        {"id": "b2", "title": "Rocky FULL MOVIE", "channel": "x", "duration": 7000},
        {"id": "c3", "title": "Cooking pasta", "channel": "y", "duration": 90}])  # fmt: skip
    res = clips_cine.buscar("no rendirse nunca", ask=ask, runner=runner)
    assert [s["pelicula"] for s in res["escenas"]] == ["Rocky"]
    urls = [c["url"] for c in res["escenas"][0]["clips"]]
    assert urls == ["https://www.youtube.com/watch?v=a1"]
    assert "reclamarlas" in res["aviso"]


def test_clips_without_model_use_known_scenes(monkeypatch):
    monkeypatch.setattr("openjarvis.video_essay.sources.web_allowed", lambda: True)
    scenes = clips_cine.scenes_for("caer y levantarse", ask=lambda p: "no json")
    assert scenes and all(s["origen"] == "lista conocida" for s in scenes)


def _frame(face_side: str = "right") -> Image.Image:
    img = Image.new("RGB", (640, 360), (30, 60, 120))
    d = ImageDraw.Draw(img)
    x = 420 if face_side == "right" else 80
    d.ellipse((x, 80, x + 140, 260), fill=(240, 200, 160))
    return img


def test_thumbnails_three_variants_that_read_small(tmp_path):
    src = tmp_path / "foto.png"
    _frame().save(src)
    res = miniaturas.crear(
        str(src), titulo="Los 5 errores al invertir", out_dir=tmp_path / "out"
    )
    assert res["palabras"] and "5" in res["palabras"]
    assert len(res["miniaturas"]) == 1  # one picture: one frame
    m = res["miniaturas"][0]
    assert Image.open(m["archivo"]).size == miniaturas.SIZE
    assert m["contraste_en_telefono"] > 1.0


def test_thumbnail_words_are_few_and_keep_numbers():
    w = miniaturas.words_from("Cómo gané 1000 dólares en una semana sin experiencia")
    assert 2 <= len(w) <= 4 and "1000" in w


def test_titles_judge_punishes_lies_and_shouting():
    good = titulos.judge(
        "Por qué el 90 % de los negocios cierra en 5 años", "negocios", "youtube"
    )
    bad = titulos.judge("NO CREERÁS ESTO!!! INCREÍBLE", "negocios", "youtube")
    assert good["puntos"] > bad["puntos"]
    assert "promete de más" in bad["por_que"]


def test_titles_clean_emojis_and_rank(monkeypatch):
    ask = lambda p: json.dumps({"titles": [  # noqa: E731
        {"text": "Negocios: el error que todos cometen 🔥", "angle": "error comun"},
        {"text": "Negocios: el error que todos cometen", "angle": "error comun"},
        {"text": "3 negocios que puedes empezar con $100", "angle": "numero"}]})  # fmt: skip
    res = titulos.generar("negocios", "youtube", ask=ask)
    texts = [t["titulo"] for t in res["titulos"]]
    assert all("🔥" not in t for t in texts)
    assert len(texts) == len(set(texts)) == 2


def test_titles_without_model_say_so():
    res = titulos.generar("ahorro", "reels", ask=lambda p: "")
    assert res["origen"] == "plantillas" and res["titulos"]
    assert "plantillas" in titulos.texto(res)


class _R:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def test_radar_drops_invented_opportunities(monkeypatch, tmp_path):
    from openjarvis.automatiza import tendencias

    monkeypatch.setattr(tendencias, "read", lambda *a, **k: {
        "pais": "EC", "fuentes": ["Google Trends"],
        "senales": [{"tema": "inteligencia artificial", "fuente": "Google Trends", "cifra": 5000,
                     "unidad": "búsquedas", "detalle": ""}]})  # fmt: skip

    def get(url, params=None, **k):
        return _R(["x", [f"{params['q']} para principiantes"]])

    runner = _yt(
        [
            {
                "id": "v1",
                "title": "5 usos de la IA",
                "channel": "c",
                "view_count": 9000,
                "duration": 480,
            }
        ]
    )
    ask = lambda p: json.dumps({  # noqa: E731
        "audiencia": "Gente que empieza.",
        "oportunidades": [
            {"signal": "inteligencia artificial", "format": "short", "hook": "La IA ya hace esto", "why": "Trends"},
            {"signal": "algo inventado", "format": "long", "hook": "x", "why": "y"}],
        "formato": "8 minutos", "evitar": ["títulos vagos"]})  # fmt: skip
    res = radar.analizar(
        "ia", "EC", "instagram", ask=ask, get=get, runner=runner, home=tmp_path
    )
    assert len(res["oportunidades"]) == 1
    assert res["busquedas"] and res["patrones"]["con_numero"] == 1.0
    assert "Mosseri" in res["algoritmo"]["fuente"]
    text = radar.texto(res)
    assert "no se adivinan" in text and "Público" in text


def test_radar_without_data_says_so(monkeypatch, tmp_path):
    from openjarvis.automatiza import tendencias

    monkeypatch.setattr(tendencias, "read", lambda *a, **k: {})
    res = radar.analizar(
        "", get=lambda *a, **k: _R([]), runner=lambda a: "", home=tmp_path
    )
    assert res["aviso"] and res["oportunidades"] == []


def test_four_tools_in_their_neuron():
    from openjarvis.connectome import neurons

    assert set(neurons.tools_of("estudio")) == {
        "clips_cine",
        "miniaturas",
        "titulos_video",
        "radar_tendencias",
    }

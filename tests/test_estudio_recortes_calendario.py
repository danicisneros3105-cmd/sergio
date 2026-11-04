"""Creator tools x2 (owner, 4 Nov 2026): the best moments of a long video as
shorts, and a content calendar with judged hooks."""

from __future__ import annotations

import datetime as dt
import json

from openjarvis.estudio import calendario, recortes


def _talk(text: str, start: float = 0.0, wps: float = 2.6):
    out, t = [], start
    for tok in text.split():
        out.append({"text": tok, "start": t, "end": t + 1 / wps * 0.9})
        t += 1 / wps
    return out


FLUFF = (
    "eh bueno o sea este pues bueno la verdad es que eh no sé cómo explicarlo bien. "
    * 6
)
GOLD = (
    "En 2019 perdí 40.000 dólares en una sola semana. Nadie me avisó del error. "
    "Lo que pasó fue que firmé con Tomás sin leer el contrato. "
    "¿Sabe qué decía la cláusula 7? Que todo el dinero era suyo. "
    "Desde ese día leo cada contrato dos veces y pregunto por cada número. "
    "Esa costumbre me ahorró 12.000 dólares el año pasado."
)


def test_sentences_end_at_punctuation_or_a_pause():
    words = _talk("hola a todos. esto sigue") + _talk("y esto otro", start=10)
    groups = recortes.sentences(words)
    assert [len(g) for g in groups] == [3, 2, 3]


def test_the_concrete_moment_with_a_hook_wins_over_the_filler():
    words = _talk(FLUFF) + _talk(GOLD, start=len(FLUFF.split()) / 2.6 + 1)
    found = recortes.moments(words, min_s=15, max_s=60, n=2)
    assert found, "should find something"
    best = found[0]
    assert "2019" in best.hook or "40.000" in best.text
    assert "empieza con un gancho" in best.reasons and "datos concretos" in best.reasons
    assert all(m.score <= best.score for m in found)
    # never overlapping
    for a in found:
        for b in found:
            if a is not b:
                assert a.end <= b.start or a.start >= b.end
    assert 15 <= best.seconds <= 61


def test_fillers_cost_points_and_slow_speech_too():
    fluffy, _ = recortes.judge(recortes.sentences(_talk(FLUFF)))
    gold, why = recortes.judge(recortes.sentences(_talk(GOLD)))
    assert gold > fluffy and any(
        "muletillas" in r for r in recortes.judge(recortes.sentences(_talk(FLUFF)))[1]
    )
    slow, why_slow = recortes.judge(recortes.sentences(_talk(GOLD, wps=1.0)))
    assert "muy lento" in why_slow and slow < gold


def test_srt_words_and_plain_report(tmp_path):
    srt = "1\n00:00:01,000 --> 00:00:03,000\nHola mundo\n\n2\n00:01:00,500 --> 00:01:02,500\nOtra frase aquí\n"
    words = recortes.from_srt(srt)
    assert [w.text for w in words] == ["Hola", "mundo", "Otra", "frase", "aquí"]
    assert words[0].start == 1.0 and abs(words[2].start - 60.5) < 1e-6
    report = recortes.texto({"video": "/x/mi-podcast.mp4", "palabras": 900, "momentos": [
        {"n": 1, "desde": 65.2, "hasta": 112.0, "segundos": 46.8, "gancho": "En 2019 perdí todo",
         "puntos": 88, "por_que": ["empieza con un gancho"]}]})  # fmt: skip
    assert "1:05-1:52" in report and "88/100" in report and "mi-podcast.mp4" in report
    assert "No encontré" in recortes.texto(
        {"video": "v", "palabras": 0, "momentos": []}
    )


def test_find_says_plainly_when_the_file_is_missing(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        recortes.find(str(tmp_path / "nada.mp4"))


def test_calendar_days_spread_and_start_on_a_fresh_week():
    wednesday = dt.date(2026, 11, 4)
    d = calendario.days(wednesday, 2, 3)
    assert d[0] == dt.date(2026, 11, 9)  # next Monday
    assert [x.weekday() for x in d] == [0, 2, 4, 0, 2, 4]
    assert len(set(d)) == len(d)
    assert calendario.days(dt.date(2026, 11, 9), 1, 3)[0] == dt.date(2026, 11, 9)


def test_calendar_judges_hooks_and_never_invents_an_hour(tmp_path):
    ideas = [
        {"titulo": "El error de 40.000 dólares", "gancho": "Perdí 40.000 dólares por no leer esto",
         "formato": "historia con giro", "que": "La cláusula 7."},
        {"titulo": "Hoy hablamos de finanzas", "gancho": "Hoy vamos a hablar de un tema muy interesante para todos",
         "formato": "lista de datos", "que": "Consejos."},
        {"titulo": "INCREÍBLE truco GRATIS", "gancho": "No creerás este truco GRATIS TOTAL", "formato": "cómo hacerlo",
         "que": "Un truco."},
    ]  # fmt: skip
    asked = []

    def ask(prompt, **kw):
        asked.append(prompt)
        return json.dumps({"ideas": ideas})

    out = calendario.plan("finanzas personales", semanas=1, por_semana=3, ask=ask,
                          tendencias=["presupuesto 2027"], hoy=dt.date(2026, 11, 9))  # fmt: skip
    rows = out["publicaciones"]
    assert len(rows) == 3 and rows[0]["dia"] == "lunes"
    assert rows[0]["revisar_gancho"] == []
    assert rows[1]["revisar_gancho"]  # too long and vague
    assert any("promete" in p for p in rows[2]["revisar_gancho"])
    assert "presupuesto 2027" in asked[0] and "never invent" in asked[0]
    assert "estadísticas" in out["hora"]
    text = calendario.texto(out)
    assert "gancho a revisar" in text and "lunes 2026-11-09" in text
    saved = calendario.save_xlsx(out, tmp_path)
    assert saved.endswith(".xlsx")
    from openjarvis.asistente import xlsx

    assert xlsx.read(saved)[0]["filas"][1][3] == "El error de 40.000 dólares"


def test_a_moment_is_cut_vertical(tmp_path):
    import shutil
    import subprocess

    import pytest

    from openjarvis.video_essay import render

    ff = render.ffmpeg()
    if not shutil.which(ff) and not __import__("os").path.exists(ff):
        pytest.skip("no ffmpeg")
    src = tmp_path / "largo.mp4"
    subprocess.run(
        [ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=8",
         "-f", "lavfi", "-i", "sine=f=300:d=8", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)],
        check=True,
    )  # fmt: skip
    files = recortes.cut(str(src), [{"desde": 2.0, "hasta": 6.0}], subtitles=False)
    assert len(files) == 1 and files[0].endswith("recorte-01.mp4")
    from openjarvis.video_essay import pro

    info = pro._probe(
        __import__("pathlib").Path(files[0]), shutil.which("ffprobe") or "ffprobe"
    )
    assert info["h"] > info["w"]  # 9:16

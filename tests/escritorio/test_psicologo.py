"""The consulting room: notes, questionnaires, risk, the animated scene."""

from __future__ import annotations

import time

import pytest
from sergio_escritorio import secure
from sergio_escritorio.psicologo import (
    GAD7,
    PHQ9,
    Consult,
    at_risk,
    explain_score,
    score,
)


def test_phq9_and_gad7_scoring():
    r = score(PHQ9, [1, 1, 2, 1, 0, 1, 1, 0, 0])
    assert (r["puntos"], r["nivel"], r["riesgo"]) == (7, "leve", False)
    r = score(PHQ9, [3, 3, 3, 3, 3, 3, 3, 3, 1])
    assert r["nivel"] == "grave" and r["riesgo"]
    g = score(GAD7, [2, 2, 2, 2, 1, 1, 1])
    assert (g["puntos"], g["nivel"]) == (11, "moderado")
    assert "Bajó 4" in explain_score(score(GAD7, [1, 1, 1, 1, 1, 1, 1]), g)
    assert "no un diagnóstico" in explain_score(g)
    with pytest.raises(ValueError):
        score(GAD7, [1, 2])


def test_risk_words():
    assert at_risk("a veces pienso que no quiero vivir") and at_risk("Quiero morirme")
    assert not at_risk("me muero de risa con esa serie") and not at_risk(
        "tuve un mal día"
    )


def test_sessions_notes_and_privacy(tmp_path):
    clock = [1000.0]
    c = Consult(tmp_path / "p.json", clock=lambda: clock[0])
    c.said("duermo mal")
    c.replied(
        {
            "respuesta": "Te escucho.",
            "nota": {"datos": "insomnio", "analisis": "", "plan": "higiene del sueño"},
            "animo": -2,
            "temas": ["sueño"],
        }
    )
    assert c.messages() == [
        {"role": "user", "content": "duermo mal"},
        {"role": "assistant", "content": "Te escucho."},
    ]
    clock[0] += 4 * 3600  # a new session after a long pause
    c.said("hoy mejor")
    assert len(c.sessions) == 2 and c.notes()[0]["plan"] == "higiene del sueño"
    raw = (tmp_path / "p.json").read_bytes()
    assert b"duermo mal" not in raw or not secure.available()
    again = Consult(tmp_path / "p.json")
    assert again.mood_trend() == [-2.0] and again.summary_for_profile()["temas"] == [
        "sueño"
    ]


def test_consult_orders():
    from sergio_escritorio.quick import parse_quick

    assert parse_quick("quiero hablar con mi psicólogo").kind == "consult"
    assert parse_quick("necesito desahogarme").kind == "consult"


def test_the_room_animates_and_the_chat_works(tmp_path):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from sergio_escritorio.psicologo_ui import ConsultWindow, Scene

    app = QApplication.instance() or QApplication([])
    scene = Scene()
    for state in ("listening", "writing", "speaking"):
        if state == "writing":
            scene.write()
        elif state == "speaking":
            scene.speak(2)
        img = QImage(500, 480, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        scene.draw(p, QRectF(0, 0, 500, 480), 1.3)
        p.end()
        assert img.pixelColor(250, 240) != QColor(0, 0, 0)
    for _ in range(12):  # a full page turns
        scene.write()
    assert len(scene.lines) <= 9
    spoken = []
    c = Consult(tmp_path / "p.json")
    w = ConsultWindow(
        c,
        lambda m, n: {"respuesta": "Cuénteme más.", "nota": {"datos": "x"}},
        spoken.append,
        lambda: None,
    )
    w.hear("me siento solo")
    deadline = time.monotonic() + 3
    while not spoken and time.monotonic() < deadline:
        app.processEvents()
    assert spoken == ["Cuénteme más."] and c.notes()[-1]["datos"] == "x"
    w.start_quiz("gad7")
    for _ in range(7):
        w._quiz_answer(1)
    assert c.tests[-1]["puntos"] == 7 and "GAD-7" in spoken[-1]
    w.close()

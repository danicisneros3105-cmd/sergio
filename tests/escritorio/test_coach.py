"""The coach on the PC: goals, sessions in your free time, video marks, school."""

from __future__ import annotations

from datetime import datetime

import pytest

from sergio_escritorio.coach import Coach, annotate_video, goal_kind, parse_goal, record_video, school_reminders

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

PLAN = {
    "titulo": "Doble lift",
    "resumen": "En 3 semanas",
    "sesiones": [
        {"dia": 0, "minutos": 15, "objetivo": "agarre", "pasos": ["a"], "video": False},
        {"dia": 2, "minutos": 20, "objetivo": "doble lift lento", "pasos": ["b"], "video": True},
        {"dia": 4, "minutos": 20, "objetivo": "velocidad", "pasos": ["c"]},
    ],
}
NOW = datetime(2026, 10, 5, 9, 0).timestamp()


def test_kinds_and_goal_phrases():
    assert goal_kind("francés") == "idioma" and goal_kind("examen de física") == "examen"
    assert goal_kind("doble lift con cartas") == "habilidad"
    assert parse_goal("estoy aprendiendo un truco de cartas") == "un truco de cartas"
    assert parse_goal("tengo examen de física el viernes") == "examen de física el viernes"
    assert parse_goal("abre spotify") is None


def test_sessions_land_in_free_time_and_results_shape_the_next(tmp_path):
    clock = [NOW]
    coach = Coach(tmp_path / "c.json", clock=lambda: clock[0])
    placed = []

    def place(after, minutes):
        placed.append((after, minutes))
        return after + 3600 * 10  # "your evening"

    goal = coach.add_goal("doble lift con cartas", PLAN, place)
    dues = [s["due"] for s in goal["sesiones"]]
    assert dues == sorted(dues) and len(placed) == 3 and goal["sesiones"][1]["video"]
    assert coach.due_sessions() == []
    clock[0] = dues[0] + 1
    (g, s), = coach.due_sessions()
    assert s["n"] == 1
    coach.finish(g, s, {"metricas": {"limpieza": 6, "x": "no"}, "errores_tipo": {"flash": 2}, "nivel": "principiante",
                        "feedback": "Más lento.", "dificultad": 1})  # fmt: skip
    assert goal["sesiones"][1]["minutos"] == 25 and coach.progress(goal)["series"] == {"limpieza": [6.0]}
    again = Coach(tmp_path / "c.json")
    assert again.goals[0]["errores"] == {"flash": 2} and "doble lift" in again.describe()
    lesson = again.for_lesson(again.goals[0])
    assert lesson["sesion"]["n"] == 2 and lesson["errores_frecuentes"] == [("flash", 2)]
    assert again.find("DOBLE LIFT") is not None
    assert again.summary_for_profile()["doble lift con cartas"]["sesiones"] == "1/3"


def test_practice_video_gets_green_and_red_circles(tmp_path):
    frames = iter([np.full((120, 160, 3), 40, np.uint8) for _ in range(30)])
    clock = [0.0]

    def tick(dt):
        clock[0] += dt

    raw = record_video(lambda: next(frames, None), tmp_path / "raw.mp4", seconds=2.0, fps=15, clock=lambda: clock[0], sleep=tick)
    marks = [
        {"t": 0.0, "duracion": 1.0, "x": 0.25, "y": 0.5, "r": 0.1, "bien": True, "texto": "buen ángulo"},
        {"t": 1.0, "duracion": 1.0, "x": 0.75, "y": 0.5, "r": 0.1, "bien": False, "texto": "se ve la carta"},
    ]
    out = annotate_video(raw, marks, tmp_path / "out.mp4")
    cap = cv2.VideoCapture(str(out))
    frames_out = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames_out.append(frame)
    assert len(frames_out) >= 25
    early, late = frames_out[8], frames_out[-3]
    b, g, r = early[60, 160 // 4 + 16].astype(int)  # on the green circle (right edge)
    assert g > r + 40 and g > b + 40
    b, g, r = late[60, 3 * 160 // 4 + 16].astype(int)  # on the red circle
    assert r > g + 40 and r > b + 40


def test_school_items_become_reminders():
    now = datetime(2026, 10, 5, 12, 0)
    data = {"tareas": [{"materia": "Física", "titulo": "informe", "fecha": "2026-10-08"},
                       {"materia": "Arte", "titulo": "vieja", "fecha": "2026-10-01"}],
            "examenes": [{"materia": "Química", "fecha": "2026-10-09", "temas": ["mol"]}]}  # fmt: skip
    items = school_reminders(data, now)
    texts = [t for _w, t in items]
    assert len(items) == 3 and "mañana se entrega informe de Física" in texts
    assert "examen de Química en 3 días" in texts and "examen de Química en 1 día" in texts


def test_coach_orders():
    from sergio_escritorio.quick import parse_quick

    assert parse_quick("estoy aprendiendo francés").kind == "learn"
    assert parse_quick("mis metas").kind == "goals"
    assert parse_quick("practiquemos francés").kind == "practice"
    assert parse_quick("revisa mi plataforma escolar").kind == "school"
    assert parse_quick("mi plataforma escolar es aula.colegio.edu.ec").arg == "https://aula.colegio.edu.ec"
    assert parse_quick("cómo voy en el gimnasio").kind == "gym_report"


def test_session_window_shows_the_lesson_and_saves_results(tmp_path):
    import time

    from PySide6.QtWidgets import QApplication

    from sergio_escritorio.coach_ui import CoachWindow, PracticeCard, SessionWindow, lesson_html

    app = QApplication.instance() or QApplication([])
    coach = Coach(tmp_path / "c.json")
    goal = coach.add_goal("francés", PLAN, lambda after, m: after)
    session = goal["sesiones"][0]
    lesson = {"titulo": "Saludos", "contenido": [{"tipo": "vocabulario", "texto": "Salut = hola (informal)", "respuesta": "x"}]}
    assert "Salut" in lesson_html(lesson)
    done = []
    window = SessionWindow(goal, session, lambda: lesson, None, lambda text: {"feedback": "bien", "metricas": {"aciertos": 8}}, done.append)
    deadline = time.monotonic() + 3
    while "Salut" not in window.lesson.toHtml() and time.monotonic() < deadline:
        app.processEvents()
    assert "Salut" in window.lesson.toHtml()
    window.results.setPlainText("8 de 10")
    window._finish()
    deadline = time.monotonic() + 3
    while not done and time.monotonic() < deadline:
        app.processEvents()
    assert done == [{"feedback": "bien", "metricas": {"aciertos": 8}}]
    goals = CoachWindow(coach, lambda gid: None)
    goals.open()
    assert goals.goals.count() == 1 and "Doble lift" in goals.detail.toHtml()
    card = PracticeCard(goal, session, lambda: None, lambda: None, lambda: None)
    assert card.grab().width() > 300
    for w in (window, goals, card):
        w.close()

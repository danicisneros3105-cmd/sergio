"""Coach windows: «hora de practicar», the session and «Mis metas»."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

STYLE = """
QWidget#coach { background: #1C1C1E; }
QLabel { color: #F5F5F7; }
QLabel#muted { color: #8E8E93; }
QTextBrowser, QTextEdit, QListWidget { background: #2C2C2E; color: #F5F5F7; border: none; border-radius: 12px; padding: 10px; font-size: 13px; }
QPushButton { background: #0A84FF; color: white; border: none; border-radius: 10px; padding: 9px 16px; font-size: 13px; }
QPushButton#plain { background: #3A3A3C; }
QPushButton#rec { background: #FF453A; }
QPushButton:disabled { background: #3A3A3C; color: #8E8E93; }
"""


def _font(size: float, bold: bool = False) -> QFont:
    f = QFont(["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"])
    f.setPointSizeF(size)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


class _Relay(QObject):
    done = Signal(object, object)  # (callback, result-or-exception)


_RELAY: list[_Relay] = []


def in_background(job: Callable[[], Any], then: Callable[[Any], None]) -> None:
    """Run *job* off the UI thread; *then* gets its result (or the exception) on it."""
    if not _RELAY:
        relay = _Relay()
        relay.done.connect(lambda cb, value: cb(value))
        _RELAY.append(relay)

    def work() -> None:
        try:
            value = job()
        except Exception as exc:  # noqa: BLE001 — shown to the user
            value = exc
        _RELAY[0].done.emit(then, value)

    threading.Thread(target=work, daemon=True).start()


def lesson_html(lesson: dict[str, Any]) -> str:
    """The lesson as simple HTML for the session window."""
    from html import escape

    parts = [f"<h2>{escape(str(lesson.get('titulo', 'Sesión')))}</h2>"]
    if lesson.get("objetivo"):
        parts.append(f"<p><b>Objetivo:</b> {escape(str(lesson['objetivo']))}</p>")
    if lesson.get("calentamiento"):
        parts.append("<h3>Calentamiento</h3><ul>" + "".join(f"<li>{escape(str(x))}</li>" for x in lesson["calentamiento"]) + "</ul>")
    blocks = lesson.get("contenido") or []
    if blocks:
        parts.append("<h3>Sesión</h3>")
    for b in blocks:
        kind = escape(str(b.get("tipo", "")))
        text = escape(str(b.get("texto", ""))).replace("\n", "<br>")
        answer = b.get("respuesta")
        parts.append(f"<p><span style='color:#0A84FF'>{kind.upper()}</span><br>{text}</p>")
        if answer:
            parts.append(f"<details><summary>Respuesta</summary><p style='color:#8E8E93'>{escape(str(answer))}</p></details>")
    if lesson.get("evaluacion"):
        parts.append("<h3>Comprueba</h3><ol>" + "".join(f"<li>{escape(str(q.get('pregunta', '')))}</li>" for q in lesson["evaluacion"]) + "</ol>")
    if lesson.get("medir"):
        parts.append("<p><b>Al terminar anota:</b> " + escape(", ".join(map(str, lesson["medir"]))) + "</p>")
    if lesson.get("consejo"):
        parts.append(f"<p><i>{escape(str(lesson['consejo']))}</i></p>")
    return "".join(parts)


class PracticeCard(QWidget):
    """«Hora de practicar»: start now, in 30 minutes or skip."""

    def __init__(self, goal: dict[str, Any], session: dict[str, Any], on_start: Callable[[], None],
                 on_later: Callable[[], None], on_skip: Callable[[], None]) -> None:  # fmt: skip
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setObjectName("coach")
        self.setStyleSheet(STYLE + "QWidget#coach { border-radius: 18px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        head = QLabel("HORA DE PRACTICAR")
        head.setObjectName("muted")
        head.setFont(_font(9, True))
        title = QLabel(goal["meta"])
        title.setFont(_font(16, True))
        title.setWordWrap(True)
        what = QLabel(f"Sesión {session['n']} · {session['minutos']} min · {session.get('objetivo', '')}")
        what.setWordWrap(True)
        what.setFont(_font(11))
        row = QHBoxLayout()
        start, later, skip = QPushButton("Empezar"), QPushButton("En 30 min"), QPushButton("Saltar")
        later.setObjectName("plain")
        skip.setObjectName("plain")
        start.clicked.connect(lambda: (self.close(), on_start()))
        later.clicked.connect(lambda: (self.close(), on_later()))
        skip.clicked.connect(lambda: (self.close(), on_skip()))
        for b in (start, later, skip):
            row.addWidget(b)
        for w in (head, title, what):
            lay.addWidget(w)
        lay.addLayout(row)
        self.resize(400, 190)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.right() - 420, geo.bottom() - 210)


class SessionWindow(QWidget):
    """One practice session: the lesson, recording a video, your results."""

    def __init__(
        self,
        goal: dict[str, Any],
        session: dict[str, Any],
        fetch_lesson: Callable[[], dict[str, Any]],
        record: Callable[[], dict[str, Any]] | None,
        assess: Callable[[str], dict[str, Any]],
        on_done: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("coach")
        self.setStyleSheet(STYLE)
        self.setWindowTitle(f"Sergio · {goal['meta']}")
        self.goal, self.session = goal, session
        self._assess, self._record, self._on_done = assess, record, on_done
        self.review: dict[str, Any] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        title = QLabel(goal["meta"])
        title.setFont(_font(18, True))
        self.status = QLabel("Preparando su sesión con lo último que practicó…")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.lesson = QTextBrowser()
        self.lesson.setOpenExternalLinks(True)
        self.results = QTextEdit()
        self.results.setPlaceholderText("Al terminar: cómo le fue, sus respuestas, cuántos intentos salieron bien…")
        self.results.setMaximumHeight(110)
        row = QHBoxLayout()
        self.rec = QPushButton("● Grabar mi práctica")
        self.rec.setObjectName("rec")
        self.rec.setVisible(record is not None and bool(session.get("video")))
        self.rec.clicked.connect(self._start_recording)
        self.done_btn = QPushButton("Terminé")
        self.done_btn.clicked.connect(self._finish)
        row.addWidget(self.rec)
        row.addStretch()
        row.addWidget(self.done_btn)
        for w in (title, self.status, self.lesson, self.results):
            lay.addWidget(w)
        lay.addLayout(row)
        self.resize(640, 720)
        in_background(fetch_lesson, self._show_lesson)

    def _show_lesson(self, lesson: Any) -> None:
        if isinstance(lesson, Exception):
            steps = "".join(f"<li>{s}</li>" for s in self.session.get("pasos") or [])
            self.lesson.setHtml(f"<h2>{self.session.get('objetivo', '')}</h2><ul>{steps}</ul>")
            self.status.setText("Sin conexión con el coach: sigue los pasos del plan.")
            return
        self.lesson.setHtml(lesson_html(lesson))
        self.status.setText(f"Sesión {self.session['n']} · {self.session['minutos']} min")

    def _start_recording(self) -> None:
        if self._record is None:
            return
        self.rec.setEnabled(False)
        self.status.setText("Grabando… haga la práctica frente a la cámara. Luego la reviso fotograma a fotograma.")
        in_background(self._record, self._reviewed)

    def _reviewed(self, review: Any) -> None:
        self.rec.setEnabled(True)
        if isinstance(review, Exception):
            self.status.setText(f"No pude revisar el video: {review}")
            return
        self.review = review
        good = sum(1 for m in review.get("marcas", []) if m.get("bien"))
        bad = len(review.get("marcas", [])) - good
        fix = (review.get("corregir") or [""])[0]
        self.status.setText(f"Video revisado: {good} aciertos (verde), {bad} errores (rojo). {fix}")

    def _finish(self) -> None:
        text = self.results.toPlainText().strip()
        if self.review:
            text += "\nRevisión del video: " + str(self.review.get("resumen", "")) + " Corregir: " + "; ".join(self.review.get("corregir", []))
        if not text:
            self.status.setText("Cuénteme en una frase cómo le fue, así ajusto la próxima sesión.")
            return
        self.done_btn.setEnabled(False)
        self.status.setText("Evaluando…")
        in_background(lambda: self._assess(text), self._assessed)

    def _assessed(self, result: Any) -> None:
        if isinstance(result, Exception):
            result = {"feedback": "Sesión guardada (sin evaluación: el coach no respondió)."}
        if self.review.get("metricas"):
            result.setdefault("metricas", {}).update(self.review["metricas"])
        self._on_done(result)
        self.status.setText(str(result.get("feedback", "")))
        self.done_btn.setText("Cerrar")
        self.done_btn.setEnabled(True)
        self.done_btn.clicked.disconnect()
        self.done_btn.clicked.connect(self.close)


class CoachWindow(QWidget):
    """«Mis metas»: what you are learning, progress, next session, the plan."""

    def __init__(self, coach: Any, start_now: Callable[[str], None]) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("coach")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Sergio · Mis metas")
        self.coach, self.start_now = coach, start_now
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        title = QLabel("Mis metas")
        title.setFont(_font(20, True))
        hint = QLabel("Diga «estoy aprendiendo…» o «tengo examen de…» y le armo un plan investigado.")
        hint.setObjectName("muted")
        self.goals = QListWidget()
        self.goals.currentRowChanged.connect(self._show)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        row = QHBoxLayout()
        practice = QPushButton("Practicar ahora")
        practice.clicked.connect(self._practice)
        stop = QPushButton("Dejar esta meta")
        stop.setObjectName("plain")
        stop.clicked.connect(self._stop)
        row.addWidget(practice)
        row.addWidget(stop)
        row.addStretch()
        for w in (title, hint, self.goals, self.detail):
            lay.addWidget(w)
        lay.addLayout(row)
        self.resize(640, 680)
        self.refresh()

    def _active(self) -> list[dict[str, Any]]:
        return [g for g in self.coach.goals if g.get("activo", True)]

    def refresh(self) -> None:
        self.goals.clear()
        for g in self._active():
            p = self.coach.progress(g)
            self.goals.addItem(f"{g['meta']}  ·  {p['hechas']}/{p['total']} sesiones")
        if self.goals.count():
            self.goals.setCurrentRow(0)
        else:
            self.detail.setHtml("<p>Aún no hay metas.</p>")

    def _show(self, row: int) -> None:
        from html import escape

        active = self._active()
        if not 0 <= row < len(active):
            return
        g = active[row]
        plan, p = g.get("plan") or {}, self.coach.progress(g)
        nxt = self.coach.next_session(g)
        html = [f"<h2>{escape(str(plan.get('titulo') or g['meta']))}</h2>", f"<p>{escape(str(plan.get('resumen', '')))}</p>"]
        if nxt:
            html.append(f"<p><b>Próxima sesión:</b> {datetime.fromtimestamp(nxt['due']).strftime('%d/%m %H:%M')} · {escape(nxt['objetivo'])}</p>")
        if p["nivel"]:
            html.append(f"<p><b>Nivel:</b> {escape(p['nivel'])}</p>")
        for name, values in p["series"].items():
            html.append(f"<p>{escape(name)}: {' → '.join(f'{v:g}' for v in values[-6:])}</p>")
        if p["errores"]:
            html.append("<p><b>Errores frecuentes:</b> " + escape(", ".join(f"{k} ({n})" for k, n in p["errores"])) + "</p>")
        if plan.get("investigacion"):
            html.append("<h3>Lo que investigué</h3><ul>" + "".join(f"<li>{escape(str(x))}</li>" for x in plan["investigacion"][:8]) + "</ul>")
        if plan.get("fuentes"):
            html.append("<h3>Fuentes</h3><ul>" + "".join(
                f"<li><a href='{escape(s.get('url', ''))}' style='color:#0A84FF'>{escape(s.get('titulo') or s.get('url', ''))}</a></li>"
                for s in plan["fuentes"][:10]
            ) + "</ul>")  # fmt: skip
        self.detail.setHtml("".join(html))

    def _selected(self) -> dict[str, Any] | None:
        active = self._active()
        row = self.goals.currentRow()
        return active[row] if 0 <= row < len(active) else None

    def _practice(self) -> None:
        g = self._selected()
        if g is not None:
            self.start_now(g["id"])

    def _stop(self) -> None:
        g = self._selected()
        if g is not None:
            self.coach.stop_goal(g["id"])
            self.refresh()

    def open(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()


__all__ = ["CoachWindow", "PracticeCard", "SessionWindow", "in_background", "lesson_html"]

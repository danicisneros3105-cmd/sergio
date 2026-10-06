"""«Tus resultados»: what the mental gym knows about you, on one screen.

* your profile per skill (0-100, from your recent answers) and its trend,
* the learning curve of each exercise (last sessions, with its weekly slope),
* the control test that is never trained (does it carry over?),
* what the background analysis found (best time of day, streak, plateaus,
  records), and the big picture from the research.

Pure drawing on top of ``brain.profile`` and ``brain.analysis``: open with
«Sergio, muéstrame mis resultados» (Esc or a click on × closes it).
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from sergio_escritorio import brain

BG = QColor(0, 0, 0, 200)
CARD = QColor(28, 28, 30)
PANEL = QColor(44, 44, 46)
LINE = QColor(255, 255, 255, 28)
TEXT = QColor(245, 245, 247)
MUTED = QColor(142, 142, 147)
ACCENT = QColor(10, 132, 255)
GOOD = QColor(48, 209, 88)
BAD = QColor(255, 69, 58)
WARM = QColor(255, 214, 10)


def font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"])
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def sparkline(p: QPainter, rect: QRectF, values: list[float], colour: QColor, lo: float = 0.0, hi: float = 100.0) -> None:
    """A small line chart of *values* inside *rect* (with a soft fill)."""
    if len(values) < 2:
        if values:
            y = rect.bottom() - (values[0] - lo) / max(hi - lo, 1e-6) * rect.height()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colour)
            p.drawEllipse(QPointF(rect.center().x(), y), 3, 3)
        return
    step = rect.width() / (len(values) - 1)
    points = [
        QPointF(rect.left() + i * step, rect.bottom() - (min(max(v, lo), hi) - lo) / max(hi - lo, 1e-6) * rect.height())
        for i, v in enumerate(values)
    ]
    fill = QPainterPath(QPointF(points[0].x(), rect.bottom()))
    for pt in points:
        fill.lineTo(pt)
    fill.lineTo(QPointF(points[-1].x(), rect.bottom()))
    soft = QColor(colour)
    soft.setAlpha(45)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(soft)
    p.drawPath(fill)
    p.setPen(QPen(colour, 2))
    for a, b in zip(points, points[1:]):
        p.drawLine(a, b)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(colour)
    p.drawEllipse(points[-1], 3, 3)


def fitted(p: QPainter, rect: QRectF, text: str, size: float, colour: QColor) -> None:
    """Wrapped *text* in *rect*, shrinking the font until all of it fits."""
    flags = int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap)
    while True:
        p.setFont(font(size))
        used = p.fontMetrics().boundingRect(rect.toRect(), flags, text)
        if used.height() <= rect.height() or size <= 7.5:
            break
        size -= 0.5
    p.setPen(colour)
    p.drawText(rect, flags, text)


def series(history: list[dict[str, Any]], kind: str, last: int = 12) -> list[float]:
    return [brain.score(h) for h in history if h.get("kind") == kind and "accuracy" in h][-last:]


class GymResults(QWidget):
    """The results screen (one window, Apple-style cards)."""

    def __init__(self, history: list[dict[str, Any]], analysis: dict[str, Any] | None = None) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.history = list(history)
        self.analysis = analysis or brain.analysis(self.history)
        self.profile = brain.profile(self.history)

    def open(self) -> None:
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen is not None else None
        if geo is not None:
            self.setGeometry(geo)
        self.show()
        self.raise_()
        self.activateWindow()

    # -- input -----------------------------------------------------------------
    def card(self) -> QRectF:
        w = min(1100.0, self.width() - 60.0)
        h = min(760.0, self.height() - 60.0)
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def close_rect(self) -> QRectF:
        c = self.card()
        return QRectF(c.right() - 52, c.top() + 18, 32, 32)

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        pos = event.position()
        if self.close_rect().contains(pos) or not self.card().contains(pos):
            self.close()

    # -- drawing -----------------------------------------------------------------
    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), BG)
        card = self.card()
        p.setPen(QPen(LINE, 1))
        p.setBrush(CARD)
        p.drawRoundedRect(card, 28, 28)
        self._header(p, card)
        body = card.adjusted(30, 96, -30, -70)
        left = QRectF(body.left(), body.top(), body.width() * 0.36, body.height())
        right = QRectF(left.right() + 20, body.top(), body.width() - left.width() - 20, body.height())
        self._profile(p, QRectF(left.left(), left.top(), left.width(), left.height() * 0.55))
        self._insights(p, QRectF(left.left(), left.top() + left.height() * 0.55 + 14, left.width(), left.height() * 0.45 - 14))
        self._curves(p, QRectF(right.left(), right.top(), right.width(), right.height() * 0.56))
        self._control(p, QRectF(right.left(), right.top() + right.height() * 0.56 + 14, right.width(), right.height() * 0.44 - 14))
        self._footer(p, QRectF(card.left() + 32, body.bottom() + 12, card.width() - 64, card.bottom() - body.bottom() - 22))
        p.end()

    def _panel(self, p: QPainter, rect: QRectF, title: str) -> QRectF:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(PANEL)
        p.drawRoundedRect(rect, 18, 18)
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.setPen(MUTED)
        p.drawText(QRectF(rect.left() + 16, rect.top() + 10, rect.width() - 32, 18), Qt.AlignmentFlag.AlignLeft, title.upper())
        return rect.adjusted(16, 34, -16, -12)

    def _header(self, p: QPainter, card: QRectF) -> None:
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.setPen(MUTED)
        p.drawText(QRectF(card.left() + 32, card.top() + 22, 400, 18), Qt.AlignmentFlag.AlignLeft, "GIMNASIO MENTAL")
        p.setFont(font(24, QFont.Weight.Bold))
        p.setPen(TEXT)
        p.drawText(QRectF(card.left() + 32, card.top() + 42, 500, 36), Qt.AlignmentFlag.AlignLeft, "Tus resultados")
        a = self.analysis
        facts = [f"{a.get('sessions', 0)} sesiones", f"{a.get('days', 0)} días"]
        if a.get("streak"):
            facts.append(f"racha de {a['streak']} días")
        if a.get("best_time"):
            facts.append(f"mejor por la {a['best_time']}")
        p.setFont(font(12))
        p.setPen(MUTED)
        p.drawText(QRectF(card.left() + 300, card.top() + 50, card.width() - 380, 24), Qt.AlignmentFlag.AlignRight, " · ".join(facts))
        close = self.close_rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(PANEL)
        p.drawEllipse(close)
        p.setPen(QPen(TEXT, 2))
        c = close.center()
        p.drawLine(QPointF(c.x() - 6, c.y() - 6), QPointF(c.x() + 6, c.y() + 6))
        p.drawLine(QPointF(c.x() + 6, c.y() - 6), QPointF(c.x() - 6, c.y() + 6))

    def _profile(self, p: QPainter, rect: QRectF) -> None:
        inner = self._panel(p, rect, "Perfil por habilidad (0-100)")
        if not self.profile:
            p.setFont(font(12))
            p.setPen(MUTED)
            p.drawText(inner, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, "Se arma con tus respuestas: haz unos ejercicios.")
            return
        ranked = sorted(self.profile.items(), key=lambda kv: -kv[1]["score"])
        row = min(34.0, inner.height() / max(1, len(ranked)))
        for i, (skill, data) in enumerate(ranked):
            y = inner.top() + i * row
            p.setFont(font(11.5))
            p.setPen(TEXT)
            p.drawText(QRectF(inner.left(), y, inner.width() * 0.45, row), Qt.AlignmentFlag.AlignVCenter, skill.capitalize())
            bar = QRectF(inner.left() + inner.width() * 0.46, y + row / 2 - 4, inner.width() * 0.38, 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(70, 70, 76))
            p.drawRoundedRect(bar, 4, 4)
            score = data["score"]
            p.setBrush(GOOD if score >= 75 else ACCENT if score >= 50 else BAD)
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * score / 100, bar.height()), 4, 4)
            trend = data.get("trend")
            arrow = "" if trend is None else ("▲" if trend >= 3 else "▼" if trend <= -3 else "■")
            p.setPen(GOOD if (trend or 0) >= 3 else BAD if (trend or 0) <= -3 else MUTED)
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.drawText(QRectF(bar.right() + 6, y, inner.right() - bar.right() - 6, row), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{score} {arrow}")

    def _insights(self, p: QPainter, rect: QRectF) -> None:
        inner = self._panel(p, rect, "Lo que encontré")
        lines = list(self.analysis.get("insights") or []) or ["Aún sin conclusiones: necesito más sesiones."]
        p.setFont(font(11))
        y = inner.top()
        for line in lines[:6]:
            box = QRectF(inner.left() + 14, y, inner.width() - 14, inner.bottom() - y)
            used = p.fontMetrics().boundingRect(box.toRect(), int(Qt.TextFlag.TextWordWrap), line)
            if y + used.height() > inner.bottom():
                break
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(WARM)
            p.drawEllipse(QPointF(inner.left() + 4, y + 9), 3, 3)
            p.setPen(TEXT)
            p.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, line)
            y += used.height() + 8

    def _curves(self, p: QPainter, rect: QRectF) -> None:
        inner = self._panel(p, rect, "Curva de aprendizaje (últimas sesiones)")
        curves = self.analysis.get("curves") or {}
        kinds = [k for k in brain.BY_KIND if series(self.history, k)][:9]
        if not kinds:
            p.setFont(font(12))
            p.setPen(MUTED)
            p.drawText(inner, Qt.AlignmentFlag.AlignCenter, "Aquí verás cómo mejoras en cada ejercicio.")
            return
        cols = 3
        rows = (len(kinds) + cols - 1) // cols
        cw, ch = inner.width() / cols, inner.height() / max(rows, 1)
        for i, kind in enumerate(kinds):
            cell = QRectF(inner.left() + (i % cols) * cw + 4, inner.top() + (i // cols) * ch + 2, cw - 8, ch - 6)
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            p.setPen(TEXT)
            title = brain.BY_KIND[kind].title
            p.drawText(QRectF(cell.left(), cell.top(), cell.width(), 16), Qt.AlignmentFlag.AlignLeft,
                       p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(cell.width())))
            info = curves.get(kind)
            if info:
                slope = info["slope"]
                colour = GOOD if info["low"] > 0 else BAD if info["high"] < 0 else MUTED
                p.setFont(font(9.5))
                p.setPen(colour)
                p.drawText(QRectF(cell.left(), cell.top() + 16, cell.width(), 14), Qt.AlignmentFlag.AlignLeft,
                           f"{slope:+.1f} pts/semana · mejor {info['best']}")
            sparkline(p, QRectF(cell.left(), cell.top() + 34, cell.width(), cell.height() - 40), series(self.history, kind), ACCENT)

    def _control(self, p: QPainter, rect: QRectF) -> None:
        inner = self._panel(p, rect, "Prueba de control: velocidad (nunca se entrena)")
        probes = [float(h.get("rate", 0)) for h in self.history if h.get("kind") == "prueba"]
        chart = QRectF(inner.left(), inner.top(), inner.width() * 0.45, inner.height() - 4)
        if probes:
            lo, hi = min(probes) * 0.9, max(probes) * 1.1 + 1e-6
            sparkline(p, chart, probes[-30:], WARM, lo, hi)
        box = QRectF(chart.right() + 16, inner.top(), inner.right() - chart.right() - 16, inner.height())
        fitted(p, box, brain.effectiveness_text(self.history), 11.0, TEXT)

    def _footer(self, p: QPainter, rect: QRectF) -> None:
        fitted(p, rect, brain.BIG_PICTURE, 10.0, MUTED)


def results_sentence(analysis: dict[str, Any]) -> str:
    """The analysis in two spoken sentences."""
    insights = list(analysis.get("insights") or [])
    if not insights:
        return "Aún no tengo resultados del gimnasio."
    return " ".join(insights[:3])


def stamp() -> str:
    return time.strftime("%d/%m/%Y %H:%M")


__all__ = ["GymResults", "fitted", "results_sentence", "series", "sparkline"]

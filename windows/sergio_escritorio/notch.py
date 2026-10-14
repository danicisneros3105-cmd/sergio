"""The notch: a Dynamic-Island-style pill at the top centre of the screen.

Pure black, flush with the top edge, home of Sergio's orb. Compact when idle
(orb + a quiet waveform); while listening the waveform follows your real
voice; while thinking the label shimmers; answers type themselves in. Click
it to open the control center (panel.py). Only the pill takes clicks.

Live Activities (activities.py): a running job rides in the pill with its
progress ring and name; when two run at once the island splits in two like
an iPhone's — the «dúo», a round bubble beside the pill with the second
one's ring (and «+N» for more). Sizes move on real springs (a soft
overshoot, like iOS), and a finished job shows a check before merging back.
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
    QTransform,
)
from PySide6.QtWidgets import QWidget

from sergio_escritorio import estilo
from sergio_escritorio.activities import (
    Activities,
    Activity,
    Fold,
    Pour,
    Spring,
    Vanish,
    lean,
)
from sergio_escritorio.character import PALETTES, STATE_COLORS, draw_character

LABELS = {
    "idle": "Sergio",
    "listening": "Te escucho",
    "thinking": "Pensando",
    "speaking": "Sergio",
    "acting": "Usando tu pantalla",
    "paused": "Control pausado",
}
FONTS = estilo.families()  # the house typeface (Josefin Sans), then system fallbacks

CANVAS_W, CANVAS_H = 620, 160
COMPACT = (132.0, 36.0)
LIVE = (236.0, 36.0)  # compact with a Live Activity in it
BUBBLE = 36.0  # the second island of the «dúo»
GAP = 9.0
MEDIUM = (252.0, 48.0)
EXPANDED_W = 460.0
PAD = 16.0
RADIUS = 22.0
BARS = 22
TYPE_SPEED = 55.0  # characters per second for answers
FACEID = (148.0, 148.0)  # the island while Face ID looks at you
EXPAND_SPRING = (0.48, 0.78)  # response, damping: growing overshoots softly
COLLAPSE_SPRING = (0.38, 0.95)  # shrinking settles without a bounce
POUR = (196.0, 54.0)  # the lake the drop fills, before it settles to size
EDGE_PX = 2  # the cursor this close to the top edge (near the centre) calls it back
EDGE_HALF_W = 170
EDGE_DWELL_S = 0.12


EAR = 6.0  # the concave flare where Apple's notch meets the top edge
SMOOTH = 0.6  # continuous ("squircle") corners, like Apple's, not plain arcs


def corner_radius(height: float) -> float:
    """Pill-round when compact, Apple's larger soft corners when it grows."""
    return min(height / 2, max(RADIUS, height * 0.28))


def notch_path(rect: QRectF) -> QPainterPath:
    """Apple's notch: flush with the top edge, flared into it by two small
    concave ears, with continuous (smoothed) bottom corners."""
    path = QPainterPath()
    r = corner_radius(rect.height())
    e = min(EAR, rect.height() / 3)
    top, bottom, left, right = rect.top(), rect.bottom(), rect.left(), rect.right()
    k = r * (1 - SMOOTH * 0.55)  # control-point inset: smaller = smoother
    path.moveTo(left - e, top)
    path.lineTo(right + e, top)
    path.quadTo(right, top, right, top + e)  # right ear (concave)
    path.lineTo(right, bottom - r)
    path.cubicTo(right, bottom - r + k, right - r + k, bottom, right - r, bottom)
    path.lineTo(left + r, bottom)
    path.cubicTo(left + r - k, bottom, left, bottom - r + k, left, bottom - r)
    path.lineTo(left, top + e)
    path.quadTo(left, top, left - e, top)  # left ear (concave)
    path.closeSubpath()
    return path


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    estilo.load_fonts()
    font = QFont()
    font.setFamilies(FONTS)
    font.setPointSizeF(size)
    font.setWeight(weight)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99)
    return font


def system_reduced_motion() -> bool:
    """Respect Windows' client-area animation preference; portable fallback."""
    import sys

    if sys.platform != "win32":
        return False
    import ctypes

    enabled = ctypes.c_int(1)
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(ok) and not bool(enabled.value)
    except (AttributeError, OSError):
        return False


def liquid_bridge(rect: QRectF, bubble: QRectF | None, angle: float) -> QPainterPath:
    """A bounded vector meniscus; the hit mask uses the same background.

    Like the supplied SVG gooey effect, it joins liquid silhouettes. Qt
    avoids a full-canvas blur pass and leaves the foreground untouched.
    """
    path = QPainterPath()
    if bubble is None or not 90 < angle < 179:
        return path
    strength = math.sin(math.pi * (angle - 90) / 90)
    left, right = rect.right() - 1, bubble.left() + 2
    y = min(rect.height(), bubble.height()) / 2
    half = 8 * strength
    path.moveTo(left, y - half)
    path.cubicTo(left + 3, y, right - 3, y, right, y - half)
    path.lineTo(right, y + half)
    path.cubicTo(right - 3, y, left + 3, y, left, y + half)
    path.closeSubpath()
    return path


class Notch(QWidget):
    def __init__(
        self,
        *,
        on_click: Callable[[], None] | None = None,
        fullscreen_app: Callable[[], bool] | None = None,
        reduced_motion: bool | None = None,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clic para abrir el centro de control de Sergio")
        self.resize(CANVAS_W, CANVAS_H)
        self.on_click = on_click
        self.reduced_motion = system_reduced_motion() if reduced_motion is None else reduced_motion
        # Hide while a video or game is fullscreen (unless Sergio is active).
        self.fullscreen_app = fullscreen_app or (lambda: False)
        self._mask_rect = None
        self._hidden_for_fullscreen = False
        self._last_fs_check = 0.0
        self.state = "idle"
        self.name = "Sergio"  # personalisation can rename him
        self.caption = ""
        self._caption_until = 0.0
        self._caption_at = 0.0
        self.level = 0.0
        self.call_since: float | None = None  # in a call with Sergio
        self.screen_sharing = False
        self.reduce_motion = False
        self._levels: deque[float] = deque([0.0] * BARS, maxlen=BARS)
        self._t0 = time.monotonic()
        self._w, self._h = COMPACT
        self._sw, self._sh = Spring(COMPACT[0]), Spring(COMPACT[1])
        # Apple's island: the old content fades and shrinks away while the
        # shape morphs, the new one fades in once the shape is nearly there.
        self._content = Spring(1.0, response=0.24, damping=1.0)
        # A touch squeezes it a little and it springs back (like a tap on iOS).
        self._press = Spring(1.0, response=0.28, damping=0.6)
        self._pressed = False
        self._faceid = None  # faceid_anim.FaceIDGlyph while approving with the face
        self._duo = Fold()  # the iPhone Duo fold: 0° merged .. 180° split
        # «Sergio, activa multitasking» splits the island; off folds it back.
        self.multitasking = False
        self._vanish = Vanish()  # «esconde el notch»: black hole, then up
        self._snap: QPixmap | None = None  # the island as it was, to swallow
        # Hidden, the cursor at the top edge calls it back as a drop of liquid.
        self._pour = Pour()
        self.on_shown: Callable[[], None] | None = None
        self._edge_since: float | None = None
        self._edge = QTimer(self)
        self._edge.timeout.connect(self._watch_edge)
        self._last_tick = time.monotonic()
        self.activities: Activities | None = None
        self._live: list[Activity] = []
        self._last_activity_poll = -math.inf
        self._small = _font(8.2, QFont.Weight.DemiBold)
        self._title = _font(9.0, QFont.Weight.DemiBold)
        self._body = _font(10.5)
        self._place()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _wake(self) -> None:
        if not self.hidden and self.isVisible():
            interval = 33 if self.reduced_motion else 16
            if not self._timer.isActive():
                self._last_tick = time.monotonic()
                self._timer.start(interval)
            elif self._timer.interval() != interval:
                self._timer.setInterval(interval)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "_timer"):
            self._wake()

    def hideEvent(self, event) -> None:
        if hasattr(self, "_timer"):
            self._timer.stop()
        super().hideEvent(event)

    # -- API ------------------------------------------------------------------
    def faceid(self, phase: str) -> None:
        """Face ID in the island, as on the iPhone: it grows into a rounded
        square with the glyph ('scan'), then 'success' or 'fail', then back."""
        from sergio_escritorio.faceid_anim import FaceIDGlyph

        if phase == "idle":
            self._faceid = None
        else:
            if self._faceid is None:
                self._faceid = FaceIDGlyph()
            self._faceid.start(phase)
        self._wake()

    def set_state(self, state: str) -> None:
        self.state = state if state in STATE_COLORS else "idle"
        self._wake()

    def set_level(self, level: float) -> None:
        """Live microphone volume 0..1 (called ~30 times a second)."""
        self.level = max(0.0, min(1.0, level))

    def set_call(self, active: bool) -> None:
        """A green call timer, like the Dynamic Island during a phone call."""
        self.call_since = time.monotonic() if active else None
        if not active:
            self.screen_sharing = False

    def set_screen_sharing(self, active: bool) -> None:
        self.screen_sharing = bool(active)
        self.setToolTip("Pantalla compartida con Gemini · diga «deja de ver mi pantalla»"
                        if active else "Clic para abrir el centro de control de Sergio")

    def set_reduce_motion(self, enabled: bool) -> None:
        self.reduce_motion = bool(enabled)

    def call_time(self) -> str:
        if self.call_since is None:
            return ""
        seconds = int(time.monotonic() - self.call_since)
        return f"{seconds // 60}:{seconds % 60:02d}"

    def say(self, text: str, seconds: float = 0.0) -> None:
        text = " ".join(text.split())
        # A live call sends the sentence as it grows: keep typing, no restart.
        growing = bool(self.caption) and text.startswith(self.caption)
        self.caption = text
        if not growing:
            self._caption_at = time.monotonic()
        self._caption_until = time.monotonic() + (
            seconds or min(18.0, 4.0 + len(self.caption) / 15)
        )

    def set_multitasking(self, on: bool) -> None:
        """Split the island in two (the iPhone Duo fold) or fold it back."""
        self.multitasking = bool(on)
        self._wake()

    @property
    def hidden(self) -> bool:
        return self._vanish.target >= 1.0

    def hide_notch(self, instant: bool = False) -> None:
        """Collapse into a small black hole, then rise off the screen."""
        if self._vanish.target >= 1.0:
            return
        self._pour.t = 1.0
        self._snap = self._snapshot()
        self._vanish.hide()
        self._edge_since = None
        self._edge.start(50)  # 20 checks a second of where the cursor is: nothing else runs
        if instant or (self.reduced_motion or self.reduce_motion):
            self._vanish.t = 1.0
            self._timer.stop()
            self.hide()
        else:
            self._timer.start(16)

    def show_notch(self) -> None:
        """The same film backwards: it drops in and opens up."""
        if self._vanish.target <= 0.0:
            return
        self._edge.stop()
        self._snap = self._snapshot()
        self._vanish.show()
        if (self.reduced_motion or self.reduce_motion):
            self._vanish.t = 0.0
        self._wake()
        if not self.isVisible():
            self.show()

    def pour_in(self, cursor_x: float) -> None:
        """Back as a drop of liquid where the cursor touched the edge."""
        if not self.hidden:
            return
        if self.reduce_motion:
            self.show_notch()
            return
        self._edge.stop()
        self._vanish.t = self._vanish.target = 0.0
        if self.reduced_motion:
            self._pour.t = 1.0
            self._last_activity_poll = -math.inf
            self.show()
            self._wake()
            if self.on_shown is not None:
                self.on_shown()
            return
        w, h = POUR
        left = (CANVAS_W - w) / 2
        self._pour.start(cursor_x - self.x(), left, left + w, h)
        self._w, self._h = POUR
        for spring, value in ((self._sw, w), (self._sh, h)):
            spring.value = spring.target = value
            spring.velocity = 0.0
        self._last_tick = time.monotonic()
        self._wake()
        if not self.isVisible():
            self.show()
        if self.on_shown is not None:
            self.on_shown()

    def _watch_edge(self) -> None:
        if not self.hidden:
            self._edge.stop()
            return
        if not self._vanish.hidden:  # still rising away
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.geometry()
        pos = QCursor.pos()
        centre = geo.x() + geo.width() / 2
        at_edge = pos.y() <= geo.top() + EDGE_PX and abs(pos.x() - centre) <= EDGE_HALF_W
        now = time.monotonic()
        if not at_edge:
            self._edge_since = None
        elif self._edge_since is None:
            self._edge_since = now
        elif now - self._edge_since >= EDGE_DWELL_S:
            self._edge_since = None
            self.pour_in(pos.x())

    def _snapshot(self) -> QPixmap:
        image = QPixmap(CANVAS_W, CANVAS_H)
        image.fill(Qt.GlobalColor.transparent)
        q = QPainter(image)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_normal(q)
        q.end()
        return image

    # -- layout -----------------------------------------------------------------
    def _place(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.geometry()
        self.move(geo.x() + (geo.width() - CANVAS_W) // 2, geo.y())

    def expanded(self) -> bool:
        return bool(self.caption) or self.state not in ("idle",)

    def lines(self) -> list[str]:
        if not self.caption:
            return []
        metrics = QFontMetricsF(self._body)
        width = EXPANDED_W - 2 * PAD - 58
        out: list[str] = []
        current = ""
        for word in self.caption.split():
            trial = f"{current} {word}".strip()
            if metrics.horizontalAdvance(trial) <= width:
                current = trial
            else:
                if current:
                    out.append(current)
                current = word
        if current:
            out.append(current)
        if len(out) > 3:
            out = out[:3]
            out[2] = metrics.elidedText(
                out[2] + " …", Qt.TextElideMode.ElideRight, width
            )
        return out

    def target_size(self) -> tuple[float, float]:
        if self._faceid is not None:
            return FACEID
        if not self.expanded():
            return LIVE if self._live and self.call_since is None else COMPACT
        lines = self.lines()
        if not lines:
            return MEDIUM  # just the state, e.g. "Te escucho" + live waveform
        metrics = QFontMetricsF(self._body)
        return EXPANDED_W, max(62.0, 34.0 + len(lines) * metrics.lineSpacing() + PAD)

    def pill(self) -> QRectF:
        squeeze = self._press.value if hasattr(self, "_press") else 1.0
        w, h = self._w * squeeze, self._h * (1 - (1 - squeeze) * 0.6)
        return QRectF((CANVAS_W - w) / 2, 0, w, h)

    def hinge(self) -> float:
        """The x of the fold's hinge, just right of the pill."""
        return self.pill().right() + GAP

    def bubble(self) -> QRectF | None:
        """The second island (dúo): where the folding half is right now."""
        if self._duo.angle <= 0.5:
            return None
        hinge, far = self.hinge(), self.hinge() + BUBBLE * self._duo.reach()
        left, right = min(hinge, far), max(hinge, far)
        return QRectF(left, 0, max(1.0, right - left), BUBBLE)

    # -- animation --------------------------------------------------------------
    def _tick(self) -> None:
        if self.caption and time.monotonic() > self._caption_until:
            self.caption = ""
        # Waveform history: real voice while listening, gentle idle shimmer.
        t = time.monotonic() - self._t0
        if self.state == "listening":
            sample = self.level
        elif self.state == "speaking":
            sample = 0.25 + 0.5 * abs(math.sin(t * 7.3))
        else:
            # Idle: the small wave still follows the microphone, so you can see
            # at a glance that Sergio hears you.
            sample = max(0.06, self.level * 0.6)
        self._levels.append(self._levels[-1] * 0.35 + sample * 0.65)
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        if now - self._last_activity_poll >= 0.25:
            self._live = self.activities.snapshot() if self.activities is not None else []
            self._last_activity_poll = now
        if self._pour.active:
            cursor = self.mapFromGlobal(QCursor.pos())
            self._pour.step(dt, float(cursor.x()))
            left, right, bottom = self._pour.basin
            region = QRegion(QRectF(left - 2, 0, right - left + 4, bottom + 4).toAlignedRect())
            if region != self._mask_rect:
                self._mask_rect = region
                self.setMask(region)
            self.update()
            return
        if self._faceid is not None and self._faceid.finished():
            self._faceid = None
        tw, th = self.target_size()
        # Real springs toward the target size: growing overshoots softly,
        # shrinking settles cleanly (Apple's island does both).
        growing = tw * th > self._sw.value * self._sh.value + 1
        response, damping = EXPAND_SPRING if growing else COLLAPSE_SPRING
        for spring in (self._sw, self._sh):
            spring.response, spring.damping = response, damping
        self._sw.target, self._sh.target = tw, th
        near = abs(self._sw.value - tw) < 0.14 * tw and abs(self._sh.value - th) < 0.18 * th
        self._content.target = 1.0 if near else 0.0
        self._content.step(dt)
        self._press.target = 0.95 if self._pressed else 1.0
        self._press.step(dt)
        if self.reduced_motion:
            for spring in (self._sw, self._sh):
                spring.value, spring.velocity = spring.target, 0.0
            self._duo.snap(self.multitasking)
        self._w, self._h = self._sw.step(dt), self._sh.step(dt)
        self._duo.open(self.multitasking)
        if self.reduce_motion:
            self._w, self._h = tw, th
            for spring in (self._sw, self._sh):
                spring.value, spring.velocity = spring.target, 0.0
            self._duo.settle()
        else:
            self._duo.step(dt)
        self._vanish.step(dt)
        if self._vanish.hidden:
            self._timer.stop()
            if self.isVisible():
                self.hide()  # gone: nothing left to click
            return
        if self._vanish.active:
            # The disc spreads past the pill while it collapses.
            r = self.pill()
            region = QRegion(
                r.adjusted(-r.width() * 0.25, 0, r.width() * 0.25, 24).toAlignedRect()
            )
            if region != self._mask_rect:
                self._mask_rect = region
                self.setMask(region)
            self.update()
            return
        rect = self.pill()
        region = QRegion(notch_path(rect).toFillPolygon().toPolygon())
        bubble = self.bubble()
        if bubble is not None:
            region = region.united(
                QRegion(bubble.toAlignedRect(), QRegion.RegionType.Ellipse)
            )
            bridge = liquid_bridge(rect, bubble, self._duo.angle)
            if not self.reduced_motion and not bridge.isEmpty():
                region = region.united(QRegion(bridge.toFillPolygon().toPolygon()))
        if region != self._mask_rect:
            self._mask_rect = region
            self.setMask(region)  # clicks outside the islands go through
        self._respect_fullscreen()
        moving = not all((self._duo.settled(), self._sw.settled(), self._sh.settled()))
        interval = 250 if self._hidden_for_fullscreen else (16 if moving and not self.reduced_motion else 33)
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)
        if self._hidden_for_fullscreen:
            return
        self.update()
        # Keep smooth transitions at 60 Hz; quiet, settled pills use 20 Hz.
        moving = (not (self._sw.settled() and self._sh.settled() and self._content.settled()
                       and self._press.settled())
                  or self._duo.angle != self._duo.target or self._vanish.active
                  or self._faceid is not None)
        self._timer.setInterval(16 if moving or self.state != "idle" else 50)

    def _respect_fullscreen(self) -> None:
        now = time.monotonic()
        if now - self._last_fs_check < 1.0:
            return
        self._last_fs_check = now
        try:
            covered = self.fullscreen_app() and not self.expanded()
        except Exception:  # noqa: BLE001 — never let a check break the notch
            covered = False
        if covered and not self._hidden_for_fullscreen:
            self._hidden_for_fullscreen = True
            self.setWindowOpacity(0.0)
        elif not covered and self._hidden_for_fullscreen:
            self._hidden_for_fullscreen = False
            self.setWindowOpacity(1.0)

    def mousePressEvent(self, event: object) -> None:  # noqa: N802 (Qt API)
        self._pressed = True  # squeezes while held (spring), opens on release
        self._wake()

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802 (Qt API)
        was = self._pressed
        self._pressed = False
        self._wake()
        if was and self.on_click is not None:
            self.on_click()

    # -- drawing ----------------------------------------------------------------
    def paintEvent(self, _event: object) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._pour.active:
            self._paint_pour(p)
        elif self._vanish.active:
            self._paint_vanish(p)
        else:
            self._paint_normal(p)

    def _paint_pour(self, p: QPainter) -> None:
        """A drop seeps from the edge, leans to the cursor, falls slowly and
        fills the island's shape like a lake; then the island appears."""
        pour = self._pour
        left, right, bottom = pour.basin
        basin = notch_path(QRectF(left, 0, right - left, bottom))
        c = self.mapFromGlobal(QCursor.pos())
        cursor = (float(c.x()), float(c.y()))
        phase = pour.phase()
        r = pour.RADIUS
        ink = QLinearGradient(0, 0, 0, bottom)
        ink.setColorAt(0.0, QColor(30, 30, 28))
        ink.setColorAt(1.0, QColor(0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        gloss = QColor(255, 255, 255, 70)

        def draw_drop(cx: float, cy: float, stretch: float, attached: float = 0.0) -> None:
            angle, pull, shift = lean(cx, cy, cursor)
            p.save()
            p.translate(cx, cy)
            if shift:
                p.translate(math.cos(math.radians(angle)) * shift, math.sin(math.radians(angle)) * shift)
                p.rotate((angle - 90.0) * min(1.0, pull * 3.0) * 0.35)
            p.scale(1.0 - pull * 0.25, 1.0 + pull)
            tail = r * (1.0 + stretch * 1.6)
            drop = QPainterPath(QPointF(0, -tail))
            drop.cubicTo(r * 0.35, -tail * 0.55, r * 1.05, -r * 0.35, r, r * 0.15)
            drop.cubicTo(r * 0.95, r * 0.85, r * 0.45, r * 1.02, 0, r * 1.02)
            drop.cubicTo(-r * 0.45, r * 1.02, -r * 0.95, r * 0.85, -r, r * 0.15)
            drop.cubicTo(-r * 1.05, -r * 0.35, -r * 0.35, -tail * 0.55, 0, -tail)
            p.setBrush(QColor(4, 4, 4))
            p.drawPath(drop)
            p.setPen(QPen(gloss, 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(-r * 0.62, -r * 0.5, r * 0.9, r * 0.9), 110 * 16, 70 * 16)
            p.restore()
            p.setPen(Qt.PenStyle.NoPen)

        if phase == "form":
            depth = pour.pendant()
            x = pour.x
            angle, pull, shift = lean(x, depth * 0.6, cursor)
            tip_x = x + math.cos(math.radians(angle)) * shift * 1.5
            tip_y = depth + max(0.0, math.sin(math.radians(angle))) * shift
            # A pendant drop: a meniscus at the edge, a neck, a round bulb.
            bulb = r * (0.55 + 0.45 * min(1.0, depth / (r * 2.6)))
            cy = max(bulb * 0.6, tip_y - bulb)
            neck = max(1.6, bulb * (0.95 - 0.55 * min(1.0, depth / (r * 2.6))))
            cx = x + (tip_x - x) * 0.8
            bead = QPainterPath(QPointF(x - r * 2.4, 0))
            bead.cubicTo(x - r * 1.1, 0, x - neck, cy * 0.35, cx - bulb * 0.92, cy)
            bead.cubicTo(cx - bulb * 0.95, cy + bulb * 0.75, cx - bulb * 0.5, cy + bulb, cx, cy + bulb)
            bead.cubicTo(cx + bulb * 0.5, cy + bulb, cx + bulb * 0.95, cy + bulb * 0.75, cx + bulb * 0.92, cy)
            bead.cubicTo(x + neck, cy * 0.35, x + r * 1.1, 0, x + r * 2.4, 0)
            bead.closeSubpath()
            p.setBrush(QColor(4, 4, 4))
            p.drawPath(bead)
            if depth > r:
                p.setPen(QPen(gloss, 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawArc(QRectF(cx - bulb * 0.7, cy - bulb * 0.55, bulb * 1.0, bulb * 1.0), 110 * 16, 70 * 16)
                p.setPen(Qt.PenStyle.NoPen)
            return
        if phase == "fall":
            y, radius, stretch = pour.drop()
            k = (pour.t - pour.FORM) / (pour.FALL - pour.FORM)
            if k < 0.3:  # the thread it hung from thins and pulls back up
                left_k = 1.0 - k / 0.3
                top_of_drop = y - radius * (1.0 + stretch * 1.6)
                p.setPen(QPen(QColor(4, 4, 4), max(0.4, 2.2 * left_k), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(pour.x, 0), QPointF(pour.x, top_of_drop * left_k))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(4, 4, 4))
                p.drawEllipse(QPointF(pour.x, 0), r * 1.2 * left_k, r * 0.7 * left_k)
            draw_drop(pour.x, y, stretch)
            return
        # The lake: a puddle that spreads to the walls, then rises to the brim.
        floor, top = bottom - 5.0, -2.0
        level = pour.level()
        base = floor + (top - floor) * level
        spread = pour.spread()
        width = 2 * r + (right - left - 2 * r) * spread
        lo = max(left, min(pour.land_x - width / 2, right - width))
        hi = min(right, lo + width)
        mid, half = (lo + hi) / 2, max(1.0, (hi - lo) / 2)
        hump = r * 1.1 * (1.0 - spread) * (1.0 - level)  # the splash, flattening
        points: list[QPointF] = []
        x = lo
        while True:
            u = (x - mid) / half
            dome = hump * max(0.0, 1.0 - u * u)
            edge = (1.0 - spread) * 5.0 * (abs(u) ** 6)  # rounded puddle rim
            y = base - dome + edge + pour.wave(x)
            dx, dy = x - cursor[0], y - cursor[1]
            if abs(dy) < 18.0:  # the cursor dips the surface like a fingertip
                y += 2.6 * math.exp(-(dx / 9.0) ** 2) * (1.0 - abs(dy) / 18.0)
            points.append(QPointF(x, min(y, bottom + 1.0)))
            if x >= hi:
                break
            x = min(hi, x + 2.0)
        lake = QPainterPath(QPointF(lo, bottom + 2.0))
        for pt in points:
            lake.lineTo(pt)
        lake.lineTo(QPointF(hi, bottom + 2.0))
        lake.closeSubpath()
        p.save()
        p.setClipPath(basin)
        p.setBrush(ink)
        p.drawPath(lake)
        if pour.fade() < 1.0:
            p.setOpacity(1.0 - pour.fade())
            p.setPen(QPen(QColor(255, 255, 255, 46), 1.0))
            p.drawPolyline(points)
            p.setOpacity(1.0)
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(4, 4, 4))
        for sx, sy, sr in pour.splash():
            p.drawEllipse(QPointF(sx, sy), sr, sr)
        if pour.fade() > 0.0:
            p.setOpacity(pour.fade())
            self._paint_normal(p)
            p.setOpacity(1.0)

    def _paint_vanish(self, p: QPainter) -> None:
        """The island falls into a black hole, then the ball rises away.

        A snapshot of the island twists and shrinks into a sphere; behind and
        in front of it an accretion disc, tilted for depth, glows and spins;
        a thin photon ring hugs the ball; a few sparks spiral in."""
        v = self._vanish
        t = time.monotonic() - self._t0
        c, rise, glow = v.collapse(), v.rise(), v.glow()
        rect = self.pill()
        ball = 12.0 * (1.0 - 0.35 * rise)
        width = rect.width() + (ball - rect.width()) * c
        height = rect.height() + (ball - rect.height()) * c
        cx = rect.center().x()
        cy = rect.height() / 2 + (-(rect.height() / 2) - 3 * ball) * rise
        body = QRectF(cx - width / 2, cy - height / 2, width, height)
        # The disc hugs the hole: wide while the island is wide, tight
        # around the ball at the end.
        disc_w = (ball * 4.6 + (width - ball) * 0.55) * (1.0 - 0.5 * rise)
        disc = QRectF(-disc_w / 2, -disc_w * 0.11, disc_w, disc_w * 0.22)

        def draw_disc(front: bool) -> None:
            if glow <= 0.01:
                return
            p.save()
            p.translate(cx, cy)
            p.rotate(-11.0)  # tilted: we look at it from a little above
            p.setClipRect(QRectF(-disc_w, 0 if front else -disc_w, 2 * disc_w, disc_w))
            ring = QConicalGradient(QPointF(0, 0), (t * 260.0) % 360.0)
            hot = QColor(255, 236, 205, int(235 * glow))
            warm = QColor(255, 150, 70, int(170 * glow))
            cool = QColor(255, 120, 60, 0)
            ring.setColorAt(0.0, hot)
            ring.setColorAt(0.18, warm)
            ring.setColorAt(0.5, cool)
            ring.setColorAt(0.82, warm)
            ring.setColorAt(1.0, hot)
            p.setPen(QPen(ring, 1.6 + 2.6 * glow, Qt.PenStyle.SolidLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(disc)
            p.setPen(QPen(QColor(255, 210, 160, int(90 * glow)), 1.0))
            p.drawEllipse(disc.adjusted(disc_w * 0.12, 1.5, -disc_w * 0.12, -1.5))
            p.restore()

        draw_disc(front=False)
        # Sparks spiralling in, on the disc's plane.
        if glow > 0.05:
            p.save()
            p.translate(cx, cy)
            p.rotate(-11.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 225, 190, int(200 * glow)))
            for i in range(9):
                a = i * 0.698 + t * 3.0 + c * 9.0
                radius = (1.0 - c) * rect.width() * 0.55 + width / 2 + 4 + (i % 3) * 3
                spark = QPointF(math.cos(a) * radius, math.sin(a) * radius * 0.22)
                p.drawEllipse(spark, 1.3, 1.3)
            p.restore()
        # The island itself, swallowed: black body, its picture twisting in.
        path = QPainterPath()
        path.addRoundedRect(body, height / 2, height / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawPath(path)
        if self._snap is not None and c < 0.9:
            p.save()
            p.setClipPath(path)
            p.setOpacity(max(0.0, 1.0 - c * 1.25))
            p.translate(cx, cy)
            p.rotate(c * 210.0)
            p.scale(width / rect.width(), height / rect.height())
            p.translate(-cx, -rect.height() / 2)
            p.drawPixmap(0, 0, self._snap)
            p.restore()
        # Event horizon, once it is a ball: a warm halo bent around it
        # (lensing) and the thin bright photon ring.
        if c > 0.7:
            halo = QRadialGradient(QPointF(cx, cy), ball * 1.6)
            halo.setColorAt(0.55, QColor(255, 190, 120, int(120 * glow)))
            halo.setColorAt(1.0, QColor(255, 160, 90, 0))
            p.setBrush(halo)
            p.drawEllipse(QPointF(cx, cy), ball * 1.6, ball * 1.6)
            p.setBrush(QColor(0, 0, 0))
            p.drawEllipse(QPointF(cx, cy), width / 2, height / 2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 240, 220, int(230 * glow)), 1.1))
            p.drawEllipse(QPointF(cx, cy), width / 2 + 1.4, height / 2 + 1.4)
        draw_disc(front=True)

    def _paint_normal(self, p: QPainter) -> None:
        t = time.monotonic() - self._t0
        rect = self.pill()

        # Flat top (flush with the screen edge), soft round bottom: a notch.
        path = notch_path(rect)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawPath(path)
        if not self.reduced_motion:
            p.drawPath(liquid_bridge(rect, self.bubble(), self._duo.angle))

        # Content rides the morph: faded and slightly shrunk while the shape
        # moves, back to full once it is nearly there (Apple's crossfade).
        alpha = 1.0 if self.reduced_motion else max(0.0, min(1.0, self._content.value))
        p.setOpacity(alpha)
        if alpha < 1.0:
            k = 0.9 + 0.1 * alpha
            c = rect.center()
            p.translate(c)
            p.scale(k, k)
            p.translate(-c)
        if self._faceid is not None:
            side = min(rect.width(), rect.height()) - 2 * PAD
            box = QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
            self._faceid.paint(p, box)
            return

        compact = rect.height() < 42
        size = 10.5 if compact else 15.0
        centre = QPointF(
            rect.left() + PAD + size,
            rect.top()
            + (rect.height() / 2 if compact else min(31.0, rect.height() / 2)),
        )
        draw_character(
            p,
            centre,
            size,
            self.state,
            t,
            self._look(centre),
            level=self.level if self.state == "listening" else 0.0,
        )

        if self.bubble() is not None:
            # The second half shows the next activity, or an empty slot ready
            # for one.
            second = self._live[1] if len(self._live) >= 2 else None
            self._draw_fold(p, second, max(0, len(self._live) - 2), t)
        if compact:
            if self.call_since is not None:
                self._draw_call(p, rect)
            elif self._live:
                self._draw_live(p, rect, self._live[0], t)
            else:
                self._draw_wave(
                    p,
                    QRectF(
                        rect.right() - PAD - 44, rect.top() + 9, 44, rect.height() - 18
                    ),
                    9,
                )
            return

        text_x = centre.x() + size + 14
        label = LABELS.get(self.state, self.name)
        if label == "Sergio":
            label = self.name
        if self.call_since is not None and self.state in ("idle", "listening"):
            label = f"En llamada · {self.call_time()}"
            if self.screen_sharing:
                label = "Pantalla en vivo"
        has_text = bool(self.lines())
        title_y = rect.top() + (24 if has_text else rect.height() / 2 + 4.5)
        p.setFont(self._title)
        if self.state == "thinking":
            self._shimmer(p, QPointF(text_x, title_y), label + "…", t)
        else:
            colour = QColor(PALETTES.get(self.state, PALETTES["idle"])[2])
            p.setPen(colour if self.state != "idle" else QColor(150, 150, 158))
            p.drawText(QPointF(text_x, title_y), label)
        if self.state in ("listening", "speaking") or not has_text:
            wave_w = 64.0
            self._draw_wave(
                p,
                QRectF(rect.right() - PAD - wave_w, rect.top() + 12, wave_w, 22),
                14,
            )
        if not has_text:
            return
        p.setFont(self._body)
        p.setPen(QColor(244, 244, 246))
        metrics = QFontMetricsF(self._body)
        shown = int((time.monotonic() - self._caption_at) * TYPE_SPEED)
        y = rect.top() + 30
        for line in self.lines():
            if shown <= 0:
                break
            visible = line[:shown]
            shown -= len(line) + 1
            y += metrics.ascent()
            if y > rect.bottom() - 6:
                break
            p.drawText(QPointF(text_x, y), visible)
            y += metrics.descent() + metrics.leading()

    # -- Live Activities ----------------------------------------------------------
    def _ring(
        self, p: QPainter, centre: QPointF, radius: float, item: Activity, t: float
    ) -> None:
        """Progress ring (spins when the progress is unknown); check or cross at the end."""
        colour = QColor(item.colour)
        track = QColor(colour)
        track.setAlpha(55)
        box = QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(track, 2.6))
        p.drawEllipse(box)
        pen = QPen(colour, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if item.state == "running" and item.progress is None:
            start = int((-t * 360 * 0.9) % 360 * 16)
            p.drawArc(box, start, int(100 * 16))
        else:
            span = 1.0 if item.state != "running" else (item.progress or 0.0)
            p.drawArc(box, 90 * 16, int(-span * 360 * 16))
        if item.state == "done":
            k = min(
                1.0, (time.monotonic() - item.ended) / 0.35
            )  # the check draws itself
            a = QPointF(centre.x() - radius * 0.42, centre.y() + radius * 0.02)
            b = QPointF(centre.x() - radius * 0.1, centre.y() + radius * 0.34)
            c = QPointF(centre.x() + radius * 0.45, centre.y() - radius * 0.32)
            path = QPainterPath(a)
            if k < 0.4:
                path.lineTo(a + (b - a) * (k / 0.4))
            else:
                path.lineTo(b)
                path.lineTo(b + (c - b) * ((k - 0.4) / 0.6))
            p.drawPath(path)
        elif item.state == "failed":
            d = radius * 0.32
            p.drawLine(
                QPointF(centre.x() - d, centre.y() - d),
                QPointF(centre.x() + d, centre.y() + d),
            )
            p.drawLine(
                QPointF(centre.x() + d, centre.y() - d),
                QPointF(centre.x() - d, centre.y() + d),
            )

    def _draw_live(self, p: QPainter, rect: QRectF, item: Activity, t: float) -> None:
        """Compact island with one Live Activity: its name and its ring."""
        ring = QPointF(rect.right() - PAD - 9, rect.center().y())
        self._ring(p, ring, 9.0, item, t)
        others = len(self._live) - 1
        if others > 0 and not self.multitasking:
            p.setFont(self._small)
            p.setPen(QColor(200, 200, 205))
            p.drawText(QPointF(ring.x() - 31, rect.center().y() + 4), f"+{others}")
            ring = QPointF(ring.x() - 22, ring.y())  # the title stops before it
        left = rect.left() + PAD + 2 * 10.5 + 10
        width = ring.x() - 16 - left
        if width < 30:
            return
        p.setFont(self._small)
        p.setPen(QColor(item.colour))
        metrics = QFontMetricsF(self._small)
        text = metrics.elidedText(item.title, Qt.TextElideMode.ElideRight, width)
        p.drawText(QPointF(left, rect.center().y() + 4), text)

    def _draw_fold(
        self, p: QPainter, item: Activity | None, more: int, t: float
    ) -> None:
        """The dúo folding open like the iPhone Duo's cover half.

        The open bubble is drawn flat, blurred and darkened by how closed
        it is, then mapped onto the half that swings around the hinge, with
        a little perspective (the far edge shrinks as it turns)."""
        fold = self._duo
        size = int(BUBBLE)
        face = QPixmap(size, size)
        face.fill(Qt.GlobalColor.transparent)
        q = QPainter(face)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(0, 0, BUBBLE, BUBBLE)
        if fold.facing():
            self._draw_bubble(q, box, item, more, t)
        else:  # its back, the plain black island
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(0, 0, 0))
            q.drawEllipse(box)
        effect, dark = fold.effect(), fold.darken()
        if dark > 0.0:
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(0, 0, 0, int(255 * dark)))
            q.drawEllipse(box)
        q.end()
        if effect > 0.02:
            # Blur by shrinking and enlarging smoothly: cheap, and soft enough.
            small = max(2, int(size * (1.0 - 0.85 * fold.tilt() / Fold.MAX_TILT)))
            mode = Qt.TransformationMode.SmoothTransformation
            face = face.scaled(small, small, mode=mode).scaled(size, size, mode=mode)
        scale_x = fold.reach()  # -1 (lying over the pill) .. 1 (open)
        depth = 0.25 * math.sin(math.radians(fold.angle)) / BUBBLE
        # Local (x from the hinge, y from the middle) → screen, projective.
        warp = QTransform(scale_x, 0.0, depth, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        warp *= QTransform.fromTranslate(self.hinge(), BUBBLE / 2)
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setTransform(warp, combine=True)
        p.drawPixmap(QPointF(0, -BUBBLE / 2), face)
        p.restore()

    def _draw_bubble(
        self, p: QPainter, box: QRectF, item: Activity | None, more: int, t: float
    ) -> None:
        """The dúo: a second black island with the next activity's ring."""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawEllipse(box)
        if item is None:
            # Multitasking on, nothing in the second half yet: four dots.
            p.setBrush(QColor(235, 235, 240, 190))
            step = box.width() * 0.13
            for dx in (-1, 1):
                for dy in (-1, 1):
                    p.drawEllipse(
                        box.center() + QPointF(dx * step, dy * step), 1.8, 1.8
                    )
            return
        self._ring(p, box.center(), box.width() * 0.3, item, t)
        if more > 0:
            p.setFont(self._small)
            badge = QRectF(box.right() - 15, box.bottom() - 13, 17, 13)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(58, 58, 64))
            p.drawRoundedRect(badge, 6.5, 6.5)
            p.setPen(QColor(240, 240, 245))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"+{more}")

    def _draw_call(self, p: QPainter, rect: QRectF) -> None:
        """Compact notch during a call: green handset + elapsed time."""
        green = QColor(48, 209, 88)
        p.setFont(self._title)
        text = self.call_time()
        width = QFontMetricsF(self._title).horizontalAdvance(text)
        right = rect.right() - PAD
        p.setPen(green)
        p.drawText(QPointF(right - width, rect.center().y() + 4), text)
        x, y = right - width - 12, rect.center().y()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(green)
        p.drawEllipse(QPointF(x, y), 4.5, 4.5)

    def _draw_wave(self, p: QPainter, box: QRectF, bars: int) -> None:
        """Rounded bars from the recent levels, coloured like the orb."""
        _, mid, bright, _ = PALETTES.get(self.state, PALETTES["idle"])
        grad = QLinearGradient(box.topLeft(), box.topRight())
        grad.setColorAt(0.0, QColor(mid))
        grad.setColorAt(1.0, QColor(bright))
        values = list(self._levels)[-bars:]
        gap = box.width() / bars
        bar_w = max(2.0, gap * 0.55)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        t = time.monotonic() - self._t0
        for i, v in enumerate(values):
            # Each bar breathes on its own phase so it reads as a voice wave.
            shape = 0.55 + 0.45 * math.sin(t * 9.0 + i * 1.7) * math.cos(
                t * 3.1 + i * 0.6
            )
            h = max(bar_w, box.height() * min(1.0, 0.12 + v * 1.25 * shape))
            x = box.left() + i * gap + (gap - bar_w) / 2
            y = box.center().y() - h / 2
            p.drawRoundedRect(QRectF(x, y, bar_w, h), bar_w / 2, bar_w / 2)

    def _shimmer(self, p: QPainter, at: QPointF, text: str, t: float) -> None:
        """Label with a light sweep across it (thinking)."""
        width = QFontMetricsF(self._title).horizontalAdvance(text)
        sweep = (t * 0.9) % 1.6 - 0.3
        grad = QLinearGradient(at.x(), 0, at.x() + width, 0)
        base = QColor(150, 150, 165)
        grad.setColorAt(0.0, base)
        grad.setColorAt(max(0.0, min(1.0, sweep - 0.15)), base)
        grad.setColorAt(max(0.0, min(1.0, sweep)), QColor(255, 255, 255))
        grad.setColorAt(max(0.0, min(1.0, sweep + 0.15)), base)
        grad.setColorAt(1.0, base)
        p.setPen(QPen(grad, 1))
        p.drawText(at, text)

    def _look(self, centre: QPointF) -> QPointF:
        """Eyes follow the mouse pointer."""
        here = self.mapToGlobal(centre.toPoint())
        cursor = QCursor.pos()
        dx, dy = cursor.x() - here.x(), cursor.y() - here.y()
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        return QPointF(dx / dist, max(-1.0, min(1.0, dy / dist)))


__all__ = ["BUBBLE", "LIVE", "Notch"]

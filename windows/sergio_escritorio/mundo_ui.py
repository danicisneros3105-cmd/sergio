"""God's Eye View, native windows: public live cameras of a place, and a
flight followed live.

* CamsWindow: the official public cameras closest to a place (TfL London,
  Fintraffic, DriveBC, Live Traffic NSW, Ontario 511, and Windy's webcams
  worldwide with a free key), a grid of stills that refresh every 10 s.
* FlightWindow: one flight right now — where, how high, how fast, the route
  — refreshed every 8 s, with its trail, the 3D globe aimed at it and the
  public live map that follows the plane.

Data comes from the local Sergio server (/v1/world/cams, /v1/world/flight);
the camera stills are downloaded straight from the authorities' servers.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

import httpx
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio import idioma

FONT = ["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"]
STYLE = """
QWidget#world { background: #0b0d10; }
QLabel { color: #f5f5f7; }
QLabel#hint { color: #8e8e93; font-size: 12px; }
QLineEdit { background: #1c1c1e; color: #f5f5f7; border: 1px solid #2c2c2e; border-radius: 14px;
            padding: 8px 12px; font-size: 13px; }
QPushButton { background: #0a84ff; color: white; border: none; border-radius: 14px; padding: 8px 16px;
              font-weight: 600; }
QPushButton#plain { background: #2c2c2e; }
QScrollArea { background: transparent; border: none; }
"""
CAM_REFRESH_MS = 10_000
FLIGHT_REFRESH_MS = 8_000


def _font(size: float, bold: bool = False) -> QFont:
    f = QFont(FONT)
    f.setPointSizeF(size)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


class CamTile(QWidget):
    """One public camera: its latest still, name, operator and distance."""

    def __init__(self, cam: dict[str, Any]) -> None:
        super().__init__()
        self.cam = cam
        self.image: QImage | None = None
        self.updated = 0.0
        self.setMinimumSize(300, 210)

    def set_image(self, data: bytes) -> None:
        image = QImage.fromData(data)
        if not image.isNull():
            self.image, self.updated = image, time.time()
            self.update()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 16, 16)
        p.setClipPath(clip)
        p.fillRect(rect, QColor("#16181c"))
        if self.image is not None:
            scaled = self.image.scaled(
                int(rect.width()), int(rect.height()),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation,
            )
            p.drawImage(
                QPointF(rect.center().x() - scaled.width() / 2, rect.center().y() - scaled.height() / 2), scaled
            )
        else:
            p.setPen(QColor("#5a5f66"))
            p.setFont(_font(10))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Cargando…")
        shade = QRectF(rect.left(), rect.bottom() - 54, rect.width(), 54)
        p.fillRect(shade, QColor(0, 0, 0, 150))
        p.setPen(QColor("white"))
        p.setFont(_font(10, True))
        p.drawText(shade.adjusted(12, 6, -12, -26), Qt.AlignmentFlag.AlignLeft, self.cam["name"][:46])
        p.setPen(QColor("#c7c7cc"))
        p.setFont(_font(8.5))
        p.drawText(
            shade.adjusted(12, 28, -12, -6), Qt.AlignmentFlag.AlignLeft,
            f"{self.cam['provider']} · {self.cam.get('km', 0):.1f} km",
        )
        # The LIVE badge (red while the still is fresh).
        fresh = time.time() - self.updated < 40
        badge = QRectF(rect.left() + 10, rect.top() + 10, 52, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ff3b30") if fresh else QColor("#48484a"))
        p.drawRoundedRect(badge, 10, 10)
        p.setPen(QColor("white"))
        p.setFont(_font(7.5, True))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, "● LIVE" if fresh else "…")
        p.end()


class CamsWindow(QWidget):
    loaded = Signal(dict)
    frame = Signal(int, bytes)

    def __init__(self, server: str, open_url: Callable[[str], None] = lambda _u: None, lang: str = "es") -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("world")
        self.setStyleSheet(STYLE)
        self.server, self.open_url, self.lang = server, open_url, lang
        self.setWindowTitle(f"Sergio · {idioma.t('cams', lang)}")
        self.http = httpx.Client(timeout=httpx.Timeout(20, connect=5), follow_redirects=True)
        self.tiles: list[CamTile] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        title = QLabel(idioma.t("cams", lang))
        title.setFont(_font(20, True))
        lay.addWidget(title)
        row = QHBoxLayout()
        self.place = QLineEdit()
        self.place.setPlaceholderText(idioma.t("place", lang))
        self.place.returnPressed.connect(lambda: self.show_place(self.place.text()))
        row.addWidget(self.place, 1)
        go = QPushButton(idioma.t("show", lang))
        go.clicked.connect(lambda: self.show_place(self.place.text()))
        row.addWidget(go)
        lay.addLayout(row)
        self.note = QLabel("")
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(holder)
        self.grid.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        lay.addWidget(scroll, 1)
        foot = QLabel(
            "Solo cámaras públicas oficiales (tráfico y clima) que sus dueños publican para todos; "
            "se actualizan cada 10 s."
        )
        foot.setObjectName("hint")
        foot.setWordWrap(True)
        lay.addWidget(foot)
        self.loaded.connect(self._show)
        self.frame.connect(lambda i, data: self.tiles[i].set_image(data) if i < len(self.tiles) else None)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.resize(1000, 720)

    def show_place(self, place: str) -> None:
        place = place.strip()
        if not place:
            return
        self.place.setText(place)
        self.note.setText(f"Buscando cámaras públicas cerca de {place}…")
        self.show()
        self.raise_()
        self.activateWindow()

        def job() -> None:
            try:
                resp = self.http.get(f"{self.server}/v1/world/cams", params={"place": place}, timeout=40)
                data = resp.json()
                if resp.status_code != 200:
                    data = {"error": data.get("detail") or resp.text}
            except Exception as exc:  # noqa: BLE001 — shown in the window
                data = {"error": str(exc)}
            self.loaded.emit(data)

        threading.Thread(target=job, daemon=True).start()

    def _show(self, data: dict) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.tiles = []
        if "error" in data:
            self.note.setText(f"No pude buscar cámaras: {str(data['error'])[:200]}")
            return
        cams = data.get("cams") or []
        label = str(data.get("label") or "").split(",")[0]
        if not cams:
            self.note.setText(
                f"No hay cámaras públicas oficiales cerca de {label}. Hoy cubro {data.get('coverage', '')}"
                " y, con una clave gratuita de Windy (WINDY_API_KEY), webcams públicas de todo el mundo."
            )
            return
        self.note.setText(f"{len(cams)} cámaras públicas cerca de {label} · fuentes: {', '.join(data.get('sources', []))}")
        for i, cam in enumerate(cams):
            tile = CamTile(cam)
            self.tiles.append(tile)
            self.grid.addWidget(tile, i // 3, i % 3)
        self._refresh()
        self.timer.start(CAM_REFRESH_MS)

    def _refresh(self) -> None:
        if not self.isVisible():
            self.timer.stop()
            return
        urls = [t.cam["url"] for t in self.tiles]

        def job() -> None:
            for i, url in enumerate(urls):
                try:
                    resp = self.http.get(url, params={"t": int(time.time())})
                    if resp.status_code == 200 and resp.content:
                        self.frame.emit(i, resp.content)
                except Exception:  # noqa: BLE001 — that camera is offline now
                    continue

        threading.Thread(target=job, daemon=True).start()


class Track(QWidget):
    """The flight's trail on a dark grid, the plane at its heading."""

    def __init__(self) -> None:
        super().__init__()
        self.points: list[tuple[float, float]] = []
        self.heading = 0.0
        self.setMinimumHeight(240)

    def add(self, lat: float, lon: float, heading: float | None) -> None:
        if not self.points or self.points[-1] != (lat, lon):
            self.points.append((lat, lon))
            self.points = self.points[-120:]
        if heading is not None:
            self.heading = heading
        self.update()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#111418"))
        p.drawRoundedRect(rect, 16, 16)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        for i in range(1, 8):
            x = rect.left() + rect.width() * i / 8
            y = rect.top() + rect.height() * i / 8
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if not self.points:
            p.end()
            return
        lats = [a for a, _ in self.points]
        lons = [b for _, b in self.points]
        span = max(max(lats) - min(lats), max(lons) - min(lons), 0.08) * 1.4
        clat, clon = (max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2
        scale = min(rect.width(), rect.height()) / span

        def at(lat: float, lon: float) -> QPointF:
            return QPointF(rect.center().x() + (lon - clon) * scale, rect.center().y() - (lat - clat) * scale)

        path = QPainterPath(at(*self.points[0]))
        for lat, lon in self.points[1:]:
            path.lineTo(at(lat, lon))
        p.setPen(QPen(QColor("#ffd60a"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)
        here = at(*self.points[-1])
        p.translate(here)
        p.rotate(self.heading)
        plane = QPainterPath()
        for x, y in ((0, -14), (2, -4), (13, 2), (2, 1), (1.5, 9), (5, 12), (-5, 12), (-1.5, 9), (-2, 1), (-13, 2), (-2, -4)):
            (plane.lineTo if plane.elementCount() else plane.moveTo)(QPointF(x, y))
        plane.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("white"))
        p.drawPath(plane)
        p.end()


class FlightWindow(QWidget):
    loaded = Signal(dict)

    def __init__(self, server: str, open_url: Callable[[str], None] = lambda _u: None, lang: str = "es") -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("world")
        self.setStyleSheet(STYLE)
        self.server, self.open_url, self.lang = server, open_url, lang
        self.flight = ""
        self.data: dict[str, Any] = {}
        self.http = httpx.Client(timeout=httpx.Timeout(20, connect=5))
        self.setWindowTitle(f"Sergio · {idioma.t('flight', lang)}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        title = QLabel(idioma.t("flight", lang))
        title.setFont(_font(20, True))
        lay.addWidget(title)
        row = QHBoxLayout()
        self.number = QLineEdit()
        self.number.setPlaceholderText(idioma.t("flight_number", lang))
        self.number.returnPressed.connect(lambda: self.follow(self.number.text()))
        row.addWidget(self.number, 1)
        go = QPushButton(idioma.t("follow", lang))
        go.clicked.connect(lambda: self.follow(self.number.text()))
        row.addWidget(go)
        lay.addLayout(row)
        self.headline = QLabel("")
        self.headline.setFont(_font(15, True))
        self.headline.setWordWrap(True)
        lay.addWidget(self.headline)
        self.facts = QLabel("")
        self.facts.setObjectName("hint")
        self.facts.setWordWrap(True)
        self.facts.setStyleSheet("font-size: 13px; color: #c7c7cc;")
        lay.addWidget(self.facts)
        self.track = Track()
        lay.addWidget(self.track, 1)
        buttons = QHBoxLayout()
        globe = QPushButton("Ver en el globo 3D")
        globe.clicked.connect(lambda: self._open("globe"))
        buttons.addWidget(globe)
        live = QPushButton("Mapa en vivo (sigue al avión)")
        live.setObjectName("plain")
        live.clicked.connect(lambda: self._open("live_map"))
        buttons.addWidget(live)
        lay.addLayout(buttons)
        self.loaded.connect(self._show)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.resize(640, 640)

    def follow(self, flight: str) -> None:
        flight = flight.strip()
        if not flight:
            return
        if flight != self.flight:
            self.track.points = []
        self.flight = flight
        self.number.setText(flight)
        self.headline.setText(f"Buscando el vuelo {flight.upper()} en el aire…")
        self.show()
        self.raise_()
        self.activateWindow()
        self._poll()
        self.timer.start(FLIGHT_REFRESH_MS)

    def _poll(self) -> None:
        if not self.isVisible() and self.data:
            self.timer.stop()
            return
        flight = self.flight

        def job() -> None:
            try:
                resp = self.http.get(f"{self.server}/v1/world/flight", params={"q": flight})
                data = resp.json()
                if resp.status_code != 200:
                    data = {"error": data.get("detail") or resp.text}
            except Exception as exc:  # noqa: BLE001
                data = {"error": str(exc)}
            self.loaded.emit(data)

        threading.Thread(target=job, daemon=True).start()

    def _show(self, data: dict) -> None:
        if "error" in data:
            if not self.data:
                self.headline.setText(str(data["error"])[:200])
            return
        self.data = data
        route = data.get("route") or {}
        trip = " → ".join(x for x in (route.get("from"), route.get("to")) if x)
        self.headline.setText(
            " · ".join(x for x in (data.get("callsign"), route.get("airline"), trip) if x)
        )
        bits = []
        if data.get("on_ground"):
            bits.append("En tierra")
        elif data.get("alt_m") is not None:
            bits.append(f"{data['alt_m']:,} m de altura".replace(",", "."))
        if data.get("speed_kmh") is not None:
            bits.append(f"{data['speed_kmh']} km/h")
        if data.get("track") is not None:
            bits.append(f"rumbo {round(data['track'])}°")
        if data.get("type"):
            bits.append(str(data["type"]))
        bits.append(f"{data['lat']:.3f}, {data['lon']:.3f}")
        bits.append(f"datos: {data.get('source', '')}, cada {FLIGHT_REFRESH_MS // 1000} s")
        self.facts.setText(" · ".join(bits))
        self.track.add(float(data["lat"]), float(data["lon"]), data.get("track"))

    def _open(self, which: str) -> None:
        if which == "globe":
            url = ((self.data.get("globe") or {}).get("url")) or ""
        else:
            url = self.data.get("live_map") or ""
        if url:
            self.open_url(url)


def distance_label(km: float) -> str:
    return f"{km:.0f} km" if km >= 10 else f"{km:.1f} km"


__all__ = ["CamsWindow", "FlightWindow", "Track", "distance_label"]

"""The control center's home: quick buttons and what is running now.

The owner (26 Oct 2026): «en el centro de control del notch solo se podrá
ver botón para Multitasking y Split Screen, Retroceder última acción de
Sergio, Usage, Change Model / Effort, Display, etc., y podrás ver las
acciones que están corriendo ahora mismo; agrégale personalización para
skills».

So the panel opens on one page, like Control Center on a Mac:

* **En marcha** — what Sergio, the Nodes, the swarms and Cowork are doing
  right now (``/v1/personal/en-marcha`` plus this PC's own tasks), each with
  a stop button;
* the switches as round buttons (listen for «Sergio», screen control…);
* six tiles: Multitarea (split island and split app window), Deshacer
  (the newest reversible thing Sergio did, ``deshacer.py``), Uso (today's
  share of the plan), Modelo (Gemini model and effort), Pantalla (Night
  Shift, the notch) and Habilidades (which skills Sergio may use).

Everything else (Nodes, Swarm, Health, Settings) is one step away and comes
back with «Volver». No text explains what a button does: the label does.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio import estilo, idioma
from sergio_escritorio.iconos import icon, pixmap
from sergio_escritorio.voice import api_base

if TYPE_CHECKING:  # the panel itself, for the type checker only
    from sergio_escritorio.panel import ControlCenter, Toggle

TEXT, SECONDARY, CARD, LINE = estilo.TEXT, estilo.SECONDARY, estilo.CARD, estilo.LINE
BLUE = estilo.BLUE
MAX_RUNNING = 3  # rows shown; the rest is «y N más»
ADDRESS = ("señor", "señora", "nombre", "neutro", "tu")  # personal.ADDRESS on the server


def _font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    estilo.load_fonts()
    font = QFont()
    font.setFamilies(estilo.families())
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


class RoundToggle(QAbstractButton):
    """A switch as a round button (Control Center's top row): blue when on."""

    SIZE = 48

    def __init__(self, toggle: "Toggle") -> None:
        super().__init__()
        self.toggle = toggle
        self.setCheckable(True)
        self.setChecked(bool(toggle.get()))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(76, 74)
        self.setToolTip(toggle.label)
        self.setAccessibleName(toggle.label)
        self.toggled.connect(lambda on: self.toggle.set(on))

    def sync(self) -> None:
        self.blockSignals(True)
        self.setChecked(bool(self.toggle.get()))
        self.blockSignals(False)
        self.update()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        r = self.SIZE / 2
        centre = QPointF(self.width() / 2, r + 1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(BLUE if on else estilo.CARD_HOT))
        p.drawEllipse(centre, r, r)
        p.drawPixmap(
            QRectF(centre.x() - 10, centre.y() - 10, 20, 20).toRect(),
            pixmap(self.toggle.icon, TEXT, 20),
        )
        p.setPen(QColor(TEXT if on else SECONDARY))
        font = _font(7.5, QFont.Weight.Medium)
        p.setFont(font)
        words = QFontMetricsF(font).elidedText(
            self.toggle.label, Qt.TextElideMode.ElideRight, self.width()
        )
        p.drawText(
            QRectF(0, self.SIZE + 6, self.width(), 18),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            words,
        )
        p.end()


class QuickTile(QAbstractButton):
    """A Control Center tile: icon, name and one line of state."""

    def __init__(self, kind: str, title: str, checkable: bool = False) -> None:
        super().__init__()
        self.kind = kind
        self.title = title
        self.sub = ""
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(68)
        self.setAccessibleName(title)

    def set_sub(self, text: str) -> None:
        if text != self.sub:
            self.sub = text
            self.setAccessibleDescription(text)
            self.update()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isCheckable() and self.isChecked()
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(LINE), 1.0))
        p.setBrush(QColor(CARD))
        p.drawRoundedRect(rect, 16, 16)
        dot = QPointF(30, rect.center().y())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(BLUE if on else estilo.CARD_HOT))
        p.drawEllipse(dot, 17, 17)
        colour = TEXT if self.isEnabled() else SECONDARY
        p.drawPixmap(QRectF(dot.x() - 9, dot.y() - 9, 18, 18).toRect(), pixmap(self.kind, colour, 18))
        width = rect.width() - 64 - 10
        title = _font(9.5, QFont.Weight.DemiBold)
        p.setFont(title)
        p.setPen(QColor(colour))
        p.drawText(
            QPointF(58, rect.center().y() - 3),
            QFontMetricsF(title).elidedText(self.title, Qt.TextElideMode.ElideRight, width),
        )
        small = _font(8.5)
        p.setFont(small)
        p.setPen(QColor(SECONDARY))
        p.drawText(
            QPointF(58, rect.center().y() + 14),
            QFontMetricsF(small).elidedText(self.sub, Qt.TextElideMode.ElideRight, width),
        )
        p.end()


def _icon_button(name: str, tip: str) -> QPushButton:
    button = QPushButton()
    button.setObjectName("icon")
    button.setIcon(icon(name, TEXT, 15))
    button.setIconSize(QSize(15, 15))
    button.setToolTip(tip)
    button.setAccessibleName(tip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _scroll(page: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(page)
    return scroll


class HomeMixin:
    """The home page and its three sheets, mixed into :class:`ControlCenter`.

    The signals live on the panel (Qt only sees signals declared on QObject
    classes): ``home_ready``, ``models_ready``, ``skills_ready``, ``undone``.
    """

    # -- pages -------------------------------------------------------------
    def _home(self: "ControlCenter") -> QWidget:
        t = lambda key: idioma.t(key, self.lang)  # noqa: E731
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        col.addWidget(QLabel(t("running_now").upper(), objectName="section"))
        self.running_box = QVBoxLayout()
        self.running_box.setSpacing(6)
        col.addLayout(self.running_box)
        self._running_key: list[str] | None = None
        self._show_running([])
        row = QHBoxLayout()
        row.setSpacing(0)
        self.tiles = [RoundToggle(toggle) for toggle in self.actions.toggles]
        for i, tile in enumerate(self.tiles):
            if i:
                row.addStretch(1)
            row.addWidget(tile)
        col.addLayout(row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.multi_tile = QuickTile("split", t("q_multi"), checkable=True)
        self.multi_tile.setChecked(bool(self.actions.multitasking()))
        self.multi_tile.toggled.connect(self._set_multitasking)
        self.undo_tile = QuickTile("undo", t("q_undo"))
        self.undo_tile.clicked.connect(self._undo)
        self.usage_tile = QuickTile("gauge", t("q_usage"))
        self.usage_tile.clicked.connect(lambda: self._web("/uso"))
        self.model_tile = QuickTile("sparkles", t("q_model"))
        self.model_tile.clicked.connect(lambda: self.show_tab(self.MODEL_SHEET))
        self.display_tile = QuickTile("monitor", t("q_display"))
        self.display_tile.clicked.connect(lambda: self.show_tab(self.DISPLAY_SHEET))
        self.skills_tile = QuickTile("puzzle", t("q_skills"))
        self.skills_tile.clicked.connect(lambda: self.show_tab(self.SKILLS_SHEET))
        self.quick_tiles = [
            self.multi_tile,
            self.undo_tile,
            self.usage_tile,
            self.model_tile,
            self.display_tile,
            self.skills_tile,
        ]
        for i, tile in enumerate(self.quick_tiles):
            grid.addWidget(tile, i // 2, i % 2)
        col.addLayout(grid)
        col.addStretch(1)
        self._sync_quick()
        return _scroll(page)

    def _model_sheet(self: "ControlCenter") -> QWidget:
        from sergio_escritorio.panel import BRAINS, Segmented  # noqa: F401 — BRAINS: the effort keys

        t = lambda key: idioma.t(key, self.lang)  # noqa: E731
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        col.addWidget(QLabel(t("q_effort").upper(), objectName="section"))
        self.brain = Segmented(
            {key: idioma.t(f"e_{key}", self.lang) for key in BRAINS},
            str(self.actions.config.get("effort", "auto")),
            lambda k: (self._save(effort=k), self._sync_quick()),
        )
        col.addWidget(self.brain)
        col.addWidget(QLabel(t("q_model").upper(), objectName="section"))
        self.model_list = QListWidget()
        self.model_list.itemClicked.connect(self._pick_model)
        col.addWidget(self.model_list, 1)
        self._show_models({})
        return page

    def _skills_sheet(self: "ControlCenter") -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(12)
        col.addWidget(QLabel(idioma.t("q_skills_hint", self.lang), objectName="hint", wordWrap=True))
        self.skills_box = QVBoxLayout()
        self.skills_box.setSpacing(14)
        col.addLayout(self.skills_box)
        col.addStretch(1)
        self._skills: list[dict] = []
        return _scroll(page)

    def _display_sheet(self: "ControlCenter") -> QWidget:
        from sergio_escritorio.panel import Switch, _row

        t = lambda key: idioma.t(key, self.lang)  # noqa: E731
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(12)
        self.display_switches: list[tuple["Toggle", Switch]] = []
        for toggle in self.actions.display:
            switch = Switch(bool(toggle.get()))
            switch.toggled.connect(lambda on, tg=toggle: (tg.set(on), self._sync_quick()))
            self.display_switches.append((toggle, switch))
            col.addLayout(_row(toggle.label, switch))
        night = QPushButton(t("q_night_settings"))
        night.setCursor(Qt.CursorShape.PointingHandCursor)
        night.clicked.connect(lambda: self._open_section("night"))
        col.addWidget(night)
        hide = QPushButton(t("hide_notch"))
        hide.setCursor(Qt.CursorShape.PointingHandCursor)
        hide.clicked.connect(lambda: (self.hide(), self.actions.hide_notch()))
        col.addWidget(hide)
        col.addStretch(1)
        return _scroll(page)

    def _address_rows(self: "ControlCenter", col: QVBoxLayout) -> None:
        """«Cómo le llamo» and the name, in Settings (``/v1/personal/perfil``)."""
        from sergio_escritorio.panel import _row

        self.address_box = QComboBox()
        for key in ADDRESS:
            self.address_box.addItem(idioma.t(f"addr_{key}", self.lang), key)
        self.address_box.setFixedWidth(208)
        self.address_box.currentIndexChanged.connect(lambda _i: self._save_profile())
        col.addLayout(_row(idioma.t("q_address", self.lang), self.address_box))
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText(idioma.t("q_name", self.lang))
        self.name_entry.setMaxLength(40)
        self.name_entry.editingFinished.connect(self._save_profile)
        col.addWidget(self.name_entry)
        self._profile_loaded = False

    # -- the back row ------------------------------------------------------
    def _back_row(self: "ControlCenter") -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        back = _icon_button("chevron-left", idioma.t("q_back", self.lang))
        back.clicked.connect(lambda: self.show_tab(self.HOME))
        row.addWidget(back)
        self.page_title = QLabel("", objectName="title")
        row.addWidget(self.page_title, 1)
        bar.setVisible(False)
        self.back_bar = bar
        return bar

    def page_name(self: "ControlCenter", index: int) -> str:
        sheets = {self.MODEL_SHEET: "q_model", self.SKILLS_SHEET: "q_skills", self.DISPLAY_SHEET: "q_display"}
        if index in sheets:
            return idioma.t(sheets[index], self.lang)
        if index == self.SETTINGS_TAB:
            return idioma.t("q_settings", self.lang)
        return idioma.t(self.TABS[index], self.lang) if index < len(self.TABS) else ""

    # -- state -------------------------------------------------------------
    def _sync_quick(self: "ControlCenter") -> None:
        """What each tile says, from what is known on this PC right now."""
        t = lambda key: idioma.t(key, self.lang)  # noqa: E731
        on = bool(self.actions.multitasking())
        self.multi_tile.blockSignals(True)
        self.multi_tile.setChecked(on)
        self.multi_tile.blockSignals(False)
        self.multi_tile.set_sub(t("q_multi_on") if on else t("q_off"))
        last = self.actions.undo_label()
        self.undo_tile.set_sub(last or t("q_undo_none"))
        self.undo_tile.setEnabled(bool(last))
        model = str(self.actions.config.get("model") or "")
        effort = str(self.actions.config.get("effort", "auto"))
        words = self._model_names.get(model, model) if model else t("q_auto")
        if effort != "auto":
            words += " · " + t(f"e_{effort}")
        self.model_tile.set_sub(words)
        lit = [tg.label for tg, _s in getattr(self, "display_switches", []) if tg.get()]
        self.display_tile.set_sub(", ".join(lit) if lit else t("q_off"))
        for toggle, switch in getattr(self, "display_switches", []):
            switch.blockSignals(True)
            switch.setChecked(bool(toggle.get()))
            switch.blockSignals(False)
        for tile in self.tiles:
            tile.sync()

    def _refresh_home(self: "ControlCenter", full: bool = False) -> None:
        """What is running (every few seconds); usage and skills on opening."""
        base = api_base(self.actions.server_url)
        http = self._http()

        def job() -> dict:
            out: dict[str, Any] = {}
            try:
                out["running"] = http.get(f"{base}/v1/personal/en-marcha").json().get("en_marcha") or []
            except Exception:  # noqa: BLE001 — server off: only this PC's tasks
                out["running"] = []
            if full:
                try:
                    items = (http.get(f"{base}/v1/plans/me").json().get("usage") or {}).get("items") or []
                    shares = [i["used"] / i["limit"] for i in items if i.get("limit")]
                    out["usage"] = round(100 * max(shares)) if shares else 0
                except Exception:  # noqa: BLE001
                    out["usage"] = None
                try:
                    out["skills"] = http.get(f"{base}/v1/personal/habilidades").json().get("habilidades") or []
                except Exception:  # noqa: BLE001
                    out["skills"] = None
            return out

        self._background(job, self.home_ready)

    def _show_home(self: "ControlCenter", data: dict) -> None:
        self._show_running(data.get("running") or [])
        if "usage" in data:
            usage = data["usage"]
            self.usage_tile.set_sub(
                idioma.t("q_usage_today", self.lang).format(n=usage)
                if usage is not None
                else idioma.t("no_server", self.lang)
            )
        if data.get("skills") is not None:
            self._show_skills({"habilidades": data["skills"]})
        self._sync_quick()

    def _show_running(self: "ControlCenter", server_rows: list[dict]) -> None:
        rows: list[tuple[str, Any]] = []
        for r in server_rows:
            rows.append((f"{r.get('quien', '')} · {r.get('que', '')}", ("srv", r.get("detener", ""))))
        details = self.actions.swarm_details()
        if details:  # this PC's own tasks, with their real progress
            for d in details:
                progress = d.get("progress")
                percent = f" · {round(progress * 100)}%" if progress is not None else ""
                rows.append((f"{d.get('title', '')}{percent}", ("pc", d.get("id"))))
        else:
            rows.extend((line, None) for line in self.actions.swarm() or [])
        key = [text for text, _ in rows]
        if key == self._running_key:
            return
        self._running_key = key
        while self.running_box.count():
            old = self.running_box.takeAt(0).widget()
            if old is not None:
                old.deleteLater()
        if not rows:
            self.running_box.addWidget(QLabel(idioma.t("nothing_running", self.lang), objectName="hint"))
            return
        for text, stop in rows[:MAX_RUNNING]:
            self.running_box.addWidget(self._running_row(text, stop))
        if len(rows) > MAX_RUNNING:
            more = QLabel(idioma.t("q_more", self.lang).format(n=len(rows) - MAX_RUNNING), objectName="hint")
            self.running_box.addWidget(more)

    def _running_row(self: "ControlCenter", text: str, stop: Any) -> QWidget:
        row = QWidget()
        row.setObjectName("runrow")
        row.setStyleSheet(f"QWidget#runrow {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}")
        line = QHBoxLayout(row)
        line.setContentsMargins(12, 4, 4, 4)
        line.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {BLUE}; border-radius: 4px;")
        line.addWidget(dot)
        label = QLabel()
        label.setText(QFontMetricsF(label.font()).elidedText(text, Qt.TextElideMode.ElideRight, 300))
        label.setToolTip(text)
        line.addWidget(label, 1)
        if stop is not None:
            button = _icon_button("x", idioma.t("q_stop", self.lang))
            button.clicked.connect(lambda _c=False, s=stop: self._stop(s))
            line.addWidget(button)
        return row

    # -- actions -----------------------------------------------------------
    def _stop(self: "ControlCenter", stop: tuple[str, Any]) -> None:
        kind, target = stop
        if kind == "pc":
            self.actions.swarm_cancel(target)
            self._running_key = None
            self._refresh_home()
            return
        if not target:
            return
        base = api_base(self.actions.server_url)

        def job() -> dict:
            self._http().post(f"{base}{target}")
            return {"running": self._http().get(f"{base}/v1/personal/en-marcha").json().get("en_marcha") or []}

        self._background(job, self.home_ready)

    def _set_multitasking(self: "ControlCenter", on: bool) -> None:
        """Split the island and the open app window together (like «activa multitasking»)."""
        self.actions.set_multitasking(on)
        threading.Thread(target=self.actions.split_screen, args=(on,), daemon=True).start()
        self._sync_quick()

    def _undo(self: "ControlCenter") -> None:
        self.undo_tile.setEnabled(False)
        self._background(lambda: {"said": self.actions.undo()}, self.undone)

    def _show_undone(self: "ControlCenter", data: dict) -> None:
        said = str(data.get("said") or data.get("error") or "")
        self.undo_tile.set_sub(said)
        self.subtitle.setText(said)
        self.subtitle.setVisible(bool(said))
        QTimer.singleShot(3000, self._sync_quick)

    def _load_models(self: "ControlCenter") -> None:
        base = api_base(self.actions.server_url)
        self._background(lambda: self._http().get(f"{base}/v1/personal/modelos").json(), self.models_ready)

    def _show_models(self: "ControlCenter", data: dict) -> None:
        chosen = str(self.actions.config.get("model") or "")
        self.model_list.clear()
        auto = QListWidgetItem(idioma.t("q_auto", self.lang))
        auto.setData(Qt.ItemDataRole.UserRole, "")
        self.model_list.addItem(auto)
        if chosen == "":
            self.model_list.setCurrentItem(auto)
        for m in data.get("modelos") or []:
            self._model_names[m["id"]] = m.get("nombre") or m["id"]
            item = QListWidgetItem(f"{m.get('nombre', m['id'])}\n{m.get('para', '')}".strip())
            item.setData(Qt.ItemDataRole.UserRole, m["id"])
            if not m.get("disponible", True):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.model_list.addItem(item)
            if m["id"] == chosen:
                self.model_list.setCurrentItem(item)
        if data.get("error"):
            self.model_list.addItem(idioma.t("no_server", self.lang))
        self._sync_quick()

    def _pick_model(self: "ControlCenter", item: QListWidgetItem) -> None:
        model = item.data(Qt.ItemDataRole.UserRole)
        if model is None:
            return
        self._save(model=str(model))
        self._sync_quick()

    def _load_skills(self: "ControlCenter") -> None:
        base = api_base(self.actions.server_url)
        self._background(lambda: self._http().get(f"{base}/v1/personal/habilidades").json(), self.skills_ready)

    def _show_skills(self: "ControlCenter", data: dict) -> None:
        from sergio_escritorio.panel import Switch

        skills = data.get("habilidades")
        if skills is None:
            if data.get("error") and not self._skills:
                self._fill_skills([QLabel(idioma.t("no_server", self.lang), objectName="hint")])
            return
        on = sum(1 for s in skills if s.get("activa"))
        self.skills_tile.set_sub(idioma.t("q_skills_on", self.lang).format(n=on, total=len(skills)))
        if [(s["clave"], s.get("activa")) for s in skills] == [(s["clave"], s.get("activa")) for s in self._skills]:
            return
        self._skills = list(skills)
        rows: list[QWidget] = []
        for skill in skills:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            words = QVBoxLayout()
            words.setSpacing(0)
            words.addWidget(QLabel(skill.get("nombre") or skill["clave"]))
            if skill.get("hace"):
                words.addWidget(QLabel(skill["hace"], objectName="hint", wordWrap=True))
            line.addLayout(words, 1)
            switch = Switch(bool(skill.get("activa")))
            switch.setAccessibleName(skill.get("nombre") or skill["clave"])
            switch.toggled.connect(lambda value, k=skill["clave"]: self._switch_skill(k, value))
            line.addWidget(switch)
            rows.append(row)
        self._fill_skills(rows)

    def _fill_skills(self: "ControlCenter", rows: list[QWidget]) -> None:
        while self.skills_box.count():
            old = self.skills_box.takeAt(0).widget()
            if old is not None:
                old.deleteLater()
        for row in rows:
            self.skills_box.addWidget(row)

    def _switch_skill(self: "ControlCenter", key: str, on: bool) -> None:
        base = api_base(self.actions.server_url)

        def job() -> dict:
            resp = self._http().put(f"{base}/v1/personal/habilidades/{key}", json={"activa": on})
            resp.raise_for_status()
            return resp.json()

        self._background(job, self.skills_ready)

    def _load_profile(self: "ControlCenter") -> None:
        base = api_base(self.actions.server_url)
        self._background(lambda: self._http().get(f"{base}/v1/personal/perfil").json(), self.profile_ready)

    def _show_profile(self: "ControlCenter", data: dict) -> None:
        if data.get("error"):
            return
        self.address_box.blockSignals(True)
        self.address_box.setCurrentIndex(max(0, self.address_box.findData(data.get("trato", "señor"))))
        self.address_box.blockSignals(False)
        self.name_entry.setText(str(data.get("nombre") or ""))
        self._profile_loaded = True

    def _save_profile(self: "ControlCenter") -> None:
        if not self._profile_loaded:
            return  # never overwrite what the server has with empty fields
        base = api_base(self.actions.server_url)
        body = {"trato": self.address_box.currentData(), "nombre": self.name_entry.text().strip()}
        self._background(
            lambda: self._http().put(f"{base}/v1/personal/perfil", json=body).json(),
            self.profile_ready,
        )


__all__ = ["ADDRESS", "HomeMixin", "QuickTile", "RoundToggle"]

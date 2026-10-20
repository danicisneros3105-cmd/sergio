"""Health windows: «Mi salud» (report, today, questionnaire, devices) and
the daily card at your chosen time."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from sergio_escritorio.coach_ui import in_background
from sergio_escritorio.salud import DAILY, QUESTIONS, Health, body_metrics, trends

STYLE = """
QWidget#salud { background: #1C1C1E; }
QLabel { color: #F5F5F7; font-size: 13px; }
QLabel#muted { color: #8E8E93; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #8E8E93; padding: 8px 14px; font-size: 13px; }
QTabBar::tab:selected { color: white; border-bottom: 2px solid #30D158; }
QTextBrowser { background: #2C2C2E; color: #F5F5F7; border: none; border-radius: 12px; padding: 12px; font-size: 13px; }
QLineEdit, QComboBox { background: #2C2C2E; color: white; border: none; border-radius: 8px; padding: 6px 8px; font-size: 13px; }
QPushButton { background: #30D158; color: #0b2414; border: none; border-radius: 10px; padding: 8px 16px; font-size: 13px; font-weight: 600; }
QPushButton#plain { background: #3A3A3C; color: white; }
QScrollArea { border: none; background: transparent; }
"""

DEVICE_HELP = """
<h3>Conectar su reloj o app</h3>
<p>Sergio importa solo cada día lo que aparezca en la <b>carpeta de sincronización</b>
(elija una que su teléfono sincronice: iCloud Drive, Google Drive, OneDrive…).</p>
<ul>
<li><b>Apple Watch / Salud (iPhone)</b>: Salud → su foto → <i>Exportar todos los datos de salud</i> → guarde el .zip en la carpeta. Para que sea automático, una app de auto-exportación (p. ej. «Health Auto Export») puede dejar un CSV diario allí.</li>
<li><b>Garmin Connect</b>: connect.garmin.com → Informes / Estadísticas → Exportar CSV (pasos, sueño, estrés, FC en reposo).</li>
<li><b>Google Fit / Health Connect / Wear OS</b>: takeout.google.com → Fit → «Daily activity metrics» (CSV).</li>
<li><b>Samsung Health</b>: Ajustes → Descargar datos personales (CSV).</li>
<li><b>Fitbit, Polar, Amazfit/Zepp, Xiaomi, Huawei</b>: su opción «Exportar datos» en CSV.</li>
<li><b>Oura y Strava</b>: se conectan en el servidor (<code>sergio conectores</code>).</li>
<li><b>Sin forma de conectar</b>: Sergio le pregunta lo del día a la hora que elija (pestaña «Hoy»).</li>
</ul>
"""


def _font(size: float, bold: bool = False) -> QFont:
    f = QFont(["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"])
    f.setPointSizeF(size)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


def report_html(health: Health) -> str:
    rep = health.report
    m = body_metrics(health.answers)
    t = trends(health.days, date.today())
    parts = ["<h2>Mi salud</h2>"]
    if not health.answers:
        parts.append("<p>Empiece por el <b>Cuestionario</b>: con eso calculo sus métricas y hago el primer análisis.</p>")
    chips = []
    if "imc" in m:
        chips.append(f"IMC <b>{m['imc']}</b> ({m['imc_categoria']})")
    if "gasto_diario" in m:
        chips.append(f"Gasto diario <b>{m['gasto_diario']}</b> kcal · basal {m['metabolismo_basal']}")
    if "fc_max" in m:
        chips.append(f"FC máx. <b>{m['fc_max']}</b> · zona 2 {m['zona2'][0]}-{m['zona2'][1]} lpm")
    if "proteina_g" in m:
        chips.append(f"Proteína {m['proteina_g'][0]}-{m['proteina_g'][1]} g/día · agua ~{m['agua_l']} L")
    names = {"pasos": "Pasos", "sueno_h": "Sueño (h)", "fc_reposo": "Pulso en reposo", "hrv_ms": "VFC (ms)", "animo": "Ánimo", "estres": "Estrés", "energia": "Energía", "peso_kg": "Peso"}
    for key, label in names.items():
        if key in t and t[key]["7d"] is not None:
            change = t[key]["cambio"]
            arrow = "" if change is None else (" ▲" if change > 0 else " ▼" if change < 0 else "")
            chips.append(f"{label}: <b>{t[key]['7d']}</b> (7 días){arrow}")
    if chips:
        parts.append("<p>" + "<br>".join(chips) + "</p>")
    if rep:
        parts.append(f"<p>{escape(str(rep.get('resumen', '')))}</p>")
        if rep.get("alertas"):
            parts.append("<h3 style='color:#FF453A'>Consulte con un médico</h3><ul>" + "".join(f"<li>{escape(str(a))}</li>" for a in rep["alertas"]) + "</ul>")
        if rep.get("recomendaciones"):
            parts.append("<h3>Qué hacer</h3><ol>" + "".join(
                f"<li><b>{escape(str(r.get('accion', '')))}</b><br><span style='color:#8E8E93'>{escape(str(r.get('por_que', '')))}</span></li>"
                for r in rep["recomendaciones"]
            ) + "</ol>")  # fmt: skip
        if rep.get("rutina"):
            parts.append("<h3>Rutina de la semana</h3><ul>" + "".join(
                f"<li>{escape(str(r.get('dia', '')))}: {escape(str(r.get('actividad', '')))} ({escape(str(r.get('minutos', '')))} min)</li>"
                for r in rep["rutina"]
            ) + "</ul>")  # fmt: skip
        if rep.get("metas"):
            parts.append("<h3>Metas</h3><ul>" + "".join(
                f"<li>{escape(str(g.get('metrica', '')))}: {escape(str(g.get('objetivo', '')))} ({escape(str(g.get('plazo', '')))})</li>" for g in rep["metas"]
            ) + "</ul>")  # fmt: skip
    parts.append("<p style='color:#8E8E93'>Orientación basada en guías (OMS, AASM…); no sustituye a su médico.</p>")
    return "".join(parts)


class HealthWindow(QWidget):
    def __init__(
        self,
        health: Health,
        analyze: Callable[[], dict[str, Any]],
        folder: Callable[[], str],
        set_folder: Callable[[str], None],
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("salud")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Sergio · Mi salud")
        self.health, self._analyze, self._folder, self._set_folder = health, analyze, folder, set_folder
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        # summary
        page = QWidget()
        v = QVBoxLayout(page)
        self.summary = QTextBrowser()
        self.status = QLabel("")
        self.status.setObjectName("muted")
        go = QPushButton("Analizar ahora")
        go.clicked.connect(self.run_analysis)
        v.addWidget(self.summary)
        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(go)
        v.addLayout(row)
        self.tabs.addTab(page, "Resumen")
        # today
        self.today_page = QWidget()
        self.today_form = QFormLayout(self.today_page)
        self.today_fields: dict[str, QLineEdit] = {}
        self.tabs.addTab(self.today_page, "Hoy")
        # questionnaire
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        qpage = QWidget()
        qpage.setObjectName("salud")
        self.q_form = QFormLayout(qpage)
        self.q_fields: dict[str, Any] = {}
        for q in QUESTIONS:
            if q.kind == "choice":
                field = QComboBox()
                field.addItems(["—", *q.options])
                current = str(health.answers.get(q.key, ""))
                if current in q.options:
                    field.setCurrentText(current)
            else:
                field = QLineEdit(str(health.answers.get(q.key, "")))
                field.setPlaceholderText(q.unit)
            label = q.text + (" (privado)" if q.private else "")
            self.q_form.addRow(QLabel(label), field)
            self.q_fields[q.key] = field
        save_q = QPushButton("Guardar cuestionario")
        save_q.clicked.connect(self._save_questionnaire)
        self.q_form.addRow(save_q)
        scroll.setWidget(qpage)
        self.tabs.addTab(scroll, "Cuestionario")
        # devices
        dpage = QWidget()
        dv = QVBoxLayout(dpage)
        help_text = QTextBrowser()
        help_text.setHtml(DEVICE_HELP)
        self.folder_label = QLabel("")
        self.folder_label.setWordWrap(True)
        row = QHBoxLayout()
        pick = QPushButton("Elegir carpeta de sincronización")
        pick.setObjectName("plain")
        pick.clicked.connect(self._pick_folder)
        imp = QPushButton("Importar un archivo…")
        imp.clicked.connect(self._import)
        row.addWidget(pick)
        row.addWidget(imp)
        dv.addWidget(help_text)
        dv.addWidget(self.folder_label)
        dv.addLayout(row)
        self.tabs.addTab(dpage, "Reloj y apps")
        self.resize(660, 720)
        self.refresh()

    def refresh(self) -> None:
        self.summary.setHtml(report_html(self.health))
        sources = ", ".join(self.health.sources) or "ninguna aún"
        self.folder_label.setText(f"Carpeta: {self._folder() or 'sin elegir'} · Fuentes: {sources}")
        while self.today_form.rowCount():
            self.today_form.removeRow(0)
        self.today_fields = {}
        today = date.today().isoformat()
        have = self.health.days.get(today, {})
        intro = QLabel("Lo que su reloj ya dio no se pregunta." if have else "¿Cómo fue su día?")
        intro.setObjectName("muted")
        self.today_form.addRow(intro)
        for key, label, unit in DAILY:
            field = QLineEdit("" if key not in have else f"{have[key]:g}")
            field.setPlaceholderText(unit)
            self.today_form.addRow(QLabel(label), field)
            self.today_fields[key] = field
        save = QPushButton("Guardar el día")
        save.clicked.connect(self._save_today)
        self.today_form.addRow(save)

    def _save_today(self) -> None:
        values = {k: f.text() for k, f in self.today_fields.items() if f.text().strip()}
        self.health.log(date.today().isoformat(), values)
        self.status.setText("Día guardado.")
        self.refresh()
        self.tabs.setCurrentIndex(0)

    def _save_questionnaire(self) -> None:
        answers = {}
        for key, field in self.q_fields.items():
            value = field.currentText() if isinstance(field, QComboBox) else field.text()
            if value and value != "—":
                answers[key] = value
        self.health.answer(answers)
        missing = self.health.missing_questions()
        self.status.setText("Cuestionario guardado." + (f" Faltan: {', '.join(q.text for q in missing[:3])}" if missing else " Analizando…"))
        self.tabs.setCurrentIndex(0)
        if not missing:
            self.run_analysis()
        else:
            self.refresh()

    def run_analysis(self) -> None:
        self.status.setText("Analizando todos sus datos en conjunto…")
        in_background(self._analyze, self._analysed)

    def _analysed(self, result: Any) -> None:
        if isinstance(result, Exception):
            self.status.setText(f"No pude analizar: {result}")
            return
        self.status.setText("Análisis actualizado.")
        self.refresh()

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de sincronización")
        if folder:
            self._set_folder(folder)
            self.refresh()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Exportación de su reloj o app", "", "Datos de salud (*.zip *.xml *.csv)")
        if path:
            days = self.health.import_file(Path(path))
            self.status.setText(f"Importados {days} días." if days else "No reconocí datos en ese archivo.")
            self.refresh()

    def open(self, tab: int = 0) -> None:
        self.refresh()
        self.tabs.setCurrentIndex(tab)
        self.show()
        self.raise_()
        self.activateWindow()


class DailyCard(QWidget):
    """The daily questions (only what no device answered), small and quick."""

    def __init__(self, health: Health, on_saved: Callable[[], None]) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setObjectName("salud")
        self.setStyleSheet(STYLE)
        self.health, self.on_saved = health, on_saved
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        head = QLabel("SALUD · SU DÍA")
        head.setObjectName("muted")
        head.setFont(_font(9, True))
        lay.addWidget(head)
        form = QFormLayout()
        self.fields: dict[str, QLineEdit] = {}
        today = date.today().isoformat()
        for key, label, unit in health.to_ask_today(today):
            field = QLineEdit()
            field.setPlaceholderText(unit)
            form.addRow(QLabel(label), field)
            self.fields[key] = field
        lay.addLayout(form)
        row = QHBoxLayout()
        save, later = QPushButton("Guardar"), QPushButton("Después")
        later.setObjectName("plain")
        save.clicked.connect(self._save)
        later.clicked.connect(self.close)
        row.addWidget(later)
        row.addWidget(save)
        lay.addLayout(row)
        self.resize(380, 120 + 34 * len(self.fields))
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 20, geo.bottom() - self.height() - 20)

    def _save(self) -> None:
        values = {k: f.text() for k, f in self.fields.items() if f.text().strip()}
        self.health.log(date.today().isoformat(), values)
        self.close()
        self.on_saved()


__all__ = ["DailyCard", "HealthWindow", "report_html"]

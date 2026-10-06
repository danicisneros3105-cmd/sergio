"""How each mental-gym exercise is done: three short steps and a looping
animated example (a "mini video" drawn live), shown during the 15 s intro.

``STEPS`` is plain data; ``paint_demo`` draws frame *t* (seconds) of the
example for one exercise inside a rectangle. Each example loops every
``LOOP`` seconds: the situation appears, a ghost finger/cursor answers and
the right answer lights up green.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

LOOP = 5.5

TEXT = QColor(245, 245, 247)
MUTED = QColor(142, 142, 147)
ACCENT = QColor(10, 132, 255)
GOOD = QColor(48, 209, 88)
BAD = QColor(255, 69, 58)
PANEL = QColor(44, 44, 46)
INK = {"ROJO": QColor("#ff3b30"), "AZUL": QColor("#0a84ff"), "VERDE": QColor("#34c759"), "AMARILLO": QColor("#ffcc00")}

STEPS: dict[str, tuple[str, ...]] = {
    "stroop": (
        "Aparece una palabra de color pintada con OTRA tinta.",
        "Ignora lo que dice: mira el COLOR de las letras.",
        "Pulsa 1-4 (o clic) en el color de la tinta. Rápido y sin fallar.",
    ),
    "calculo": (
        "Sale una operación (suma, resta, multiplicación...).",
        "Resuélvela de cabeza, sin papel.",
        "Escribe el número y pulsa Enter.",
    ),
    "simetria": (
        "Sale un dibujo de cuadros.",
        "Imagina un espejo en la línea del centro: ¿la mitad izquierda es igual a la derecha?",
        "S = simétrico, A = asimétrico.",
    ),
    "nback": (
        "Cada 2-3 s se ilumina un cuadro y suena/se ve una letra.",
        "Compara con lo que salió N pasos antes (empieza en N = 2).",
        "A si el LUGAR se repite, L si la LETRA se repite. Si aciertas, sube N.",
    ),
    "relacional": (
        "Lees unas relaciones: «A es mayor que B», «B es mayor que C».",
        "Encadénalas en tu cabeza.",
        "Decide si la conclusión es Verdadera (V) o Falsa (F).",
    ),
    "rotacion": (
        "Arriba hay una figura de cubos.",
        "Gírala mentalmente: una de las cuatro de abajo es la misma, solo girada.",
        "Las otras son su reflejo en un espejo. Pulsa 1-4.",
    ),
    "listas": (
        "Salen palabras una por una: memorízalas.",
        "Cuando desaparecen, escríbelas AL REVÉS (de la última a la primera).",
        "Separadas por espacios y Enter. Si aciertas, la lista crece.",
    ),
    "matrices": (
        "Una cuadrícula de 3×3 con una pieza que falta.",
        "Busca la regla en filas y columnas (forma, cantidad, color, giro).",
        "Elige la pieza que completa el patrón (1-6).",
    ),
    "palabras": (
        "Te piden una categoría con una regla: «animales que empiecen con P».",
        "Escribe todas las que puedas, una por una.",
        "Enter tras cada palabra. Vale lo que cumpla la regla.",
    ),
    "coordinacion": (
        "Se encienden cuadros en orden: D F (izquierda) y J K (derecha).",
        "Mira la secuencia completa.",
        "Repítela con las teclas; dos cuadros a la vez = las dos teclas juntas.",
    ),
    "repaso": (
        "Sale una pregunta.",
        "Responde de memoria antes de pensar en mirar nada.",
        "Si fallas ves la respuesta y vuelve pronto; si aciertas vuelve en días.",
    ),
    "inductivo": (
        "Sale una serie («2 4 8 16 ?»), un grupo («¿cuál no encaja?») o una analogía.",
        "Busca la REGLA que conecta todo: suma, multiplica, alterna, categoría…",
        "Elige la respuesta con 1-4. Al responder verás la regla.",
    ),
    "alternancia": (
        "Aparece un número ARRIBA (azul) o ABAJO (naranja).",
        "Arriba: ¿par (D) o impar (K)? Abajo: ¿menor (D) o mayor (K) que 5?",
        "La regla cambia según dónde salga: responde rápido sin confundirte.",
    ),
    "doble": (
        "Mira el CENTRO: un destello muy corto muestra un auto o un camión, y un auto AFUERA.",
        "Responde qué había en el centro: 1 = auto, 2 = camión.",
        "Luego haz clic donde estaba el auto de afuera. Si aciertas, el destello se acorta.",
    ),
    "pausa": (
        "Ponte de pie.",
        "Sentadillas o saltos de tijera a buen ritmo, sin parar.",
        "60 segundos. Al terminar pulsa Enter.",
    ),
    "prueba": (
        "Arriba está la clave: cada símbolo tiene un número del 1 al 9.",
        "Sale un símbolo abajo: busca su número en la clave.",
        "Pulsa ese número; todos los que puedas en 90 s.",
    ),
}


def _font(size: float, weight: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    f = QFont(["Segoe UI Variable Display", "SF Pro Display", "Segoe UI"])
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def _key(p: QPainter, rect: QRectF, label: str, on: bool, colour: QColor = ACCENT) -> None:
    p.setPen(QPen(colour if on else QColor(90, 90, 96), 2))
    p.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 90) if on else PANEL)
    p.drawRoundedRect(rect, 9, 9)
    p.setFont(_font(11))
    p.setPen(TEXT)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


def _finger(p: QPainter, at: QPointF, pressing: bool) -> None:
    """A ghost fingertip/cursor showing what to press."""
    r = 9 if pressing else 12
    p.setPen(QPen(QColor(255, 255, 255, 220), 2))
    p.setBrush(QColor(255, 255, 255, 70 if pressing else 35))
    p.drawEllipse(at, r, r)


def _tick(p: QPainter, rect: QRectF, ok: bool = True) -> None:
    p.setFont(_font(26, QFont.Weight.Black))
    p.setPen(GOOD if ok else BAD)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "✓" if ok else "✗")


def _text(p: QPainter, rect: QRectF, text: str, size: float = 14, colour: QColor = TEXT) -> None:
    p.setFont(_font(size))
    p.setPen(colour)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)


def _typed(text: str, t: float, start: float, speed: float = 0.18) -> str:
    return text[: max(0, int((t - start) / speed))]


def paint_demo(p: QPainter, rect: QRectF, kind: str, t: float) -> None:
    """Frame *t* of the looping example for *kind*."""
    t %= LOOP
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 30), 1))
    p.setBrush(QColor(18, 18, 20))
    p.drawRoundedRect(rect, 16, 16)
    _text(p, QRectF(rect.left(), rect.top() + 6, rect.width(), 20), "EJEMPLO", 9, MUTED)
    inner = rect.adjusted(14, 30, -14, -14)
    p.setClipRect(rect.adjusted(2, 2, -2, -2))
    painter = DEMOS.get(kind)
    if painter is not None:
        painter(p, inner, t)
    p.restore()


def _stroop(p: QPainter, r: QRectF, t: float) -> None:
    p.setFont(_font(30, QFont.Weight.Black))
    p.setPen(INK["AZUL"])
    p.drawText(QRectF(r.left(), r.top(), r.width(), r.height() * 0.45), Qt.AlignmentFlag.AlignCenter, "ROJO")
    _text(p, QRectF(r.left(), r.top() + r.height() * 0.4, r.width(), 18), "la tinta es AZUL", 9, MUTED)
    w = (r.width() - 30) / 4
    keys = [QRectF(r.left() + i * (w + 10), r.bottom() - 46, w, 40) for i in range(4)]
    press = t > 2.4
    for i, (name, rect) in enumerate(zip(INK, keys)):
        _key(p, rect, str(i + 1), press and i == 1, GOOD)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK[name])
        p.drawEllipse(QPointF(rect.left() + 12, rect.center().y()), 5, 5)
    target = keys[1].center()
    start = QPointF(r.center().x(), r.center().y())
    k = min(1.0, max(0.0, (t - 1.2) / 1.2))
    _finger(p, start + (target - start) * k, press)
    if press:
        _tick(p, QRectF(r.right() - 50, r.top(), 50, 50))


def _calculo(p: QPainter, r: QRectF, t: float) -> None:
    _text(p, QRectF(r.left(), r.top(), r.width(), r.height() * 0.45), "7 × 8 = ?", 26)
    box = QRectF(r.center().x() - 70, r.bottom() - 60, 140, 40)
    p.setPen(QPen(ACCENT, 2))
    p.setBrush(PANEL)
    p.drawRoundedRect(box, 18, 18)
    _text(p, box, _typed("56", t, 1.6, 0.4), 16)
    if t > 3.0:
        _text(p, QRectF(box.right() + 6, box.top(), 70, 40), "Enter", 10, MUTED)
        _tick(p, QRectF(r.right() - 50, r.top(), 50, 50))


def _simetria(p: QPainter, r: QRectF, t: float) -> None:
    grid = ((1, 0, 0, 1), (0, 1, 1, 0), (1, 1, 1, 1), (0, 1, 1, 0))
    size = min(r.width(), r.height() - 60) / 4.6
    x0 = r.center().x() - 2 * size
    y0 = r.top() + 4
    for y, row in enumerate(grid):
        for x, on in enumerate(row):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ACCENT if on else PANEL)
            p.drawRoundedRect(QRectF(x0 + x * size + 2, y0 + y * size + 2, size - 4, size - 4), 4, 4)
    sweep = min(1.0, t / 1.8)
    p.setPen(QPen(QColor(255, 214, 10), 2, Qt.PenStyle.DashLine))
    p.drawLine(QPointF(r.center().x(), y0), QPointF(r.center().x(), y0 + 4 * size * sweep))
    keys = [QRectF(r.center().x() - 110, r.bottom() - 42, 100, 38), QRectF(r.center().x() + 10, r.bottom() - 42, 100, 38)]
    press = t > 2.8
    _key(p, keys[0], "S simétrico", press, GOOD)
    _key(p, keys[1], "A asimétrico", False)
    if press:
        _tick(p, QRectF(r.right() - 50, r.top(), 50, 50))


def _nback(p: QPainter, r: QRectF, t: float) -> None:
    seq = (("K", 0), ("B", 4), ("K", 0))  # step 3 repeats the place AND letter of step 1
    step = min(2, int(t / 1.6))
    cell = min(r.width(), r.height() - 70) / 3.2
    x0 = r.center().x() - 1.5 * cell
    y0 = r.top()
    for i in range(9):
        lit = i == seq[step][1]
        p.setPen(QPen(QColor(90, 90, 96), 1))
        p.setBrush(ACCENT if lit else PANEL)
        p.drawRoundedRect(QRectF(x0 + (i % 3) * cell + 3, y0 + (i // 3) * cell + 3, cell - 6, cell - 6), 6, 6)
    _text(p, QRectF(r.left(), y0 + 3 * cell, r.width(), 24), f"paso {step + 1}: letra «{seq[step][0]}»", 11)
    if step == 2:
        _text(p, QRectF(r.left(), y0 + 3 * cell + 20, r.width(), 20), "igual que hace 2 pasos →", 9, MUTED)
        keys = [QRectF(r.center().x() - 110, r.bottom() - 38, 100, 34), QRectF(r.center().x() + 10, r.bottom() - 38, 100, 34)]
        press = t % 1.6 > 0.6
        _key(p, keys[0], "A lugar", press, GOOD)
        _key(p, keys[1], "L letra", press, GOOD)


def _relacional(p: QPainter, r: QRectF, t: float) -> None:
    lines = ("Ana es mayor que Beto.", "Beto es mayor que Carla.", "¿Ana es mayor que Carla?")
    for i, line in enumerate(lines):
        if t > i * 0.8:
            _text(p, QRectF(r.left(), r.top() + i * 30, r.width(), 28), line, 12, TEXT if i < 2 else QColor(255, 214, 10))
    if t > 2.6:
        _text(p, QRectF(r.left(), r.top() + 96, r.width(), 22), "Ana > Beto > Carla", 11, MUTED)
    keys = [QRectF(r.center().x() - 110, r.bottom() - 42, 100, 38), QRectF(r.center().x() + 10, r.bottom() - 42, 100, 38)]
    press = t > 3.6
    _key(p, keys[0], "V verdad", press, GOOD)
    _key(p, keys[1], "F falso", False)


def _blocks(p: QPainter, centre: QPointF, size: float, angle: float, colour: QColor, mirror: bool = False) -> None:
    shape = ((0, 0), (1, 0), (2, 0), (2, 1))  # an L of four squares
    c, s = math.cos(angle), math.sin(angle)
    p.setPen(QPen(QColor(20, 20, 22), 1))
    p.setBrush(colour)
    for x, y in shape:
        x = 2 - x if mirror else x
        px, py = (x - 1) * size, (y - 0.5) * size
        rx, ry = px * c - py * s, px * s + py * c
        p.drawRect(QRectF(centre.x() + rx - size / 2, centre.y() + ry - size / 2, size, size))


def _rotacion(p: QPainter, r: QRectF, t: float) -> None:
    size = min(r.width() / 16, r.height() / 12)
    angle = min(1.0, t / 2.2) * math.pi / 2
    _blocks(p, QPointF(r.center().x(), r.top() + r.height() * 0.22), size * 1.3, angle, ACCENT)
    w = r.width() / 4
    for i in range(4):
        centre = QPointF(r.left() + w * (i + 0.5), r.bottom() - size * 3.2)
        right = i == 2
        _blocks(p, centre, size, math.pi / 2 if right else (i * math.pi / 2), GOOD if (right and t > 2.8) else MUTED, mirror=not right)
        _text(p, QRectF(centre.x() - 15, r.bottom() - 20, 30, 18), str(i + 1), 10, MUTED)
    if t > 2.8:
        _text(p, QRectF(r.left(), r.top() + r.height() * 0.44, r.width(), 36), "la 3 es la misma girada; las otras son reflejos", 9, MUTED)


def _listas(p: QPainter, r: QRectF, t: float) -> None:
    words = ("sol", "mar", "pan")
    if t < 2.4:
        _text(p, QRectF(r.left(), r.top(), r.width(), r.height() * 0.6), words[min(2, int(t / 0.8))].upper(), 28)
        _text(p, QRectF(r.left(), r.bottom() - 30, r.width(), 20), "memoriza…", 10, MUTED)
        return
    _text(p, QRectF(r.left(), r.top(), r.width(), 30), "Ahora al revés", 13)
    box = QRectF(r.center().x() - 110, r.bottom() - 60, 220, 40)
    p.setPen(QPen(ACCENT, 2))
    p.setBrush(PANEL)
    p.drawRoundedRect(box, 18, 18)
    _text(p, box, _typed("pan mar sol", t, 2.6, 0.15), 15)
    if t > 4.4:
        _tick(p, QRectF(r.right() - 50, r.top(), 50, 50))


def _matrices(p: QPainter, r: QRectF, t: float) -> None:
    cell = min(r.width() * 0.6, r.height() - 50) / 3
    x0 = r.left() + 6
    for row in range(3):
        for col in range(3):
            rect = QRectF(x0 + col * cell, r.top() + row * cell, cell - 4, cell - 4)
            p.setPen(QPen(QColor(90, 90, 96), 1))
            p.setBrush(PANEL)
            p.drawRoundedRect(rect, 5, 5)
            if row == 2 and col == 2:
                _text(p, rect, "?" if t < 3.4 else "", 18, QColor(255, 214, 10))
                if t >= 3.4:
                    _dots(p, rect, 3, GOOD)
                continue
            _dots(p, rect, col + 1, TEXT)
    opts = QRectF(x0 + 3 * cell + 14, r.top(), r.right() - x0 - 3 * cell - 14, r.height() - 50)
    for i, n in enumerate((1, 3, 2)):
        rect = QRectF(opts.left(), opts.top() + i * (cell * 0.9), cell * 0.8, cell * 0.8)
        lit = n == 3 and t > 2.6
        p.setPen(QPen(GOOD if lit else QColor(90, 90, 96), 2))
        p.setBrush(PANEL)
        p.drawRoundedRect(rect, 5, 5)
        _dots(p, rect, n, GOOD if lit else MUTED)
    _text(p, QRectF(r.left(), r.bottom() - 40, r.width(), 36), "regla: cada fila suma un punto (1, 2, 3)", 9, MUTED)


def _dots(p: QPainter, rect: QRectF, n: int, colour: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(colour)
    for i in range(n):
        x = rect.left() + rect.width() * (i + 1) / (n + 1)
        p.drawEllipse(QPointF(x, rect.center().y()), rect.width() * 0.09, rect.width() * 0.09)


def _palabras(p: QPainter, r: QRectF, t: float) -> None:
    _text(p, QRectF(r.left(), r.top(), r.width(), 40), "Animales que empiecen con P", 13)
    done = []
    for i, word in enumerate(("perro", "pato", "puma")):
        start = 0.8 + i * 1.4
        if t > start + 1.0:
            done.append(word)
    _text(p, QRectF(r.left(), r.top() + 50, r.width(), 30), "  ✓ ".join(done) + ("  ✓" if done else ""), 12, GOOD)
    current = next((w for i, w in enumerate(("perro", "pato", "puma")) if 0.8 + i * 1.4 <= t < 1.8 + i * 1.4), "")
    box = QRectF(r.center().x() - 90, r.bottom() - 50, 180, 38)
    p.setPen(QPen(ACCENT, 2))
    p.setBrush(PANEL)
    p.drawRoundedRect(box, 18, 18)
    if current:
        start = 0.8 + ("perro", "pato", "puma").index(current) * 1.4
        _text(p, box, _typed(current, t, start, 0.15), 14)


def _coordinacion(p: QPainter, r: QRectF, t: float) -> None:
    seq = ("d", "k", ("f", "j"))
    w = (r.width() - 40) / 4
    pads = {k: QRectF(r.left() + i * (w + 13), r.top() + 20, w, w * 0.8) for i, k in enumerate("dfjk")}
    showing = t < 3.0
    step = int(t / 1.0) if showing else int((t - 3.0) / 0.8)
    current = seq[step] if step < len(seq) else ()
    lit = set(current if isinstance(current, tuple) else (current,))
    for key, rect in pads.items():
        _key(p, rect, key.upper(), key in lit, ACCENT if showing else GOOD)
    _text(p, QRectF(r.left(), r.bottom() - 50, r.width(), 40),
          "mira la secuencia…" if showing else "ahora repítela (F+J juntas)", 11, MUTED)


def _repaso(p: QPainter, r: QRectF, t: float) -> None:
    _text(p, QRectF(r.left(), r.top(), r.width(), 50), "¿Cuál es la capital de Japón?", 13)
    box = QRectF(r.center().x() - 90, r.top() + 70, 180, 38)
    p.setPen(QPen(ACCENT, 2))
    p.setBrush(PANEL)
    p.drawRoundedRect(box, 18, 18)
    _text(p, box, _typed("Tokio", t, 1.0, 0.2), 14)
    if t > 2.6:
        _text(p, QRectF(r.left(), r.bottom() - 60, r.width(), 24), "¡Correcto!", 14, GOOD)
        _text(p, QRectF(r.left(), r.bottom() - 34, r.width(), 22), "vuelve en 3 días (si fallas, en minutos)", 10, MUTED)


def _pausa(p: QPainter, r: QRectF, t: float) -> None:
    """A stick figure doing squats."""
    k = (1 - math.cos(t * 2 * math.pi / 1.4)) / 2  # 0 standing .. 1 down
    cx, ground = r.center().x(), r.bottom() - 30
    hip = QPointF(cx, ground - 110 + 45 * k)
    knee = QPointF(cx + 26 * k, ground - 55 + 10 * k)
    head = QPointF(cx - 10 * k, hip.y() - 85 + 10 * k)
    pen = QPen(TEXT, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(cx - 18, ground), knee)
    p.drawLine(knee, hip)
    p.drawLine(hip, QPointF(head.x(), head.y() + 16))
    arms = QPointF(head.x() + 45 * k + 10, head.y() + 40)
    p.drawLine(QPointF(head.x(), head.y() + 30), arms)
    p.setBrush(TEXT)
    p.drawEllipse(head, 13, 13)
    p.setPen(QPen(MUTED, 2))
    p.drawLine(QPointF(r.left() + 20, ground), QPointF(r.right() - 20, ground))
    _text(p, QRectF(r.left(), r.top(), r.width(), 22), "baja… y sube, a buen ritmo", 11, MUTED)


def _prueba(p: QPainter, r: QRectF, t: float) -> None:
    glyphs = ("◆", "▲", "●", "■", "✚")
    w = r.width() / len(glyphs)
    for i, g in enumerate(glyphs):
        cell = QRectF(r.left() + i * w, r.top(), w - 4, 50)
        lit = i == 1 and t > 1.6
        p.setPen(QPen(GOOD if lit else QColor(90, 90, 96), 1.5))
        p.setBrush(PANEL)
        p.drawRoundedRect(cell, 6, 6)
        _text(p, QRectF(cell.left(), cell.top(), cell.width(), 30), g, 14)
        _text(p, QRectF(cell.left(), cell.top() + 26, cell.width(), 22), str(i + 1), 11, MUTED)
    _text(p, QRectF(r.left(), r.top() + 70, r.width(), 50), "▲", 30, QColor(255, 214, 10))
    if t > 2.6:
        _key(p, QRectF(r.center().x() - 30, r.bottom() - 46, 60, 40), "2", True, GOOD)


def _inductivo(p: QPainter, r: QRectF, t: float) -> None:
    _text(p, QRectF(r.left(), r.top(), r.width(), r.height() * 0.38), "2   4   8   16   ?", 24)
    if t > 1.4:
        _text(p, QRectF(r.left(), r.top() + r.height() * 0.36, r.width(), 20), "regla: × 2", 11, QColor(255, 214, 10))
    w = (r.width() - 30) / 4
    opts = ("24", "32", "18", "30")
    keys = [QRectF(r.left() + i * (w + 10), r.bottom() - 46, w, 40) for i in range(4)]
    press = t > 2.8
    for i, (label, rect) in enumerate(zip(opts, keys)):
        _key(p, rect, f"{i + 1}  {label}", press and i == 1, GOOD)
    k = min(1.0, max(0.0, (t - 1.8) / 1.0))
    start = QPointF(r.center().x(), r.center().y())
    _finger(p, start + (keys[1].center() - start) * k, press)
    if press:
        _tick(p, QRectF(r.right() - 50, r.top(), 50, 50))


def _alternancia(p: QPainter, r: QRectF, t: float) -> None:
    top = QRectF(r.left(), r.top(), r.width(), (r.height() - 50) / 2 - 4)
    bottom = QRectF(r.left(), top.bottom() + 8, r.width(), top.height())
    blue, orange = QColor(10, 132, 255), QColor(255, 159, 10)
    first = t < LOOP / 2
    for rect, colour, label, on in ((top, blue, "PAR · IMPAR", first), (bottom, orange, "MENOR · MAYOR que 5", not first)):
        p.setPen(QPen(colour if on else QColor(70, 70, 76), 2))
        p.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 40) if on else PANEL)
        p.drawRoundedRect(rect, 10, 10)
        _text(p, QRectF(rect.left(), rect.top() + 2, rect.width(), 16), label, 8, MUTED)
    number = "8" if first else "3"
    _text(p, top if first else bottom, number, 30)
    keys = [QRectF(r.center().x() - 110, r.bottom() - 40, 100, 36), QRectF(r.center().x() + 10, r.bottom() - 40, 100, 36)]
    phase = t % (LOOP / 2)
    press = phase > 1.4
    _key(p, keys[0], "D par / menor", press, GOOD)
    _key(p, keys[1], "K impar / mayor", False)
    if press:
        _tick(p, QRectF(r.right() - 50, r.top(), 50, 50))


def _vehicle(p: QPainter, centre: QPointF, size: float, truck: bool, colour: QColor) -> None:
    """A tiny car or truck glyph."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(colour)
    if truck:
        p.drawRoundedRect(QRectF(centre.x() - size * 0.9, centre.y() - size * 0.45, size * 1.2, size * 0.6), 2, 2)
        p.drawRoundedRect(QRectF(centre.x() + size * 0.35, centre.y() - size * 0.25, size * 0.5, size * 0.4), 2, 2)
        wheels = (-0.6, -0.1, 0.6)
    else:
        p.drawRoundedRect(QRectF(centre.x() - size * 0.7, centre.y() - size * 0.15, size * 1.4, size * 0.35), 4, 4)
        p.drawRoundedRect(QRectF(centre.x() - size * 0.35, centre.y() - size * 0.4, size * 0.7, size * 0.3), 4, 4)
        wheels = (-0.4, 0.4)
    p.setBrush(QColor(20, 20, 22))
    for w in wheels:
        p.drawEllipse(QPointF(centre.x() + size * w, centre.y() + size * 0.22), size * 0.14, size * 0.14)


def _doble(p: QPainter, r: QRectF, t: float) -> None:
    centre = QPointF(r.center().x(), r.top() + (r.height() - 50) / 2)
    radius = min(r.width(), r.height() - 50) * 0.4
    flash = 0.6 < t < 1.0
    p.setPen(QPen(QColor(70, 70, 76), 1, Qt.PenStyle.DotLine))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(centre, radius, radius)
    spot = QPointF(centre.x() + radius * math.cos(math.radians(-45)), centre.y() + radius * math.sin(math.radians(-45)))
    if flash:
        _vehicle(p, centre, 20, False, QColor(100, 210, 255))
        _vehicle(p, spot, 16, False, QColor(100, 210, 255))
    elif 1.0 <= t < 1.4:
        for i in range(40):  # the mask
            a = i * 2.39996
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(90, 90, 96))
            p.drawRect(QRectF(centre.x() + math.cos(a) * i * 2.2, centre.y() + math.sin(a) * i * 2.2, 5, 5))
    else:
        _text(p, QRectF(centre.x() - 10, centre.y() - 12, 20, 24), "+", 14, MUTED)
    if t > 1.6:
        keys = [QRectF(r.center().x() - 110, r.bottom() - 40, 100, 36), QRectF(r.center().x() + 10, r.bottom() - 40, 100, 36)]
        _key(p, keys[0], "1 auto", t > 2.3, GOOD)
        _key(p, keys[1], "2 camión", False)
    if t > 3.0:
        p.setPen(QPen(GOOD, 2))
        p.setBrush(QColor(48, 209, 88, 60))
        p.drawEllipse(spot, 16, 16)
        _finger(p, spot, t > 3.4)
    if t > 3.6:
        _tick(p, QRectF(r.right() - 50, r.top(), 50, 50))


DEMOS = {
    "inductivo": _inductivo,
    "alternancia": _alternancia,
    "doble": _doble,
    "stroop": _stroop,
    "calculo": _calculo,
    "simetria": _simetria,
    "nback": _nback,
    "relacional": _relacional,
    "rotacion": _rotacion,
    "listas": _listas,
    "matrices": _matrices,
    "palabras": _palabras,
    "coordinacion": _coordinacion,
    "repaso": _repaso,
    "pausa": _pausa,
    "prueba": _prueba,
}

__all__ = ["DEMOS", "LOOP", "STEPS", "paint_demo"]

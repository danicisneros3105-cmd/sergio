"""Mental gym: the ten exercises, as pure logic (no Qt, easy to test).

Every exercise makes its items with a seeded random generator and knows the
right answer, so the window (``gym.py``) only shows and collects answers.

* Interferencia tipo Stroop — 15 en 1,5 min: press the INK colour.
* Cálculo mental aleatorio — 10 en 1,5 min.
* Detección de patrones asimétricos — 20 en 1,5 min: symmetric or not.
* Dual N-Back adaptativo (micro) — 1 bloque continuo de 2 min.
* Marcos relacionales lógicos — 3 problemas en 2 min.
* Rotación mental de objetos — 5 figuras 3D en 2 min.
* Retención de listas invertidas — 4 secuencias en 2 min.
* Matrices progresivas — 2 matrices en 2 min.
* Asociación de palabras restringida — 3 desafíos en 2 min.
* Secuencias de coordinación — 5 patrones en 2 min (both hands).
"""

from __future__ import annotations

import itertools
import random
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Exercise:
    kind: str
    title: str
    items: int
    seconds: float
    how: str  # instructions shown (and said) before starting


EXERCISES: tuple[Exercise, ...] = (
    Exercise(
        "stroop",
        "Interferencia tipo Stroop",
        15,
        90,
        "Elige el COLOR DE LA TINTA, no lo que dice la palabra. Teclas 1 a 4.",
    ),
    Exercise(
        "calculo",
        "Cálculo mental aleatorio",
        10,
        90,
        "Resuelve de cabeza y escribe el resultado. Enter para responder.",
    ),
    Exercise(
        "simetria",
        "Detección de patrones asimétricos",
        20,
        90,
        "¿El dibujo es simétrico de izquierda a derecha? S = simétrico, A = asimétrico.",
    ),
    Exercise(
        "nback",
        "Dual N-Back adaptativo",
        1,
        120,
        "Cada paso muestra un cuadro y una letra. Pulsa A si la POSICIÓN es la "
        "de hace N pasos y L si la LETRA es la de hace N pasos.",
    ),
    Exercise(
        "relacional",
        "Marcos relacionales lógicos",
        3,
        120,
        "Lee las relaciones y decide si la conclusión es verdadera (V) o falsa (F).",
    ),
    Exercise(
        "rotacion",
        "Rotación mental de objetos",
        5,
        120,
        "¿Cuál de las cuatro piezas es la misma figura, solo girada? Teclas 1 a 4. "
        "Las demás están reflejadas como en un espejo.",
    ),
    Exercise(
        "listas",
        "Retención de listas invertidas",
        4,
        120,
        "Memoriza la lista y escríbela AL REVÉS, del último al primero.",
    ),
    Exercise(
        "matrices",
        "Matrices progresivas",
        2,
        120,
        "Descubre las reglas de filas y columnas y elige la pieza que falta (1 a 6).",
    ),
    Exercise(
        "palabras",
        "Asociación de palabras restringida",
        3,
        120,
        "Escribe palabras de la categoría que cumplan la regla. Enter tras cada una.",
    ),
    Exercise(
        "coordinacion",
        "Secuencias de coordinación",
        5,
        120,
        "Mira la secuencia y repítela con D F (mano izquierda) y J K (mano derecha). "
        "Dos cuadros a la vez = pulsa las dos teclas juntas.",
    ),
)
# Two more, the ones with the strongest evidence of all (for learning and
# for an immediate boost), though neither is an "IQ trainer":
EXERCISES = EXERCISES + (
    Exercise(
        "repaso",
        "Repaso espaciado",
        6,
        120,
        "Responde de memoria; si fallas verás la respuesta y volverá pronto. "
        "Lo que aciertas vuelve cada vez más tarde (1, 3, 7, 16 días).",
    ),
    Exercise(
        "pausa",
        "Pausa activa: 60 segundos intensos",
        1,
        60,
        "Ponte de pie: sentadillas o saltos de tijera a buen ritmo durante 60 "
        "segundos. Al terminar pulsa Enter.",
    ),
)

# Why each exercise is here: what the best studies found (shown before it).
EVIDENCE: dict[str, str] = {
    "nback": "Dual n-back: el más estudiado para la inteligencia fluida; "
    "metaanálisis g = 0,24 (Au 2015), casi 0 frente a controles activos.",
    "matrices": "Matrices: practicar el formato de los tests de CI sube 0,23–0,42 DE "
    "en ellos (Scharfen 2018), aunque no la inteligencia general.",
    "rotacion": "Rotación mental: el entrenamiento espacial mejora y transfiere a otras "
    "tareas espaciales, g = 0,47 y duradero (Uttal 2013).",
    "repaso": "Recuperación activa espaciada: la técnica de aprendizaje con más "
    "evidencia, g = 0,61 (Adesope 2017); espaciar suma más (g ≈ 0,7).",
    "pausa": "Ejercicio breve: mejora la función ejecutiva (inhibición, memoria de "
    "trabajo) en los minutos siguientes; efecto pequeño y constante.",
    "relacional": "Razonamiento relacional: estudios pequeños con mejoras en CI; "
    "evidencia aún débil.",
    "listas": "Memoria de trabajo: mejora lo entrenado; la transferencia lejana es "
    "mínima (Melby-Lervåg 2016).",
    "stroop": "Control inhibitorio: mejora la tarea; poca transferencia (Sala y Gobet 2019).",
    "calculo": "Cálculo mental: fluidez numérica, se transfiere a cálculos similares.",
    "simetria": "Velocidad perceptiva: mejora lo entrenado.",
    "palabras": "Fluidez verbal: mejora lo entrenado.",
    "coordinacion": "Coordinación bimanual y secuencias motoras: mejora lo entrenado.",
    "prueba": "Medida, no entrenamiento: dice si lo demás te mejora de verdad.",
}

# Every 12 minutes one exercise; the best-evidenced come twice as often.
SCHEDULE = (
    "nback", "matrices", "repaso", "rotacion", "relacional", "nback",
    "matrices", "pausa", "rotacion", "repaso", "listas", "stroop",
    "calculo", "simetria", "palabras", "coordinacion",
)  # fmt: skip

# Not trained: a standard processing-speed test (like WAIS's Digit Symbol
# Substitution) taken once a day to measure whether the training carries
# over to something it never practised (far transfer).
PROBE = Exercise(
    "prueba",
    "Prueba de control: velocidad de procesamiento",
    200,  # as many as you can: the score is how many in 90 s
    90,
    "Arriba está la clave: cada símbolo tiene un número. Cuando aparezca un "
    "símbolo, pulsa su número (1 a 9) lo más rápido que puedas sin "
    "equivocarte. No se entrena: sirve para medir si el gimnasio te mejora.",
)
BY_KIND = {e.kind: e for e in (*EXERCISES, PROBE)}


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower().strip())
    return "".join(c for c in text if not unicodedata.combining(c))


# -- 1. Stroop -----------------------------------------------------------------------
STROOP_COLORS = (
    ("ROJO", "#ff3b30"),
    ("AZUL", "#0a84ff"),
    ("VERDE", "#34c759"),
    ("AMARILLO", "#ffcc00"),
)


@dataclass
class StroopItem:
    word: str
    ink: str  # colour name (the answer)
    ink_hex: str

    def check(self, answer: str) -> bool:
        return plain(answer) == plain(self.ink)


def stroop(rng: random.Random) -> StroopItem:
    word = rng.choice(STROOP_COLORS)[0]
    if rng.random() < 0.25:  # some congruent ones keep you honest
        ink = next(c for c in STROOP_COLORS if c[0] == word)
    else:
        ink = rng.choice([c for c in STROOP_COLORS if c[0] != word])
    return StroopItem(word, ink[0], ink[1])


# -- 2. Mental arithmetic --------------------------------------------------------------
@dataclass
class MathItem:
    text: str
    answer: int

    def check(self, answer: str) -> bool:
        try:
            return int(str(answer).strip().replace(" ", "")) == self.answer
        except ValueError:
            return False


def arithmetic(rng: random.Random, level: int = 0) -> MathItem:
    kind = rng.choice(("+", "-", "x", "/", "2", "%"))
    if level < 3 and kind in ("2", "%"):
        kind = rng.choice(("+", "-", "x"))
    if kind == "+":
        a, b = rng.randint(17, 99), rng.randint(17, 99)
        return MathItem(f"{a} + {b}", a + b)
    if kind == "-":
        a, b = rng.randint(40, 150), rng.randint(11, 39)
        return MathItem(f"{a} − {b}", a - b)
    if kind == "x":
        a, b = rng.randint(6, 19), rng.randint(3, 12)
        return MathItem(f"{a} × {b}", a * b)
    if kind == "/":
        b, q = rng.randint(3, 12), rng.randint(4, 15)
        return MathItem(f"{b * q} ÷ {b}", q)
    if kind == "%":
        p, base = rng.choice((10, 20, 25, 50, 75)), rng.choice((40, 60, 80, 120, 160, 200, 240))
        return MathItem(f"{p}% de {base}", p * base // 100)
    a, b, c = rng.randint(3, 12), rng.randint(3, 9), rng.randint(5, 30)
    return MathItem(f"({a} × {b}) − {c}", a * b - c)


# -- 3. Symmetry ------------------------------------------------------------------------
@dataclass
class SymmetryItem:
    grid: list[list[int]]  # 1 = filled cell
    symmetric: bool

    def check(self, answer: str) -> bool:
        said = plain(answer)
        return (said in ("s", "si", "simetrico")) == self.symmetric


def is_symmetric(grid: list[list[int]]) -> bool:
    return all(row == row[::-1] for row in grid)


def symmetry(rng: random.Random, size: int = 6) -> SymmetryItem:
    half = size // 2
    grid = []
    for _ in range(size):
        left = [int(rng.random() < 0.45) for _ in range(half)]
        middle = [int(rng.random() < 0.45)] if size % 2 else []
        grid.append(left + middle + left[::-1])
    if rng.random() < 0.5:
        return SymmetryItem(grid, True)
    flips = rng.randint(1, 2)  # subtle: one or two cells break the mirror
    for _ in range(flips):
        r, c = rng.randrange(size), rng.randrange(size)
        grid[r][c] ^= 1
    if is_symmetric(grid):  # the flips cancelled out: break it for sure
        grid[0][0] ^= 1
        if is_symmetric(grid):
            grid[0][size - 1] ^= 1
    return SymmetryItem(grid, False)


# -- 4. Dual N-back ------------------------------------------------------------------------
NBACK_LETTERS = ("C", "H", "K", "L", "Q", "R", "S", "T")


@dataclass
class NBackTrial:
    position: int  # 0..8 in the 3x3 grid
    letter: str
    position_match: bool
    letter_match: bool


class NBack:
    """Adaptive dual n-back: every 12 trials the level goes up or down."""

    def __init__(self, rng: random.Random, level: int = 2, block: int = 12) -> None:
        self.rng = rng
        self.level = max(1, min(level, 6))
        self.block = block
        self.history: list[NBackTrial] = []
        self.results: list[tuple[bool, bool]] = []  # (position ok, letter ok)
        self.max_level = self.level
        self._block_results: list[tuple[bool, bool]] = []

    def next(self) -> NBackTrial:
        n = self.level
        back = self.history[-n] if len(self.history) >= n else None
        if back is not None and self.rng.random() < 0.3:
            position = back.position
        else:
            choices = [p for p in range(9) if back is None or p != back.position]
            position = self.rng.choice(choices)
        if back is not None and self.rng.random() < 0.3:
            letter = back.letter
        else:
            choices = [c for c in NBACK_LETTERS if back is None or c != back.letter]
            letter = self.rng.choice(choices)
        trial = NBackTrial(
            position,
            letter,
            back is not None and position == back.position,
            back is not None and letter == back.letter,
        )
        self.history.append(trial)
        return trial

    def answer(self, said_position: bool, said_letter: bool) -> tuple[bool, bool]:
        """What you pressed for the last trial; adapts the level per block."""
        trial = self.history[-1]
        result = (said_position == trial.position_match, said_letter == trial.letter_match)
        self.results.append(result)
        self._block_results.append(result)
        if len(self._block_results) >= self.block:
            hits = sum(a + b for a, b in self._block_results) / (2 * len(self._block_results))
            if hits >= 0.85 and self.level < 6:
                self.level += 1
                self.history.clear()
            elif hits < 0.6 and self.level > 1:
                self.level -= 1
                self.history.clear()
            self.max_level = max(self.max_level, self.level)
            self._block_results = []
        return result

    @property
    def accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(a + b for a, b in self.results) / (2 * len(self.results))


# -- 5. Relational frames ---------------------------------------------------------------------
NONSENSE = ("ZEP", "MUL", "KAV", "DOR", "FIS", "LUN", "PAX", "BEM", "TOK", "RIV", "GAX", "NOL")


@dataclass
class RelationalItem:
    premises: list[str]
    question: str
    answer: bool

    def check(self, answer: str) -> bool:
        said = plain(answer)
        return (said in ("v", "verdadero", "si", "s")) == self.answer


def relational(rng: random.Random, premises: int = 4) -> RelationalItem:
    names = rng.sample(NONSENSE, premises + 1)
    if rng.random() < 0.5:  # comparison: more / less
        # A chain that only goes one way, so any two can be compared by
        # following it (transitivity); the wording still mixes both ways.
        values = sorted(rng.sample(range(10, 99), len(names)), reverse=rng.random() < 0.5)
        size = dict(zip(names, values))
        order = list(range(premises))
        rng.shuffle(order)
        lines = []
        for i in order:
            a, b = names[i], names[i + 1]
            bigger = size[a] > size[b]
            if rng.random() < 0.5:
                lines.append(f"{a} es {'más grande' if bigger else 'más pequeño'} que {b}.")
            else:
                lines.append(f"{b} es {'más pequeño' if bigger else 'más grande'} que {a}.")
        x, y = rng.sample([names[0], names[-1], names[1], names[-2]], 2)
        while abs(names.index(x) - names.index(y)) < 2:
            x, y = rng.sample(names, 2)
        word = rng.choice(("más grande", "más pequeño"))
        truth = size[x] > size[y] if word == "más grande" else size[x] < size[y]
        return RelationalItem(lines, f"¿{x} es {word} que {y}?", truth)
    # coordination / opposition: "igual a" / "lo opuesto a"
    signs = {n: rng.choice((1, -1)) for n in names}
    order = list(range(premises))
    rng.shuffle(order)
    lines = []
    for i in order:
        a, b = names[i], names[i + 1]
        if rng.random() < 0.5:
            a, b = b, a
        same = signs[a] == signs[b]
        lines.append(f"{a} es {'igual a' if same else 'lo opuesto a'} {b}.")
    x, y = names[0], names[-1]
    if rng.random() < 0.5:
        x, y = y, x
    asked = rng.choice(("igual a", "lo opuesto a"))
    same = signs[x] == signs[y]
    truth = same if asked == "igual a" else not same
    return RelationalItem(lines, f"¿{x} es {asked} {y}?", truth)


# -- 6. Mental rotation (3D cube figures) -----------------------------------------------------
Voxel = tuple[int, int, int]


def _rotations() -> list[tuple[tuple[int, ...], ...]]:
    """The 24 proper rotations of a cube as 3x3 integer matrices."""
    mats = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            m = [[0] * 3 for _ in range(3)]
            for row, col in enumerate(perm):
                m[row][col] = signs[row]
            det = (
                m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
            )
            if det == 1:
                mats.append(tuple(tuple(r) for r in m))
    return mats


ROTATIONS = _rotations()


def rotate(cubes: list[Voxel], m: Any) -> list[Voxel]:
    return [
        tuple(sum(m[r][c] * v[c] for c in range(3)) for r in range(3))  # type: ignore[misc]
        for v in cubes
    ]


def normalise(cubes: list[Voxel]) -> tuple[Voxel, ...]:
    mins = [min(c[i] for c in cubes) for i in range(3)]
    return tuple(sorted(tuple(c[i] - mins[i] for i in range(3)) for c in cubes))  # type: ignore[misc]


def canonical(cubes: list[Voxel]) -> tuple[Voxel, ...]:
    """The same for any rotation of the figure (not for its mirror image)."""
    return min(normalise(rotate(cubes, m)) for m in ROTATIONS)


def mirror(cubes: list[Voxel]) -> list[Voxel]:
    return [(-x, y, z) for x, y, z in cubes]


def figure(rng: random.Random, size: int = 8) -> list[Voxel]:
    """A Shepard-Metzler style arm of cubes that bends in 3D (chiral)."""
    while True:
        cubes: list[Voxel] = [(0, 0, 0)]
        axis_used: list[int] = []
        while len(cubes) < size:
            axis = rng.choice([a for a in range(3) if not axis_used or a != axis_used[-1]])
            step = rng.choice((1, -1))
            length = rng.randint(2, 3)
            for _ in range(length):
                if len(cubes) >= size:
                    break
                last = cubes[-1]
                nxt = list(last)
                nxt[axis] += step
                nxt_t = tuple(nxt)
                if nxt_t in cubes:
                    break
                cubes.append(nxt_t)  # type: ignore[arg-type]
            axis_used.append(axis)
        if len(cubes) == size and len(set(axis_used)) == 3 and canonical(cubes) != canonical(mirror(cubes)):
            return cubes


@dataclass
class RotationItem:
    reference: list[Voxel]
    options: list[list[Voxel]]
    answer: int  # index of the rotated copy

    def check(self, answer: str) -> bool:
        try:
            return int(answer) - 1 == self.answer
        except (TypeError, ValueError):
            return False


def rotation(rng: random.Random) -> RotationItem:
    ref = figure(rng)
    same = rotate(ref, rng.choice(ROTATIONS[1:]))
    options = [same]
    while len(options) < 4:
        if len(options) < 3 or rng.random() < 0.5:
            other = rotate(mirror(ref), rng.choice(ROTATIONS))  # the mirror twin
        else:
            other = rotate(figure(rng), rng.choice(ROTATIONS))
            if canonical(other) == canonical(ref):
                continue
        if any(normalise(other) == normalise(o) for o in options):
            continue
        options.append(other)
    rng.shuffle(options)
    answer = next(i for i, o in enumerate(options) if canonical(o) == canonical(ref))
    return RotationItem(ref, options, answer)


# -- 7. Reversed lists -----------------------------------------------------------------------------
LIST_WORDS = (
    "sol", "mar", "pan", "luz", "rey", "flor", "gato", "mesa", "nube", "tren",
    "roca", "lago", "vino", "faro", "lobo", "pino", "río", "copa", "dedo", "foca",
)


@dataclass
class ListItem:
    items: list[str]

    @property
    def answer(self) -> list[str]:
        return self.items[::-1]

    def check(self, answer: str) -> bool:
        said = [plain(w) for w in re.split(r"[\s,;]+", answer.strip()) if w]
        if all(len(i) == 1 for i in self.items) and len(said) == 1:
            said = list(said[0])  # "93715" for digits
        return said == [plain(w) for w in self.answer]

    def partial(self, answer: str) -> float:
        said = [plain(w) for w in re.split(r"[\s,;]+", answer.strip()) if w]
        if all(len(i) == 1 for i in self.items) and len(said) == 1:
            said = list(said[0])
        good = 0
        for a, b in zip(said, (plain(w) for w in self.answer)):
            if a != b:
                break
            good += 1
        return good / len(self.items)


def reversed_list(rng: random.Random, length: int = 5) -> ListItem:
    if rng.random() < 0.5:
        digits = []
        while len(digits) < length:
            d = str(rng.randint(1, 9))
            if not digits or digits[-1] != d:
                digits.append(d)
        return ListItem(digits)
    return ListItem(rng.sample(LIST_WORDS, min(length, len(LIST_WORDS))))


# -- 8. Progressive matrices ---------------------------------------------------------------------
SHAPES = ("circulo", "cuadrado", "triangulo", "rombo", "hexagono")
SHADES = ("blanco", "gris", "negro")


# Rotation step per shape, chosen so the three steps always look different
# (a square turned 90 degrees would look unturned, a hexagon at 60...).
TURN_STEP = {"circulo": 0, "cuadrado": 30, "triangulo": 40, "rombo": 45, "hexagono": 15}


@dataclass(frozen=True)
class Cell:
    shape: str
    count: int
    shade: str
    turn: int  # 0, 1 or 2 steps of TURN_STEP[shape]

    @property
    def degrees(self) -> int:
        return self.turn * TURN_STEP[self.shape]


@dataclass
class MatrixItem:
    cells: list[Cell]  # 9, the last one is the answer (hidden)
    options: list[Cell]
    answer: int
    rules: dict[str, str] = field(default_factory=dict)

    def check(self, answer: str) -> bool:
        try:
            return int(answer) - 1 == self.answer
        except (TypeError, ValueError):
            return False


def matrix(rng: random.Random) -> MatrixItem:
    shapes = rng.sample(SHAPES, 3)
    shade_perm = rng.sample(SHADES, 3)
    counts = rng.choice(((1, 2, 3), (3, 2, 1), (2, 3, 4)))
    turns = (0, 1, 2)
    rules = {
        "shape": rng.choice(("fila", "latino")),
        "count": rng.choice(("progresion", "latino", "fijo")),
        "shade": rng.choice(("latino", "columna", "fijo")),
        "turn": rng.choice(("progresion", "fijo")),
    }
    if list(rules.values()).count("fijo") >= 2:
        rules["count"] = "progresion"
    cells = []
    for r in range(3):
        for c in range(3):
            shape = shapes[r] if rules["shape"] == "fila" else shapes[(r + c) % 3]
            if rules["count"] == "progresion":
                count = counts[c]
            elif rules["count"] == "latino":
                count = counts[(c + 2 * r) % 3]
            else:
                count = counts[1]
            if rules["shade"] == "latino":
                shade = shade_perm[(r + 2 * c) % 3]
            elif rules["shade"] == "columna":
                shade = shade_perm[c]
            else:
                shade = shade_perm[0]
            turn = turns[c] if rules["turn"] == "progresion" else 0
            if shape == "circulo":
                turn = 0
            cells.append(Cell(shape, count, shade, turn))
    right = cells[-1]
    options = {right}
    attempts = 0
    while len(options) < 6 and attempts < 200:
        attempts += 1
        change = rng.choice(("shape", "count", "shade", "turn"))
        if change == "shape":
            wrong = Cell(rng.choice([s for s in SHAPES if s != right.shape]), right.count, right.shade, right.turn)
        elif change == "count":
            wrong = Cell(right.shape, rng.choice([n for n in (1, 2, 3, 4) if n != right.count]), right.shade, right.turn)
        elif change == "shade":
            wrong = Cell(right.shape, right.count, rng.choice([s for s in SHADES if s != right.shade]), right.turn)
        else:
            if right.shape == "circulo":
                continue
            wrong = Cell(right.shape, right.count, right.shade, rng.choice([t for t in (0, 1, 2) if t != right.turn]))
        if wrong.shape == "circulo" and wrong.turn:
            wrong = Cell(wrong.shape, wrong.count, wrong.shade, 0)
        options.add(wrong)
    shown = list(options)
    rng.shuffle(shown)
    return MatrixItem(cells, shown, shown.index(right), rules)


# -- 9. Restricted word association --------------------------------------------------------------
CATEGORIES: dict[str, tuple[str, ...]] = {
    "animales": tuple(
        "abeja aguila alce almeja alpaca anaconda anguila antilope araña ardilla asno atun avestruz "
        "avispa ballena bisonte bufalo buho burro caballo cabra caiman calamar camaleon camello "
        "canario cangrejo canguro caracol castor cebra cerdo chacal chimpance chinchilla ciervo "
        "cigüeña cisne cobra cocodrilo codorniz colibri comadreja conejo cordero coyote cucaracha "
        "cuervo delfin dromedario elefante erizo escarabajo escorpion foca gacela gallina gallo "
        "ganso gato gavilan gaviota gorila gorrion grillo guepardo guacamayo gusano halcon hamster "
        "hiena hipopotamo hormiga huron iguana jabali jaguar jirafa koala langosta lagartija "
        "lagarto leon leopardo libelula liebre llama lobo loro lombriz lince mapache mariposa "
        "medusa mono mosca mosquito murcielago nutria oca orca oso oveja pajaro paloma panda "
        "pantera pato pavo pelicano perdiz perico perro pez pinguino piraña pulpo puma rana raton "
        "rinoceronte salamandra salmon saltamontes sapo sardina serpiente suricata tapir tarantula "
        "tejon tiburon tigre topo tortuga trucha tucan urraca vaca venado vibora yegua zorro zorrillo "
        "anchoa arana boa buey cachalote condor faisan flamenco gamba gorgojo jabalí lechuza morsa "
        "mula ñu ocelote ostra pavo-real pez-espada polilla pulga quetzal raya reno sanguijuela "
        "ternero toro vicuña cuy armadillo perezoso oruga marmota alacran".split()
    ),
    "frutas": tuple(
        "aguacate albaricoque arandano banano banana cereza ciruela coco datil durazno frambuesa "
        "fresa frutilla granada granadilla guanabana guayaba higo kiwi lima limon lichi mandarina "
        "mango manzana maracuya melocoton melon membrillo mora naranja naranjilla nispero papaya "
        "pera piña pitahaya platano pomelo sandia tamarindo tomate toronja tuna uva uvilla zapote "
        "babaco carambola chirimoya grosella kumquat mamey maracuya mangostan nectarina noni "
        "taxo tomate-de-arbol pepino-dulce badea arazá caimito guaba".split()
    ),
    "paises": tuple(
        "afganistan albania alemania andorra angola arabia argelia argentina armenia australia "
        "austria azerbaiyan bahamas banglades barbados barein belgica belice benin bielorrusia "
        "birmania bolivia bosnia botsuana brasil brunei bulgaria burundi butan camboya camerun "
        "canada catar chad chile china chipre colombia comoras congo corea croacia cuba dinamarca "
        "dominica ecuador egipto emiratos eritrea eslovaquia eslovenia españa estonia etiopia "
        "filipinas finlandia fiyi francia gabon gambia georgia ghana granada grecia guatemala "
        "guinea guyana haiti honduras hungria india indonesia irak iran irlanda islandia israel "
        "italia jamaica japon jordania kazajistan kenia kirguistan kiribati kosovo kuwait laos "
        "lesoto letonia libano liberia libia liechtenstein lituania luxemburgo macedonia "
        "madagascar malasia malaui maldivas mali malta marruecos mauricio mauritania mexico "
        "micronesia moldavia monaco mongolia montenegro mozambique namibia nauru nepal nicaragua "
        "niger nigeria noruega nueva-zelanda oman paises-bajos pakistan palaos panama paraguay peru "
        "polonia portugal ruanda rumania rusia samoa senegal serbia seychelles singapur siria "
        "somalia sudafrica sudan suecia suiza surinam tailandia tanzania tayikistan togo tonga "
        "tunez turkmenistan turquia tuvalu ucrania uganda uruguay uzbekistan vanuatu venezuela "
        "vietnam yemen yibuti zambia zimbabue holanda inglaterra escocia gales".split()
    ),
    "profesiones": tuple(
        "abogado actor actriz administrador agricultor albañil arquitecto artista astronauta "
        "astronomo azafata bailarin bibliotecario biologo bombero cajero camarero camionero "
        "cantante carnicero carpintero cartero chef cientifico cirujano cocinero conductor "
        "contador dentista diseñador economista electricista enfermero escritor escultor "
        "farmaceutico filosofo fisico fontanero fotografo futbolista geologo guia historiador "
        "ingeniero jardinero joyero juez locutor maestro marinero matematico mecanico medico "
        "mesero militar minero modelo musico notario obrero oculista panadero payaso peluquero "
        "periodista piloto pintor plomero policia politico profesor programador psicologo "
        "psiquiatra quimico recepcionista reportero sacerdote sastre secretario soldado "
        "taxista tecnico traductor veterinario vendedor zapatero barbero banquero cerrajero "
        "detective director editor empresario entrenador investigador pescador poeta "
        "productor relojero repartidor tenista agronomo carnicera".split()
    ),
    "partes del cuerpo": tuple(
        "abdomen antebrazo axila barbilla boca brazo cabello cabeza cadera canilla cara ceja "
        "cerebro cintura codo columna corazon costilla craneo cuello dedo diente encia espalda "
        "estomago frente garganta higado hombro hueso intestino labio lengua mandibula mano "
        "mejilla muñeca muslo nalga nariz nuca oido ojo ombligo oreja palma pantorrilla parpado "
        "pecho pelo pestaña pie piel pierna pulgar pulmon riñon rodilla talon tobillo tripa "
        "uña vena vientre arteria bazo pancreas tibia femur clavicula esternon menton sien".split()
    ),
    "deportes": tuple(
        "ajedrez alpinismo atletismo badminton baloncesto balonmano beisbol boxeo buceo "
        "canotaje ciclismo criquet equitacion escalada esgrima esqui futbol futsal gimnasia "
        "golf halterofilia hockey judo karate kayak lucha maraton motociclismo natacion "
        "paracaidismo parapente patinaje pesca polo remo rugby senderismo skate snowboard "
        "softbol squash surf taekwondo tenis tiro triatlon vela voleibol waterpolo yoga "
        "boliche billar padel carrera crossfit danza dardos frontenis karting kickboxing "
        "pentatlon sambo sumo windsurf".split()
    ),
    "verduras": tuple(
        "acelga aji ajo alcachofa apio arveja berenjena berro brocoli calabacin calabaza "
        "cebolla cebollin col coliflor esparrago espinaca garbanzo haba lechuga lenteja maiz "
        "nabo papa pepino perejil pimiento puerro rabano remolacha repollo rucula tomate "
        "vainita yuca zanahoria zapallo camote choclo cilantro frejol frijol jengibre mostaza "
        "nopal oca okra pimenton quinua rabanito albahaca champiñon hongo".split()
    ),
}


@dataclass
class WordChallenge:
    category: str
    rule: str  # shown to the user
    test: tuple[str, Any]  # ("starts", "c") etc.
    target: int = 3
    examples: tuple[str, ...] = ()

    def fits(self, word: str) -> bool:
        w = plain(word).replace(" ", "-")
        kind, value = self.test
        if kind == "starts":
            return w.startswith(value)
        if kind == "ends":
            return w.endswith(value)
        if kind == "contains":
            return value in w
        if kind == "without":
            return value not in w
        if kind == "length":
            return len(w.replace("-", "")) == value
        if kind == "longer":
            return len(w.replace("-", "")) > value
        return False

    def known(self, word: str) -> bool:
        w = plain(word).replace(" ", "-")
        words = {plain(x) for x in CATEGORIES[self.category]}
        return w in words or w.rstrip("s") in words or (w.endswith("es") and w[:-2] in words)

    def judge(self, word: str) -> str:
        """'ok', 'regla' (breaks the rule) or 'desconocida' (not in my list)."""
        if not self.fits(word):
            return "regla"
        return "ok" if self.known(word) else "desconocida"


_RULES = (
    ("starts", "empiezan con «{v}»", "abcdefghilmnoprstv"),
    ("ends", "terminan en «{v}»", "aeion"),
    ("contains", "tienen la letra «{v}»", "bcdfgjlmnprstvz"),
    ("without", "NO tienen la letra «{v}»", "aeo"),
    ("length", "tienen exactamente {v} letras", (4, 5, 6, 7)),
    ("longer", "tienen más de {v} letras", (7, 8)),
)


def word_challenge(rng: random.Random, minimum: int = 6) -> WordChallenge:
    while True:
        category = rng.choice(list(CATEGORIES))
        kind, text, values = rng.choice(_RULES)
        value = rng.choice(list(values))
        challenge = WordChallenge(category, text.format(v=value), (kind, value))
        valid = [w for w in CATEGORIES[category] if challenge.fits(w)]
        if len(valid) >= minimum:
            challenge.examples = tuple(rng.sample(valid, min(3, len(valid))))
            return challenge


# -- 10. Coordination sequences -----------------------------------------------------------------
PADS = ("d", "f", "j", "k")  # left hand D F, right hand J K


@dataclass
class CoordinationItem:
    steps: list[tuple[str, ...]]  # each step: one key or a chord (two keys)

    def check(self, pressed: list[tuple[str, ...]]) -> bool:
        return [tuple(sorted(s)) for s in pressed] == [tuple(sorted(s)) for s in self.steps]

    def partial(self, pressed: list[tuple[str, ...]]) -> float:
        good = 0
        for a, b in zip(pressed, self.steps):
            if tuple(sorted(a)) != tuple(sorted(b)):
                break
            good += 1
        return good / len(self.steps)


def coordination(rng: random.Random, length: int, chords: int = 0) -> CoordinationItem:
    steps: list[tuple[str, ...]] = []
    chord_at = set(rng.sample(range(1, length), min(chords, length - 1)))
    for i in range(length):
        if i in chord_at:  # both hands at once: one left key + one right key
            steps.append((rng.choice(PADS[:2]), rng.choice(PADS[2:])))
        else:
            key = rng.choice([k for k in PADS if not steps or (k,) != steps[-1]])
            steps.append((key,))
    return CoordinationItem(steps)


# -- control test: digit-symbol substitution (untrained) --------------------------------------
# Nine line drawings in a unit square: polylines of (x, y), y down.
GLYPHS: dict[str, tuple[tuple[tuple[float, float], ...], ...]] = {
    "uve": (((0.2, 0.2), (0.5, 0.8), (0.8, 0.2)),),
    "te": (((0.5, 0.2), (0.5, 0.8)), ((0.2, 0.8), (0.8, 0.8))),
    "u": (((0.2, 0.2), (0.2, 0.8), (0.8, 0.8), (0.8, 0.2)),),
    "igual": (((0.2, 0.38), (0.8, 0.38)), ((0.2, 0.62), (0.8, 0.62))),
    "equis": (((0.2, 0.2), (0.8, 0.8)), ((0.8, 0.2), (0.2, 0.8))),
    "lambda": (((0.2, 0.8), (0.5, 0.2), (0.8, 0.8)),),
    "mayor": (((0.25, 0.2), (0.75, 0.5), (0.25, 0.8)),),
    "ele": (((0.25, 0.2), (0.25, 0.8), (0.75, 0.8)),),
    "zeta": (((0.2, 0.2), (0.8, 0.2), (0.2, 0.8), (0.8, 0.8)),),
}


@dataclass
class SymbolKey:
    """Which number goes with each symbol (new order every time)."""

    order: list[str]  # order[i] is the symbol for number i + 1

    def digit(self, glyph: str) -> int:
        return self.order.index(glyph) + 1


def symbol_key(rng: random.Random) -> SymbolKey:
    return SymbolKey(rng.sample(sorted(GLYPHS), len(GLYPHS)))


def next_symbol(rng: random.Random, previous: str = "") -> str:
    return rng.choice([g for g in sorted(GLYPHS) if g != previous])


# -- does it work? ------------------------------------------------------------------------------
_T95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26,
        10: 2.23, 12: 2.18, 15: 2.13, 20: 2.09, 30: 2.04, 60: 2.00}


def _t95(df: int) -> float:
    return _T95[max(k for k in _T95 if k <= max(1, df))]


def trend(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Least squares slope with its 95% interval: (slope, low, high)."""
    n = len(points)
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if n < 3 or sxx == 0:
        return 0.0, float("-inf"), float("inf")
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    resid = sum((y - (my + slope * (x - mx))) ** 2 for x, y in points)
    se = (resid / (n - 2) / sxx) ** 0.5
    half = _t95(n - 2) * se
    return slope, slope - half, slope + half


def effectiveness(history: list[dict[str, Any]], now: float | None = None) -> dict[str, Any]:
    """Is the gym working? Trained exercises vs the untrained control test.

    * near transfer: your accuracy in each trained exercise, first half of
      your sessions vs the second half (practice makes these go up);
    * far transfer: the daily control test (never trained), its trend per
      week with a 95% confidence interval. Research predicts little or none.
    """
    import time as _time

    now = _time.time() if now is None else now
    trained: dict[str, list[float]] = {}
    probes: list[tuple[float, float]] = []
    for h in history:
        if h.get("kind") == "prueba":
            probes.append((float(h.get("time", now)), float(h.get("rate", h.get("correct", 0)))))
        elif "accuracy" in h:
            trained.setdefault(str(h.get("kind")), []).append(float(h["accuracy"]))
    near = {}
    for kind, values in trained.items():
        if len(values) >= 4:
            half = len(values) // 2
            first = sum(values[:half]) / half
            last = sum(values[half:]) / (len(values) - half)
            near[kind] = round((last - first) * 100, 1)
    out: dict[str, Any] = {"near": near, "probe_days": len(probes)}
    if len(probes) >= 5:
        start = probes[0][0]
        weeks = [((t - start) / (7 * 86400), rate) for t, rate in probes]
        slope, low, high = trend(weeks)
        base = sum(r for _, r in probes[:2]) / 2 or 1.0
        out.update(
            slope=round(slope, 2), low=round(low, 2), high=round(high, 2),
            percent_per_week=round(100 * slope / base, 1),
            far="sí" if low > 0 else ("empeora" if high < 0 else "no"),
        )
    return out


def effectiveness_text(history: list[dict[str, Any]]) -> str:
    """The same, in a few Spanish sentences Sergio can say."""
    data = effectiveness(history)
    parts = []
    if data["near"]:
        mean = sum(data["near"].values()) / len(data["near"])
        best = max(data["near"], key=data["near"].get)
        parts.append(
            f"En los ejercicios entrenados mejoraste {mean:+.0f} puntos de acierto de media "
            f"(lo que más: {BY_KIND[best].title if best in BY_KIND else best}, "
            f"{data['near'][best]:+.0f})."
        )
    else:
        parts.append("Aún hay pocas sesiones para ver tu progreso en los ejercicios.")
    days = data["probe_days"]
    if days < 5:
        parts.append(
            f"Para medir si te mejora fuera de los ejercicios necesito 5 días de la "
            f"prueba de control; llevas {days}."
        )
    elif data["far"] == "sí":
        parts.append(
            f"En la prueba de control, que no se entrena, subes {data['percent_per_week']:+.1f}% "
            f"por semana (intervalo del 95%: {data['low']:+.2f} a {data['high']:+.2f} aciertos/min): "
            "hay mejora medible, aunque parte puede ser práctica con la propia prueba."
        )
    else:
        parts.append(
            f"En la prueba de control, que no se entrena, el cambio es {data['percent_per_week']:+.1f}% "
            f"por semana y su intervalo del 95% ({data['low']:+.2f} a {data['high']:+.2f}) incluye "
            "el cero: no hay evidencia de que mejore fuera de lo entrenado, que es lo que "
            "predicen los metaanálisis."
        )
    return " ".join(parts)



# -- your profile: what each pop-up says about you ---------------------------------------
# Every answer is scored; the scores build a profile per skill. The weakest
# skill comes up more often, and after each exercise Sergio compares you
# with yourself (your own average), not with other people.
SKILLS = {
    "nback": "memoria de trabajo", "listas": "memoria de trabajo",
    "matrices": "razonamiento", "relacional": "razonamiento",
    "rotacion": "visoespacial", "simetria": "visoespacial",
    "stroop": "atención", "calculo": "cálculo mental",
    "palabras": "fluidez verbal", "repaso": "memoria a largo plazo",
    "coordinacion": "coordinación",
}  # fmt: skip
TRAINS: dict[str, list[str]] = {}
for _kind in dict.fromkeys(SCHEDULE):  # evidence order: the best one first
    if _kind in SKILLS:
        TRAINS.setdefault(SKILLS[_kind], []).append(_kind)
for _kind, _skill in SKILLS.items():
    TRAINS.setdefault(_skill, [])
    if _kind not in TRAINS[_skill]:
        TRAINS[_skill].append(_kind)
RECENT = 8  # sessions per skill that make its score (recent ones weigh more)
WEAK_GAP = 8.0  # points under your mean for a skill to count as "to work on"


def score(entry: dict[str, Any]) -> float:
    """One session, 0-100. The n-back level counts: 80% at 3-back > at 2-back."""
    value = float(entry.get("accuracy", 0.0)) * 100
    if entry.get("kind") == "nback":
        value += (int(entry.get("level", 2) or 2) - 2) * 10
    return max(0.0, min(100.0, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def profile(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per skill: score (0-100), trend (points, recent vs before), sessions, speed."""
    by_skill: dict[str, list[dict[str, Any]]] = {}
    for h in history:
        skill = SKILLS.get(str(h.get("kind")))
        if skill and "accuracy" in h:
            by_skill.setdefault(skill, []).append(h)
    out = {}
    for skill, entries in by_skill.items():
        recent = entries[-RECENT:]
        weights = range(1, len(recent) + 1)
        value = sum(w * score(e) for w, e in zip(weights, recent)) / sum(weights)
        trend = None
        if len(entries) >= 6:
            trend = round(_mean([score(e) for e in entries[-3:]]) - _mean([score(e) for e in entries[-6:-3]]), 1)
        speeds = [float(e["speed"]) for e in recent if e.get("speed")]
        out[skill] = {
            "score": round(value),
            "trend": trend,
            "sessions": len(entries),
            "speed": round(_mean(speeds), 1) if speeds else None,
        }
    return out


def weakest(prof: dict[str, dict[str, Any]], min_sessions: int = 2) -> str | None:
    """The skill clearly under your own mean (None while there is little data)."""
    known = {k: v["score"] for k, v in prof.items() if v["sessions"] >= min_sessions}
    if len(known) < 3:
        return None
    worst = min(known, key=known.get)
    return worst if _mean(list(known.values())) - known[worst] >= WEAK_GAP else None


def personal_next(index: int, history: list[dict[str, Any]]) -> tuple[Exercise, int]:
    """The evidence rotation, but every third pop-up trains your weakest skill."""
    exercise, after = next_exercise(index)
    if index % 3 != 2 or exercise.kind in ("pausa", "repaso"):
        return exercise, after
    weak = weakest(profile(history))
    if weak is None:
        return exercise, after
    last_seen = {str(h.get("kind")): i for i, h in enumerate(history)}
    kind = min(TRAINS[weak], key=lambda k: last_seen.get(k, -1))  # the least recent
    return BY_KIND[kind], after


def feedback(history: list[dict[str, Any]], entry: dict[str, Any]) -> str:
    """This session against your own record in the same exercise."""
    skill = SKILLS.get(str(entry.get("kind")))
    if not skill:
        return ""
    before = [h for h in history if h is not entry and h.get("kind") == entry.get("kind") and "accuracy" in h]
    if len(before) < 2:
        return f"Primeras medidas de tu {skill}: ya tengo tu punto de partida."
    mean = _mean([score(h) for h in before[-RECENT:]])
    diff = score(entry) - mean
    if diff >= 5:
        line = f"Mejor que tu media en {skill} ({mean:.0f}%)."
    elif diff <= -5:
        line = f"Por debajo de tu media en {skill} ({mean:.0f}%); un mal rato es normal."
    else:
        line = f"En tu media de {skill} ({mean:.0f}%)."
    speeds = [float(h["speed"]) for h in before[-RECENT:] if h.get("speed")]
    if entry.get("speed") and speeds:
        usual = _mean(speeds)
        if float(entry["speed"]) < usual * 0.9:
            line += " Y respondiste más rápido de lo habitual."
        elif float(entry["speed"]) > usual * 1.15:
            line += " Fuiste más lento de lo habitual."
    return line


def profile_text(history: list[dict[str, Any]]) -> str:
    """Your profile in a few Spanish sentences."""
    prof = profile(history)
    if not prof:
        return "Aún no tengo tu perfil: se arma con tus respuestas en el gimnasio mental."
    ranked = sorted(prof, key=lambda k: prof[k]["score"], reverse=True)
    parts = [
        "Tu perfil: "
        + ", ".join(f"{k} {prof[k]['score']}" for k in ranked)
        + " (de 100, según tus respuestas recientes)."
    ]
    if len(ranked) >= 2:
        parts.append(f"Tu punto fuerte: {ranked[0]}.")
    weak = weakest(prof)
    if weak:
        parts.append(f"A trabajar: {weak}; te lo pondré más a menudo.")
    rising = [k for k in ranked if (prof[k]["trend"] or 0) >= 5]
    falling = [k for k in ranked if (prof[k]["trend"] or 0) <= -5]
    if rising:
        parts.append("Subiendo: " + ", ".join(rising) + ".")
    if falling:
        parts.append("Bajando un poco: " + ", ".join(falling) + ".")
    return " ".join(parts)

# -- the session -------------------------------------------------------------------------------
@dataclass
class Session:
    """Score keeping for one pop-up."""

    exercise: Exercise
    correct: float = 0.0
    answered: int = 0
    times: list[float] = field(default_factory=list)
    level: int = 0  # n-back level reached, list length, etc.
    absent: bool = False  # nobody answered: not scored

    def record(self, ok: float, seconds: float | None = None) -> None:
        self.correct += ok
        self.answered += 1
        if seconds is not None:
            self.times.append(seconds)

    @property
    def total(self) -> int:
        if self.exercise.kind in ("nback", "prueba"):
            return max(1, self.answered)
        return self.exercise.items

    @property
    def rate(self) -> float:
        """Correct answers per minute (the control test's score)."""
        return self.correct * 60.0 / self.exercise.seconds

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def verdict(self) -> str:
        if self.absent:
            return "Parece que no estabas: lo dejamos para dentro de un rato."
        acc = self.accuracy
        if acc >= 0.9:
            return "Excelente."
        if acc >= 0.7:
            return "Muy bien."
        if acc >= 0.5:
            return "Bien. Se puede mejorar."
        return "A seguir entrenando."

    def summary(self) -> str:
        if self.absent:
            return "Sin respuestas: no cuenta."
        if self.exercise.kind == "nback":
            return f"Nivel {self.level}, {round(self.accuracy * 100)}% de aciertos."
        if self.exercise.kind == "prueba":
            return f"{int(self.correct)} símbolos correctos ({self.rate:.0f} por minuto)."
        shown = int(self.correct) if self.correct == int(self.correct) else round(self.correct, 1)
        line = f"{shown} de {self.total}"
        if self.times:
            line += f", {sum(self.times) / len(self.times):.1f} s por respuesta"
        return line + "."


def next_exercise(index: int) -> tuple[Exercise, int]:
    """Rotation by evidence (SCHEDULE): (this one, the index after it)."""
    i = index % len(SCHEDULE)
    return BY_KIND[SCHEDULE[i]], (i + 1) % len(SCHEDULE)


# -- spaced retrieval practice ------------------------------------------------------------
# Questions worth knowing (science, world, language, history): the point is
# the method, retrieving from memory at growing gaps, not these facts.
CARDS: tuple[tuple[str, str], ...] = (
    ("¿Cuál es el planeta más grande del sistema solar?", "júpiter"),
    ("¿Cuál es el símbolo químico del oro?", "au"),
    ("¿Qué gas absorben las plantas en la fotosíntesis?", "dióxido de carbono|co2"),
    ("¿Cuántos huesos tiene un adulto humano?", "206"),
    ("¿Cuál es la capital de Australia?", "canberra"),
    ("¿Cuál es el río más largo de Sudamérica?", "amazonas"),
    ("¿En qué año llegó el ser humano a la Luna?", "1969"),
    ("¿Quién formuló la teoría de la relatividad?", "einstein|albert einstein"),
    ("¿Cuál es la velocidad de la luz, aproximada, en km por segundo?", "300000|300 000|300.000|trescientos mil"),
    ("¿Qué orgánulo produce la energía de la célula?", "mitocondria|la mitocondria"),
    ("¿Cuál es el volcán activo más alto del Ecuador?", "cotopaxi|el cotopaxi"),
    ("¿Cuál es la capital de Canadá?", "ottawa"),
    ("¿Cuál es el océano más grande?", "pacífico|el pacífico"),
    ("¿Qué significa «efímero»?", "que dura poco|pasajero|breve|fugaz"),
    ("¿Qué significa «ubicuo»?", "que está en todas partes|omnipresente"),
    ("¿Cuánto es la raíz cuadrada de 144?", "12|doce"),
    ("¿Cuánto es 15 por 15?", "225"),
    ("¿Cuántos lados tiene un hexágono?", "6|seis"),
    ("¿Qué científico propuso la selección natural?", "darwin|charles darwin"),
    ("¿Cuál es el elemento más abundante del universo?", "hidrógeno"),
    ("¿En qué país están las pirámides de Giza?", "egipto"),
    ("¿Qué escritor creó a Don Quijote?", "cervantes|miguel de cervantes"),
    ("¿Cuál es la capital de Japón?", "tokio"),
    ("¿Cuál es la montaña más alta del mundo?", "everest|el everest"),
    ("¿Cuál es el punto de ebullición del agua al nivel del mar, en grados Celsius?", "100|cien"),
    ("¿Qué instrumento mide la presión atmosférica?", "barómetro|el barómetro"),
    ("¿Cuál es el hueso más largo del cuerpo?", "fémur|el fémur"),
    ("¿Qué pintor hizo La noche estrellada?", "van gogh|vincent van gogh"),
    ("¿Cuál es la moneda del Japón?", "yen|el yen"),
    ("¿Cuál es el número primo que sigue a 13?", "17|diecisiete"),
    ("¿En qué continente está Kenia?", "áfrica"),
    ("¿Qué parte del cerebro es clave para formar recuerdos nuevos?", "hipocampo|el hipocampo"),
    ("¿Qué vitamina produce la piel con el sol?", "d|vitamina d"),
    ("¿Cuál es la fórmula del agua?", "h2o"),
    ("¿Qué significa «perspicaz»?", "agudo|que entiende rápido|sagaz|listo"),
    ("¿Cuál es la capital de Alemania?", "berlín"),
    ("¿Quién pintó la Mona Lisa?", "leonardo|da vinci|leonardo da vinci"),
    ("¿Cuántos minutos tiene un día?", "1440|1 440|1.440"),
    ("¿Qué planeta se conoce como el planeta rojo?", "marte"),
    ("¿Qué islas del Ecuador inspiraron a Darwin?", "galápagos|las galápagos"),
)  # fmt: skip
GAPS_DAYS = (0.0, 1.0, 3.0, 7.0, 16.0, 35.0)  # Leitner boxes


def answer_matches(given: str, accepted: str) -> bool:
    """Typed answer vs the accepted ones ("júpiter" = "Jupiter" = "jupiter")."""
    import difflib

    def words(text: str) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", plain(text)).split())

    said = words(given)
    if not said:
        return False
    for option in accepted.split("|"):
        want = words(option)
        if said == want or (len(want) >= 4 and difflib.SequenceMatcher(None, said, want).ratio() >= 0.85):
            return True
        if len(want) >= 4 and want in said.split() + [said]:
            return True
    return False


@dataclass
class Deck:
    """Which card is in which box, and when each is due (epoch seconds)."""

    boxes: dict[str, int] = field(default_factory=dict)
    due: dict[str, float] = field(default_factory=dict)

    def pick(self, now: float, count: int, rng: random.Random) -> list[int]:
        """Due cards first (lowest box first), then new ones."""
        due = [i for i in range(len(CARDS)) if str(i) in self.due and self.due[str(i)] <= now]
        due.sort(key=lambda i: (self.boxes.get(str(i), 0), self.due[str(i)]))
        new = [i for i in range(len(CARDS)) if str(i) not in self.due]
        rng.shuffle(new)
        later = sorted(
            (i for i in range(len(CARDS)) if str(i) in self.due and self.due[str(i)] > now),
            key=lambda i: self.due[str(i)],
        )
        return (due + new + later)[:count]

    def review(self, card: int, ok: bool, now: float) -> None:
        key = str(card)
        box = min(self.boxes.get(key, 0) + 1, len(GAPS_DAYS) - 1) if ok else 0
        self.boxes[key] = box
        # A miss comes back in this very session's next round (10 min).
        self.due[key] = now + (GAPS_DAYS[box] * 86400 if ok else 600)

    def to_json(self) -> dict[str, Any]:
        return {"boxes": self.boxes, "due": self.due}

    @classmethod
    def from_json(cls, data: Any) -> "Deck":
        if not isinstance(data, dict):
            return cls()
        return cls(
            {str(k): int(v) for k, v in (data.get("boxes") or {}).items()},
            {str(k): float(v) for k, v in (data.get("due") or {}).items()},
        )


__all__ = [
    "BY_KIND",
    "CARDS",
    "Deck",
    "EVIDENCE",
    "SCHEDULE",
    "answer_matches",
    "CATEGORIES",
    "GLYPHS",
    "PROBE",
    "SymbolKey",
    "effectiveness",
    "effectiveness_text",
    "next_symbol",
    "symbol_key",
    "trend",
    "EXERCISES",
    "Exercise",
    "NBack",
    "PADS",
    "Session",
    "arithmetic",
    "canonical",
    "coordination",
    "figure",
    "matrix",
    "mirror",
    "next_exercise",
    "relational",
    "reversed_list",
    "rotation",
    "stroop",
    "symmetry",
    "word_challenge",
]

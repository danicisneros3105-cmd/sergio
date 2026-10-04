"""Real physics over the camera image: make things with your hands and play.

Mode "Física" (camera window or "Sergio, crea una pelota"):

* **Create with two hands**: pinch with both hands close together and pull
  them apart; a box grows between your fingers. Let go and it drops.
  Hold the pinch still for a moment with one hand to make a ball there.
* **Grab and throw**: pinch near an object to grab it, move, and open your
  fingers to throw it — it keeps the speed of your hand.
* **Push**: your fingertips are solid; flick objects or juggle them.
* Voice: "crea 5 cubos", "lanza una pelota roja", "gravedad cero",
  "gravedad lunar", "gravedad invertida", "explota todo", "borra los objetos".

Rigid bodies with mass, friction, bounce, rotation and collisions (pymunk,
the Chipmunk2D engine). World units: the image is 1000 wide (y downwards),
in the coordinates you see (mirrored like a selfie when the view is).
"""

from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

WIDTH = 1000.0
GRAVITY = {
    "normal": (0.0, 1400.0),
    "lunar": (0.0, 260.0),
    "cero": (0.0, 0.0),
    "invertida": (0.0, -1400.0),
}
MAX_OBJECTS = 40
SHAPES = ("pelota", "cubo", "triangulo", "estrella")
COLORS = {
    "rojo": "#ff453a",
    "roja": "#ff453a",
    "naranja": "#ff9f0a",
    "amarillo": "#ffd60a",
    "amarilla": "#ffd60a",
    "verde": "#30d158",
    "azul": "#0a84ff",
    "morado": "#bf5af2",
    "morada": "#bf5af2",
    "rosa": "#ff375f",
    "blanco": "#f2f2f7",
    "blanca": "#f2f2f7",
    "negro": "#3a3a3c",
    "negra": "#3a3a3c",
    "dorado": "#e5c07b",
    "dorada": "#e5c07b",
}
PALETTE = ("#0a84ff", "#30d158", "#ff9f0a", "#ff453a", "#bf5af2", "#64d2ff", "#ffd60a")
FINGERTIPS = (4, 8, 12, 16, 20)
GRAB_REACH = 70.0  # world units from the pinch to an object's edge
PINCH_ON, PINCH_OFF = 0.3, 0.45  # thumb-index distance / palm size
HOLD_TO_CREATE = 0.8  # seconds of a still pinch in the air -> a ball


@dataclass
class Thing:
    """One object in the world (what the camera window draws)."""

    id: int
    shape: str
    color: str
    size: float  # radius for balls, side for the rest
    body: Any
    poly: list[tuple[float, float]] = field(default_factory=list)  # local verts

    @property
    def position(self) -> tuple[float, float]:
        return float(self.body.position.x), float(self.body.position.y)

    @property
    def angle(self) -> float:
        return float(self.body.angle)

    def outline(self) -> list[tuple[float, float]]:
        """World-space polygon (or the centre for balls)."""
        if self.shape == "pelota":
            return [self.position]
        b = self.body
        return [tuple(b.local_to_world(v)) for v in self.poly]


def star_points(size: float, points: int = 5) -> list[tuple[float, float]]:
    out = []
    for i in range(points * 2):
        r = size / 2 if i % 2 == 0 else size / 4.6
        a = -math.pi / 2 + i * math.pi / points
        out.append((r * math.cos(a), r * math.sin(a)))
    return out


def _pinch(lm: Sequence[Sequence[float]]) -> float:
    palm = math.dist(lm[0][:2], lm[9][:2]) or 1e-6
    return math.dist(lm[4][:2], lm[8][:2]) / palm


@dataclass
class HandState:
    pinching: bool = False
    grabbed: Any = None  # (thing, joint, anchor body)
    still_since: float = 0.0
    still_at: tuple[float, float] = (0.0, 0.0)
    colliders: list[Any] = field(default_factory=list)


class Sandbox:
    """A little physics world drawn over the camera picture."""

    def __init__(
        self,
        aspect: float = 9 / 16,
        rng: random.Random | None = None,
        floor: float = 0.88,
    ):
        import pymunk

        self._pm = pymunk
        self.width = WIDTH
        self.height = WIDTH * aspect
        self.floor = self.height * floor  # above the camera window's buttons
        self.space = pymunk.Space()
        self.space.gravity = GRAVITY["normal"]
        self.space.damping = 0.98
        self.gravity = "normal"
        self.things: list[Thing] = []
        self.hands: dict[int, HandState] = {}
        self.preview: tuple[tuple[float, float], tuple[float, float]] | None = None
        self.rng = rng or random.Random()
        self._next = 1
        self._walls()

    # -- the room ----------------------------------------------------------------
    def _walls(self) -> None:
        pm, w, h = self._pm, self.width, self.floor
        static = self.space.static_body
        walls = [
            pm.Segment(static, (-50, h), (w + 50, h), 6),  # floor
            pm.Segment(static, (-6, -h), (-6, h + 50), 6),  # left
            pm.Segment(static, (w + 6, -h), (w + 6, h + 50), 6),  # right
            pm.Segment(static, (-50, -6), (w + 50, -6), 6),  # ceiling
        ]
        for wall in walls:
            wall.elasticity = 0.55
            wall.friction = 0.9
        self.space.add(*walls)

    def set_gravity(self, name: str) -> str:
        if name not in GRAVITY:
            return f"No conozco la gravedad {name}."
        self.gravity = name
        self.space.gravity = GRAVITY[name]
        self.space.damping = 0.9 if name == "cero" else 0.98
        for thing in self.things:
            thing.body.activate()
        return {
            "normal": "Gravedad normal.",
            "lunar": "Gravedad lunar: todo flota un poco.",
            "cero": "Gravedad cero: todo flota.",
            "invertida": "Gravedad invertida: todo cae hacia arriba.",
        }[name]

    # -- making things -------------------------------------------------------------
    def add(
        self,
        shape: str = "pelota",
        at: tuple[float, float] | None = None,
        size: float | None = None,
        color: str = "",
        velocity: tuple[float, float] = (0.0, 0.0),
    ) -> Thing:
        pm = self._pm
        shape = shape if shape in SHAPES else self.rng.choice(SHAPES)
        size = float(size or self.rng.uniform(55, 95))
        size = max(24.0, min(size, self.height * 0.8))
        x, y = at if at is not None else (self.rng.uniform(80, self.width - 80), 60.0)
        color = color or self.rng.choice(PALETTE)
        if shape == "pelota":
            radius = size / 2
            mass = 0.002 * radius**2
            body = pm.Body(mass, pm.moment_for_circle(mass, 0, radius))
            parts = [pm.Circle(body, radius)]
            poly: list[tuple[float, float]] = []
        else:
            if shape == "cubo":
                half = size / 2
                poly = [(-half, -half), (half, -half), (half, half), (-half, half)]
            elif shape == "triangulo":
                r = size / math.sqrt(3)
                poly = [
                    (r * math.cos(a), r * math.sin(a))
                    for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)
                ]
            else:  # estrella: concave, made of convex pieces on one body
                poly = star_points(size)
            mass = 0.0016 * size**2
            if shape == "estrella":
                body = pm.Body(mass, pm.moment_for_circle(mass, 0, size / 2))
                parts = [
                    pm.Poly(body, [(0, 0), poly[i], poly[(i + 1) % len(poly)]])
                    for i in range(len(poly))
                ]
            else:
                body = pm.Body(mass, pm.moment_for_poly(mass, poly))
                parts = [pm.Poly(body, poly)]
        body.position = (x, y)
        body.velocity = velocity
        body.angle = self.rng.uniform(-0.4, 0.4) if shape != "pelota" else 0.0
        for part in parts:
            part.elasticity = 0.62 if shape == "pelota" else 0.35
            part.friction = 0.7
        self.space.add(body, *parts)
        thing = Thing(self._next, shape, color, size, body, poly)
        self._next += 1
        self.things.append(thing)
        while len(self.things) > MAX_OBJECTS:
            self.remove(self.things[0])
        return thing

    def remove(self, thing: Thing) -> None:
        for state in self.hands.values():
            if state.grabbed and state.grabbed[0] is thing:
                self._release(state)
        self.space.remove(thing.body, *thing.body.shapes)
        self.things.remove(thing)

    def clear(self) -> int:
        count = len(self.things)
        for thing in list(self.things):
            self.remove(thing)
        return count

    def explode(self, strength: float = 1400.0) -> None:
        cx, cy = self.width / 2, self.height * 0.8
        for thing in self.things:
            x, y = thing.position
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy) or 1.0
            mass = thing.body.mass
            thing.body.apply_impulse_at_world_point(
                (dx / dist * strength * mass, (dy / dist - 1.2) * strength * mass),
                (x, y),
            )

    def command(self, text: str) -> str:
        """Spoken orders: "crea 5 cubos rojos", "gravedad cero", "borra todo"."""
        from sergio_escritorio.jarvis import _plain

        t = _plain(text)
        if re.search(r"\b(borra|quita|limpia|elimina)\b", t):
            n = self.clear()
            return f"Listo, quité {n} objetos." if n else "No había objetos."
        if re.search(r"\b(explota|explosion|revienta)\b", t):
            self.explode()
            return "Boom."
        if "gravedad" in t or "sin gravedad" in t:
            if "sin gravedad" in t or "cero" in t:
                return self.set_gravity("cero")
            for name in ("lunar", "invertida", "normal"):
                if name in t or (name == "lunar" and "luna" in t):
                    return self.set_gravity(name)
            return self.set_gravity("normal")
        numbers = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
                   "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
        m = re.search(r"\b(\d+|" + "|".join(numbers) + r")\b", t)
        count = 1
        if m:
            word = m.group(1)
            count = int(word) if word.isdigit() else numbers[word]
        count = max(1, min(count, 20))
        shape = "pelota"
        for word, name in (
            ("pelota", "pelota"), ("bola", "pelota"), ("balon", "pelota"),
            ("cubo", "cubo"), ("caja", "cubo"), ("triangulo", "triangulo"),
            ("estrella", "estrella"), ("objeto", "aleatorio"),
        ):
            if word in t:
                shape = name
                break
        color = next((COLORS[c] for c in COLORS if re.search(rf"\b{c}s?\b", t)), "")
        big = 120.0 if re.search(r"\b(grande|enorme|gigante)\b", t) else None
        small = 40.0 if re.search(r"\b(pequen[ao]s?|chiquit[ao]s?)\b", t) else None
        throw = re.search(r"\b(lanza|tira)\b", t) is not None
        for i in range(count):
            velocity = (self.rng.uniform(-500, 500), -self.rng.uniform(300, 700)) if throw else (0.0, 0.0)
            at = (self.width / 2 + self.rng.uniform(-300, 300), 50.0 + 30 * (i % 3))
            self.add(
                shape if shape != "aleatorio" else self.rng.choice(SHAPES),
                at=at,
                size=big or small,
                color=color,
                velocity=velocity,
            )
        names = {"pelota": "pelota", "cubo": "cubo", "triangulo": "triángulo",
                 "estrella": "estrella", "aleatorio": "objeto"}
        noun = names[shape]
        if count == 1:
            return f"Ahí tiene su {noun}."
        plural = noun + ("es" if noun.endswith("n") else "s")
        return f"Ahí van {count} {plural}."

    # -- your hands -------------------------------------------------------------------
    def to_world(self, x: float, y: float, mirror: bool) -> tuple[float, float]:
        return ((1 - x) if mirror else x) * self.width, y * self.height

    def update_hands(self, hands: Sequence[Any], dt: float, mirror: bool, now: float | None = None) -> None:
        """Hands from MediaPipe (``.landmarks`` 0..1): touch, grab, create."""
        pm = self._pm
        now = time.monotonic() if now is None else now
        dt = max(dt, 1e-3)
        seen = set()
        pinches: list[tuple[int, tuple[float, float]]] = []
        for i, hand in enumerate(hands[:2]):
            lm = hand.landmarks
            seen.add(i)
            state = self.hands.setdefault(i, HandState())
            if not state.colliders:
                for _ in (*FINGERTIPS, 9):
                    body = pm.Body(body_type=pm.Body.KINEMATIC)
                    circle = pm.Circle(body, 16)
                    circle.elasticity, circle.friction = 0.4, 0.9
                    self.space.add(body, circle)
                    state.colliders.append(body)
            # Fingertips (and the palm) push things: move with the hand's speed.
            for body, idx in zip(state.colliders, (*FINGERTIPS, 9)):
                target = self.to_world(lm[idx][0], lm[idx][1], mirror)
                vx = (target[0] - body.position.x) / dt
                vy = (target[1] - body.position.y) / dt
                if math.hypot(vx, vy) > 6000:  # the hand reappeared: jump there
                    body.position, body.velocity = target, (0, 0)
                else:
                    body.velocity = (vx, vy)
            ratio = _pinch(lm)
            pinch_at = self.to_world(
                (lm[4][0] + lm[8][0]) / 2, (lm[4][1] + lm[8][1]) / 2, mirror
            )
            was = state.pinching
            state.pinching = ratio < (PINCH_OFF if was else PINCH_ON)
            for body in state.colliders:  # a pinching hand holds, not hits
                for shape in body.shapes:
                    shape.sensor = state.pinching
            if state.pinching:
                pinches.append((i, pinch_at))
                if not was:
                    self._grab(state, pinch_at)
                    state.still_since, state.still_at = now, pinch_at
                if state.grabbed:
                    anchor = state.grabbed[2]
                    anchor.velocity = (
                        (pinch_at[0] - anchor.position.x) / dt,
                        (pinch_at[1] - anchor.position.y) / dt,
                    )
                elif math.dist(pinch_at, state.still_at) > 25:
                    state.still_since, state.still_at = now, pinch_at
            elif was:
                self._release(state)
        for i in list(self.hands):
            if i not in seen:
                self._drop_hand(i)
        self._create_with_hands(pinches, now)

    def _create_with_hands(self, pinches: list[tuple[int, tuple[float, float]]], now: float) -> None:
        free = [(i, p) for i, p in pinches if not self.hands[i].grabbed]
        if len(free) == 2:
            (_, a), (_, b) = free
            self.preview = (a, b)  # pull apart: a box grows between them
            return
        if self.preview is not None:
            a, b = self.preview
            self.preview = None
            side = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
            if side >= 40:
                self.add("cubo", at=((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), size=side)
            return
        for i, point in free:
            state = self.hands[i]
            if now - state.still_since >= HOLD_TO_CREATE:
                thing = self.add("pelota", at=point, size=70)
                self._attach(state, thing, point)
                state.still_since = now + 1e9  # once per pinch

    def _grab(self, state: HandState, point: tuple[float, float]) -> None:
        best, best_d = None, GRAB_REACH
        for thing in self.things:
            query = thing.body.shapes and min(
                s.point_query(point).distance for s in thing.body.shapes
            )
            if query is not None and query < best_d:
                best, best_d = thing, query
        if best is not None:
            self._attach(state, best, point)

    def _attach(self, state: HandState, thing: Thing, point: tuple[float, float]) -> None:
        pm = self._pm
        anchor = pm.Body(body_type=pm.Body.KINEMATIC)
        anchor.position = point
        joint = pm.PivotJoint(anchor, thing.body, (0, 0), thing.body.world_to_local(point))
        joint.max_force = 60000 * thing.body.mass
        joint.error_bias = (1 - 0.35) ** 60
        self.space.add(anchor, joint)
        state.grabbed = (thing, joint, anchor)

    def _release(self, state: HandState) -> None:
        if not state.grabbed:
            return
        thing, joint, anchor = state.grabbed
        self.space.remove(joint, anchor)
        state.grabbed = None
        # It keeps the hand's speed: a throw.
        thing.body.velocity = anchor.velocity
        thing.body.activate()

    def _drop_hand(self, i: int) -> None:
        state = self.hands.pop(i)
        self._release(state)
        for body in state.colliders:
            self.space.remove(body, *body.shapes)

    # -- time ----------------------------------------------------------------------
    def step(self, dt: float) -> None:
        dt = min(max(dt, 0.0), 0.05)
        steps = max(1, int(math.ceil(dt / (1 / 240))))
        for _ in range(steps):
            self.space.step(dt / steps)
        # Anything flung out of the room comes back from the top.
        for thing in self.things:
            x, y = thing.position
            if not (-200 < x < self.width + 200 and -400 < y < self.height + 200):
                thing.body.position = (self.width / 2, 60)
                thing.body.velocity = (0, 0)


__all__ = ["COLORS", "GRAVITY", "SHAPES", "Sandbox", "Thing", "star_points"]

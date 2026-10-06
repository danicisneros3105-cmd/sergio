"""Sergio's camera vision, live on the laptop: who and what is in front of him.

Layers, from instant to deep:

* **Objects and species** (MediaPipe EfficientDet, ~5 times a second):
  people, dogs, cats, birds... and 70 kinds of everyday objects, named in
  Spanish, with a stable number per thing while it stays in view.
* **Faces up close** (MediaPipe Face Landmarker, ~10 times a second): the
  478-point face mesh, where the head points (yaw/pitch/roll) and the
  expression (smiling, surprised, eyes closed, winking). Nodding means "sí"
  and shaking the head "no".
* **Names** come from Sergio's face recognition (server), voted over several
  looks so a stranger is never called by your name after one lucky frame.
* **Analizar** asks Gemini about everything in view: any object at all,
  breeds, and how people look (man or woman, rough age, clothes).

The maths (labels, tracking, votes, head gestures) is pure and tested
without a camera; MediaPipe only turns frames into boxes and points.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

log = logging.getLogger(__name__)

MODELS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SergioEscritorio" / "models"
SHIPPED = Path(__file__).parent / "models"  # small files that ship with Sergio
MODEL_URLS = {
    # 30 % more accurate than Lite0 (COCO mAP 34 vs 26) and finds about twice
    # as many objects on the test photos; ~150 ms a frame, in the background.
    "efficientdet_lite2.tflite": (
        "https://storage.googleapis.com/mediapipe-models/object_detector/"
        "efficientdet_lite2/float16/latest/efficientdet_lite2.tflite"
    ),
    "efficientdet_lite0.tflite": (
        "https://storage.googleapis.com/mediapipe-models/object_detector/"
        "efficientdet_lite0/float16/latest/efficientdet_lite0.tflite"
    ),
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/latest/face_landmarker.task"
    ),
}

# COCO classes (what the detector knows) -> Spanish, kind, species.
ANIMALS = {
    "bird": "pájaro",
    "cat": "gato",
    "dog": "perro",
    "horse": "caballo",
    "sheep": "oveja",
    "cow": "vaca",
    "elephant": "elefante",
    "bear": "oso",
    "zebra": "cebra",
    "giraffe": "jirafa",
}
OBJECTS = {
    "bicycle": "bicicleta",
    "car": "auto",
    "motorcycle": "moto",
    "airplane": "avión",
    "bus": "bus",
    "train": "tren",
    "truck": "camión",
    "boat": "bote",
    "traffic light": "semáforo",
    "fire hydrant": "hidrante",
    "stop sign": "señal de pare",
    "parking meter": "parquímetro",
    "bench": "banca",
    "backpack": "mochila",
    "umbrella": "paraguas",
    "handbag": "bolso",
    "tie": "corbata",
    "suitcase": "maleta",
    "frisbee": "frisbi",
    "skis": "esquís",
    "snowboard": "snowboard",
    "sports ball": "pelota",
    "kite": "cometa",
    "baseball bat": "bate",
    "baseball glove": "guante",
    "skateboard": "patineta",
    "surfboard": "tabla de surf",
    "tennis racket": "raqueta",
    "bottle": "botella",
    "wine glass": "copa",
    "cup": "taza",
    "fork": "tenedor",
    "knife": "cuchillo",
    "spoon": "cuchara",
    "bowl": "tazón",
    "banana": "plátano",
    "apple": "manzana",
    "sandwich": "sánduche",
    "orange": "naranja",
    "broccoli": "brócoli",
    "carrot": "zanahoria",
    "hot dog": "hot dog",
    "pizza": "pizza",
    "donut": "dona",
    "cake": "pastel",
    "chair": "silla",
    "couch": "sofá",
    "potted plant": "planta",
    "bed": "cama",
    "dining table": "mesa",
    "toilet": "inodoro",
    "tv": "televisor",
    "laptop": "laptop",
    "mouse": "mouse",
    "remote": "control remoto",
    "keyboard": "teclado",
    "cell phone": "celular",
    "microwave": "microondas",
    "oven": "horno",
    "toaster": "tostadora",
    "sink": "lavabo",
    "refrigerator": "refrigeradora",
    "book": "libro",
    "clock": "reloj",
    "vase": "florero",
    "scissors": "tijeras",
    "teddy bear": "peluche",
    "hair drier": "secadora",
    "toothbrush": "cepillo de dientes",
}


def label_es(name: str) -> tuple[str, str, str]:
    """English COCO name -> (Spanish label, kind, species)."""
    name = (name or "").strip().lower()
    if name == "person":
        return "persona", "persona", "humano"
    if name in ANIMALS:
        return ANIMALS[name], "animal", ANIMALS[name]
    return OBJECTS.get(name, name or "objeto"), "objeto", ""


Box = tuple[float, float, float, float]  # x, y, w, h — 0..1 of the frame

# The detector only knows 80 kinds of things, so anything else in a hand
# (a lipstick, a pen, a key) comes out as its nearest look-alike: "control
# remoto", "celular", "cepillo de dientes"... These names are only shown when
# the detector is really sure; otherwise the thing is just "Objeto" until
# Gemini names it from a close-up (see AutoNamer / Tracker.name_track).
CONFUSABLE = {
    "remote", "cell phone", "toothbrush", "scissors", "knife", "spoon", "fork",
    "mouse", "hair drier", "tie", "baseball bat", "skateboard", "surfboard",
    "frisbee", "kite", "skis", "snowboard", "sports ball", "hot dog", "carrot",
    "banana", "donut", "cake", "vase", "bottle", "book", "handbag", "umbrella",
    "parking meter", "fire hydrant", "toaster",
}  # fmt: skip
MIN_SCORE = {"persona": 0.45, "animal": 0.4, "objeto": 0.45}
SURE = 0.68  # a confusable class needs this much to keep its name


@dataclass
class Seen:
    """One thing found in one frame."""

    label: str
    kind: str  # persona | animal | objeto
    species: str
    score: float
    box: Box
    held: bool = False  # in one of your hands


def iou(a: Box, b: Box) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    w = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    h = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = w * h
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def overlap_small(a: Box, b: Box) -> float:
    """How much of the smaller box lies inside the other one (0..1)."""
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    w = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    h = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    small = min(a[2] * a[3], b[2] * b[3])
    return (w * h) / small if small > 0 else 0.0


def _same_thing(a: Box, b: Box) -> bool:
    """Two boxes of one thing (a cup on a laptop or a cat in front of a dog
    are two things: one box is much smaller than the other)."""
    if iou(a, b) > 0.55:
        return True
    areas = sorted((a[2] * a[3], b[2] * b[3]))
    return areas[1] > 0 and areas[0] / areas[1] > 0.45 and overlap_small(a, b) > 0.85


# Things a hand alone gets mistaken for (by any COCO detector).
HANDLIKE = {"plátano", "hot dog", "zanahoria", "dona", "peluche", "guante",
            "sánduche", "cepillo de dientes", "objeto"}  # fmt: skip
# Furniture and fixtures: real, but noise on screen unless asked about.
BACKGROUND = {"mesa", "cama", "sofá", "silla", "planta", "lavabo", "inodoro",
              "refrigeradora", "horno", "microondas", "banca", "televisor"}  # fmt: skip
MAX_OBJECTS = 4  # on screen at once: the held ones and the most salient


def hand_box(landmarks: Sequence[Sequence[float]], grow: float = 0.15) -> Box:
    """The box around a hand's 21 points (0..1 of the frame), a bit larger."""
    xs = [pt[0] for pt in landmarks]
    ys = [pt[1] for pt in landmarks]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    return (max(0.0, x0 - w * grow), max(0.0, y0 - h * grow), w * (1 + 2 * grow), h * (1 + 2 * grow))


def _area(b: Box) -> float:
    return max(0.0, b[2]) * max(0.0, b[3])


def is_the_hand(item: Seen, hand: Box) -> bool:
    """The detector boxed the hand itself (as "persona", "plátano"...)."""
    if item.kind == "persona":
        # A real person's box is far bigger than one of their hands (an arm
        # coming into view is not another person either).
        return _area(item.box) < 3.0 * _area(hand) and overlap_small(item.box, hand) > 0.4
    if item.kind == "objeto":
        if iou(item.box, hand) > 0.45 and (item.label in HANDLIKE or iou(item.box, hand) > 0.7):
            return True
        # Something unsure lying wholly inside the hand is a finger, not a
        # thing you hold (what you hold sticks out of your hand).
        inside = overlap_small(item.box, hand) > 0.85 and _area(item.box) < _area(hand)
        return inside and item.label in HANDLIKE
    return False


def clean_detections(found: Sequence[Seen], hands: Sequence[Box] = ()) -> list[Seen]:
    """One label per thing, and no confident-sounding wrong names.

    The detector gives the same lipstick three boxes ("control remoto",
    "celular", "cepillo de dientes"): only the best one stays (per kind, so a
    held object is never swallowed by the person holding it). Weak guesses
    are dropped and unsure look-alike names become "objeto".
    """
    kept: list[Seen] = []
    for item in sorted(found, key=lambda f: -f.score):
        if item.score < MIN_SCORE.get(item.kind, 0.5):
            continue
        if any(is_the_hand(item, hand) for hand in hands):
            continue  # your hand is not a banana, nor another person
        if any(k.kind == item.kind and _same_thing(k.box, item.box) for k in kept):
            continue
        if item.kind == "objeto" and any(
            overlap_small(item.box, hand) > 0.25 and _area(item.box) < 2.5 * _area(hand) for hand in hands
        ):
            item.held = True
        kept.append(item)
    return kept


def salient(tracks: Sequence["Track"], limit: int = MAX_OBJECTS, clean: bool = False) -> list["Track"]:
    """What is worth showing: people, animals, held things, then a few of
    the biggest objects; furniture only when it is all there is.

    *clean* (the default view): people, animals, what you hold and what
    Gemini named; other things only when sure and big (no "objeto ¿?")."""
    people = [t for t in tracks if t.kind != "objeto"]
    things = [t for t in tracks if t.kind == "objeto"]
    if clean:
        keep = [
            t
            for t in things
            if t.held
            or t.named
            or (t.label != "objeto" and t.shown not in BACKGROUND and t.box[2] * t.box[3] >= 0.04)
        ]
        keep.sort(key=lambda t: (not t.held, not t.named, -t.box[2] * t.box[3]))
        return people + keep[:2]
    things.sort(key=lambda t: (not t.held, t.shown in BACKGROUND, -t.box[2] * t.box[3]))
    shown = [t for t in things if t.held or t.shown not in BACKGROUND or t.named][:limit]
    return people + shown


UNKNOWN = "?"


def body_of(face: Box, people: Sequence["Track"]) -> "Track | None":
    """The person whose body this face belongs to: the face centre in the
    upper part of the body box; the tightest such box wins."""
    cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
    fits = [
        t
        for t in people
        if t.box[0] <= cx <= t.box[0] + t.box[2]
        and t.box[1] - face[3] <= cy <= t.box[1] + t.box[3] * 0.6
    ]
    return min(fits, key=lambda t: t.box[2] * t.box[3], default=None)


def contains(outer: Box, inner: Box) -> bool:
    cx, cy = inner[0] + inner[2] / 2, inner[1] + inner[3] / 2
    return outer[0] <= cx <= outer[0] + outer[2] and outer[1] <= cy <= outer[1] + outer[3]


# -- tracking -------------------------------------------------------------------
@dataclass
class Track:
    id: int
    label: str
    kind: str
    species: str
    box: Box
    score: float
    first_seen: float
    last_seen: float
    hits: int = 1
    names: deque = field(default_factory=lambda: deque(maxlen=3))
    guest: int = 0
    detail: str = ""  # from "Analizar" (Gemini): breed, looks...
    detail_until: float = 0.0
    face_score: float = 0.0
    face_box: Box | None = None  # where the face is (to crop it for a name)
    held: bool = False  # in your hand right now
    votes: Counter = field(default_factory=Counter)  # label -> evidence
    named: str = ""  # what Gemini said it is, from a close-up (sticky)

    @property
    def shown(self) -> str:
        """The object's name on screen: Gemini's, a sure one, or "objeto"."""
        if self.named:
            return self.named
        return self.label if self.label != "objeto" else "objeto"

    @property
    def name(self) -> str:
        """A name only once most recent looks agree (no lucky guesses)."""
        counts = Counter(n for n in self.names if n)
        if not counts:
            return ""
        best, votes = counts.most_common(1)[0]
        # "?" = a clear face that is nobody enrolled: never shown as a name.
        return best if votes >= 2 and best != UNKNOWN else ""

    def title(self, now: float, clean: bool = False) -> str:
        if self.kind == "persona":
            base = self.name or (f"Persona {self.guest}" if self.guest else "Persona")
        else:
            base = self.shown[:1].upper() + self.shown[1:]
            if self.held:
                base += " · en tu mano"
        if clean:
            return base
        if self.detail and now < self.detail_until and self.detail.lower() != base.lower():
            return f"{base} · {self.detail}"
        return base


class Tracker:
    """Gives each person, animal and object a number that stays with it."""

    def __init__(self, keep: float = 1.0, smooth: float = 0.55) -> None:
        self.keep = keep  # seconds a thing may vanish before it is dropped
        self.smooth = smooth  # box smoothing (0 = frozen, 1 = jumpy)
        self.tracks: list[Track] = []
        self._next = 1
        self._lock = threading.Lock()

    def update(self, seen: Sequence[Seen], now: float) -> list[Track]:
        with self._lock:
            free = list(self.tracks)
            for item in sorted(seen, key=lambda s: -s.score):
                best, best_iou = None, 0.25
                for track in free:
                    if track.kind != item.kind:
                        continue
                    overlap = iou(track.box, item.box)
                    if overlap > best_iou:
                        best, best_iou = track, overlap
                if best is None:
                    track = Track(
                        self._next,
                        item.label,
                        item.kind,
                        item.species,
                        item.box,
                        item.score,
                        now,
                        now,
                    )
                    track.votes[item.label] += item.score
                    track.held = item.held
                    self.tracks.append(track)
                    self._next += 1
                    continue
                free.remove(best)
                k = self.smooth
                best.box = tuple(  # type: ignore[assignment]
                    (1 - k) * old + k * new for old, new in zip(best.box, item.box)
                )
                best.score = 0.7 * best.score + 0.3 * item.score
                # The name is voted over the last frames (a flicker between
                # "celular" and "control remoto" is one thing, not two).
                for key in list(best.votes):
                    best.votes[key] *= 0.85
                best.votes[item.label] += item.score
                best.label = best.votes.most_common(1)[0][0]
                best.held = item.held
                if item.label == best.label:
                    best.species = item.species
                best.last_seen = now
                best.hits += 1
            self.tracks = [t for t in self.tracks if now - t.last_seen <= self.keep]
            if not self.tracks:
                self._next = 1
            return list(self.tracks)

    def visible(self, now: float, min_hits: int = 2) -> list[Track]:
        """Tracks seen a couple of times (no one-frame ghosts)."""
        with self._lock:
            return [
                t
                for t in self.tracks
                if t.hits >= min_hits and now - t.last_seen <= self.keep
            ]

    def add_faces(self, faces: Sequence[dict], now: float) -> list[str]:
        """Face recognition results -> names voted onto the people.

        *faces*: ``{"name", "guest", "score", "box"}`` with boxes 0..1.
        Returns the names that just became certain (to greet them).
        """
        confirmed = []
        with self._lock:
            people = [t for t in self.tracks if t.kind == "persona"]
            taken: set[int] = set()
            for face in faces:
                box = tuple(face["box"])
                owner = body_of(box, [t for t in people if t.id not in taken])
                if owner is None:  # the detector missed the body: face only
                    owner = next(
                        (t for t in people if t.id not in taken and iou(t.box, box) > 0.3), None
                    )
                if owner is None:
                    owner = Track(
                        self._next, "persona", "persona", "humano", box, 0.9, now, now, 2
                    )
                    self._next += 1
                    self.tracks.append(owner)
                    people.append(owner)
                taken.add(owner.id)
                before = owner.name
                owner.face_box = box
                vote = face.get("name") or ""
                if not vote and face.get("quality", "ok") == "ok" and face.get("guest"):
                    vote = UNKNOWN  # seen clearly and it is nobody we know
                if vote and any(n and n != vote for n in owner.names):
                    owner.names.clear()  # someone else now: no inherited name
                owner.names.append(vote)
                owner.guest = int(face.get("guest") or 0) or owner.guest
                owner.face_score = float(face.get("score") or 0.0)
                if owner.name and owner.name != before:
                    confirmed.append(owner.name)
        return confirmed

    def name_track(self, track_id: int, label: str, detail: str = "") -> bool:
        """Gemini looked at this thing up close: that is its name now."""
        label = " ".join(str(label or "").split())[:40]
        if not label:
            return False
        with self._lock:
            for track in self.tracks:
                if track.id == track_id:
                    track.named = label.lower()
                    if detail:
                        track.detail, track.detail_until = detail[:60], 1e18
                    return True
        return False

    def add_scene(self, items: Sequence[dict], now: float, seconds: float = 12.0) -> None:
        """Gemini's "Analizar" details: breeds, looks, any object."""
        with self._lock:
            for item in items:
                box = tuple(item["box"])
                detail = item.get("detail") or ""
                match = max(
                    (t for t in self.tracks if t.kind == item.get("kind")),
                    key=lambda t: iou(t.box, box),
                    default=None,
                )
                if match is not None and iou(match.box, box) > 0.3:
                    match.detail, match.detail_until = detail, now + seconds
                    if match.kind == "objeto" and item.get("label"):
                        match.named = str(item["label"]).lower()[:40]
                    continue
                kind = item.get("kind") or "objeto"
                track = Track(
                    self._next,
                    item.get("label") or "objeto",
                    kind,
                    item.get("species") or "",
                    box,
                    0.6,
                    now,
                    now + seconds - self.keep,  # stays while the detail shows
                    2,
                )
                track.detail, track.detail_until = detail, now + seconds
                if item.get("name"):
                    track.names.extend([item["name"]] * 2)
                self._next += 1
                self.tracks.append(track)


def summary(tracks: Sequence[Track], now: float) -> str:
    """'2 personas (Dani y una que no conozco), 1 perro y 3 objetos: ...'"""
    people = [t for t in tracks if t.kind == "persona"]
    animals = [t for t in tracks if t.kind == "animal"]
    things = [t for t in tracks if t.kind == "objeto"]
    parts = []
    if people:
        named = [t.name for t in people if t.name]
        strangers = len(people) - len(named)
        who = list(named)
        if strangers:
            who.append(
                "una persona que no conozco"
                if strangers == 1
                else f"{strangers} personas que no conozco"
            )
        parts.append(" y ".join(who) if len(who) <= 2 else ", ".join(who))
    if animals:
        count = Counter(t.label for t in animals)
        parts.append(
            ", ".join(
                f"{n} {label}{'s' if n > 1 and not label.endswith('s') else ''}"
                if n > 1
                else f"un{'a' if label.endswith('a') else ''} {label}"
                for label, n in count.items()
            )
        )
    if things:
        names = list(dict.fromkeys(t.shown for t in things))[:6]
        parts.append("objetos: " + ", ".join(names))
    if not parts:
        return "No veo a nadie ni nada en particular."
    return "Veo " + "; ".join(parts) + "."


def scene_sentence(items: Sequence[dict]) -> str:
    """Gemini's "Analizar" items -> what Sergio says about them."""
    people, animals, things = [], [], []
    for item in items:
        detail = (item.get("detail") or "").strip()
        if item.get("kind") == "persona":
            name = item.get("name") or ""
            if name:
                people.append(name)
            else:
                people.append(f"una persona ({detail})" if detail else "una persona")
        elif item.get("kind") == "animal":
            label = item.get("label") or item.get("species") or "animal"
            animals.append(f"{label} ({detail})" if detail and detail != label else label)
        else:
            label = item.get("label") or "objeto"
            things.append(label)
    parts = []
    if people:
        who = [f"a {p}" for p in people]
        parts.append(" y ".join(who) if len(who) <= 2 else ", ".join(who[:-1]) + " y " + who[-1])
    if animals:
        parts.append(("animales: " if len(animals) > 1 else "un animal: ") + ", ".join(animals))
    if things:
        parts.append("objetos: " + ", ".join(dict.fromkeys(things)))
    return ("Veo " + "; ".join(parts) + ".") if parts else "No distingo nada en particular."


# -- faces up close: expressions and head pose --------------------------------------
def expressions(blend: dict[str, float]) -> list[str]:
    """MediaPipe blendshapes -> what the face is doing, in Spanish."""
    g = blend.get
    out = []
    smile = (g("mouthSmileLeft", 0) + g("mouthSmileRight", 0)) / 2
    if smile > 0.55:
        out.append("sonriendo")
    if g("jawOpen", 0) > 0.45 and smile < 0.4:
        out.append("boca abierta")
    if g("browInnerUp", 0) > 0.5 and g("jawOpen", 0) > 0.25:
        out.append("sorprendido")
    blink_l, blink_r = g("eyeBlinkLeft", 0), g("eyeBlinkRight", 0)
    if blink_l > 0.6 and blink_r > 0.6:
        out.append("ojos cerrados")
    elif abs(blink_l - blink_r) > 0.45 and max(blink_l, blink_r) > 0.6:
        out.append("guiño")
    if (g("browDownLeft", 0) + g("browDownRight", 0)) / 2 > 0.6 and smile < 0.3:
        out.append("ceño fruncido")
    if g("mouthPucker", 0) > 0.6:
        out.append("beso")
    return out


def head_angles(matrix: Sequence[Sequence[float]]) -> tuple[float, float, float]:
    """(yaw, pitch, roll) in degrees from MediaPipe's face transform matrix."""
    r = [[float(matrix[i][j]) for j in range(3)] for i in range(3)]
    sy = math.hypot(r[0][0], r[1][0])
    if sy > 1e-6:
        pitch = math.degrees(math.atan2(r[2][1], r[2][2]))
        yaw = math.degrees(math.atan2(-r[2][0], sy))
        roll = math.degrees(math.atan2(r[1][0], r[0][0]))
    else:
        pitch = math.degrees(math.atan2(-r[1][2], r[1][1]))
        yaw = math.degrees(math.atan2(-r[2][0], sy))
        roll = 0.0
    return yaw, pitch, roll


class HeadGestures:
    """Nodding = "sí", shaking the head = "no" (answers without words)."""

    def __init__(self, window: float = 1.4, swing: float = 9.0, cooldown: float = 2.5):
        self.window, self.swing, self.cooldown = window, swing, cooldown
        self._yaw: deque[tuple[float, float]] = deque()
        self._pitch: deque[tuple[float, float]] = deque()
        self._last = -1e9

    @staticmethod
    def _swings(series: deque, swing: float) -> int:
        """How many times the angle reversed by more than *swing* degrees."""
        count, direction, anchor = 0, 0, None
        for _t, value in series:
            if anchor is None:
                anchor = value
                continue
            delta = value - anchor
            if direction >= 0 and delta <= -swing:
                count += direction != 0
                direction, anchor = -1, value
            elif direction <= 0 and delta >= swing:
                count += direction != 0
                direction, anchor = 1, value
            elif (direction > 0 and value > anchor) or (direction < 0 and value < anchor):
                anchor = value
            elif direction == 0 and abs(delta) < 1:
                anchor = value
        return count

    def feed(self, now: float, yaw: float, pitch: float) -> str | None:
        for series, value in ((self._yaw, yaw), (self._pitch, pitch)):
            series.append((now, value))
            while series and now - series[0][0] > self.window:
                series.popleft()
        if now - self._last < self.cooldown:
            return None
        nods = self._swings(self._pitch, self.swing)
        shakes = self._swings(self._yaw, self.swing)
        if nods >= 2 and nods > shakes:
            self._last = now
            self._yaw.clear()
            self._pitch.clear()
            return "si"
        if shakes >= 2 and shakes > nods:
            self._last = now
            self._yaw.clear()
            self._pitch.clear()
            return "no"
        return None


@dataclass
class FaceInfo:
    points: list[tuple[float, float]]  # 478 face mesh points, 0..1
    box: Box
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    expressions: list[str] = field(default_factory=list)
    blend: dict = field(default_factory=dict)  # MediaPipe blendshapes (eyes, gaze...)


# Face mesh outlines worth drawing (MediaPipe indices): oval, eyes, brows, lips.
FACE_OVAL = (10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365,
             379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93,
             234, 127, 162, 21, 54, 103, 67, 109, 10)
LEFT_EYE = (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387,
            388, 466, 263)
RIGHT_EYE = (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160,
             161, 246, 33)
LIPS = (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0,
        37, 39, 40, 185, 61)
LEFT_BROW = (276, 283, 282, 295, 285)
RIGHT_BROW = (46, 53, 52, 65, 55)
OUTLINES = (FACE_OVAL, LEFT_EYE, RIGHT_EYE, LIPS, LEFT_BROW, RIGHT_BROW)


# -- MediaPipe ----------------------------------------------------------------------
def ensure_model(name: str, folder: Path = MODELS_DIR) -> Path:
    path = folder / name
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    import httpx

    folder.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with httpx.stream("GET", MODEL_URLS[name], timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)
    tmp.replace(path)
    return path


class _Clock:
    def __init__(self) -> None:
        self.last = 0

    def __call__(self) -> int:
        stamp = max(self.last + 1, int(time.monotonic() * 1000))
        self.last = stamp
        return stamp


class ObjectFinder:
    """Frame (OpenCV BGR) -> people, animals and objects (Spanish names)."""

    MODELS = ("efficientdet_lite2.tflite", "efficientdet_lite0.tflite")

    def __init__(self, score: float = 0.3, max_results: int = 25) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        self._clock = _Clock()
        last: Exception | None = None
        for name in self.MODELS:  # the better model, else the small one
            try:
                path = ensure_model(name)
                self._detector = vision.ObjectDetector.create_from_options(
                    vision.ObjectDetectorOptions(
                        base_options=BaseOptions(model_asset_path=str(path)),
                        running_mode=vision.RunningMode.VIDEO,
                        score_threshold=score,
                        max_results=max_results,
                    )
                )
                self.model = name
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("object model %s unavailable: %s", name, exc)
                last = exc
        else:
            raise RuntimeError(f"Sin modelo de objetos: {last}")

    def find(self, frame: Any, hands: Sequence[Box] = ()) -> list[Seen]:
        import cv2
        import numpy as np

        h, w = frame.shape[:2]
        # The detector squeezes its input into a square. Squashing a 16:9
        # webcam frame misses people; padding it all the way to a square
        # mistakes dogs for cats. Padding to 4:3 was best on every test photo
        # (right species, higher scores, more objects).
        ph, pw = max(h, int(round(w * 3 / 4))), max(w, int(round(h * 4 / 3)))
        y0, x0 = (ph - h) // 2, (pw - w) // 2
        square = np.zeros((ph, pw, 3), dtype=frame.dtype)
        square[y0 : y0 + h, x0 : x0 + w] = frame
        rgb = cv2.cvtColor(square, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect_for_video(image, self._clock())
        found = []
        for det in result.detections or []:
            cat = det.categories[0]
            label, kind, species = label_es(cat.category_name)
            if kind == "objeto" and cat.category_name in CONFUSABLE and cat.score < SURE:
                label = "objeto"  # a look-alike guess: Gemini will name it
            b = det.bounding_box
            x = max(0.0, (b.origin_x - x0) / w)
            y = max(0.0, (b.origin_y - y0) / h)
            bw = min(1.0 - x, b.width / w)
            bh = min(1.0 - y, b.height / h)
            if bw <= 0 or bh <= 0:
                continue
            found.append(Seen(label, kind, species, float(cat.score), (x, y, bw, bh)))
        return clean_detections(found, hands)


YOLO_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/{name}"


def cuda_works() -> bool:
    """True only if the NVIDIA card really runs PyTorch's kernels. A torch
    built for other cards says "available" and then fails on every frame
    (cudaErrorNoKernelImageForDevice): then the processor is the answer."""
    try:
        import torch

        if not torch.cuda.is_available():
            return False
        major, minor = torch.cuda.get_device_capability(0)
        arches = torch.cuda.get_arch_list()
        if arches and f"sm_{major}{minor}" not in arches and not any(
            a.startswith("compute_") for a in arches
        ):
            log.warning("PyTorch has no kernels for this card (sm_%s%s): CPU", major, minor)
            return False
        return float((torch.ones(8, device="cuda") * 2).sum().item()) == 16.0
    except Exception as exc:  # noqa: BLE001
        log.warning("CUDA unusable, vision on the CPU: %s", exc)
        return False


def gpu_broken(exc: BaseException) -> bool:
    text = str(exc)
    return "cuda" in text.lower() or "no kernel image" in text.lower()


class YoloFinder:
    """YOLO11 (Ultralytics): the modern detector, on the NVIDIA GPU when there
    is one (the medium model) or the CPU (the small one). It makes far fewer
    of the old mistakes (window = televisor, hoodie = corbata)."""

    def __init__(self, score: float = 0.4) -> None:
        from ultralytics import YOLO

        gpu = cuda_works()
        name = "yolo11m.pt" if gpu else "yolo11s.pt"
        MODEL_URLS.setdefault(name, YOLO_URL.format(name=name))
        self._model = YOLO(str(ensure_model(name)))
        self._device = 0 if gpu else "cpu"
        self._half = gpu  # half precision on the GPU: about twice as fast
        self._size = 640
        self._score = score
        self.gpu = gpu
        self.model = name + (" (GPU)" if gpu else " (CPU)")
        self._vocab: Any = None
        self._vocab_every = 1 if gpu else 3  # the open vocabulary, every N frames
        self._frame = 0
        self._extra: list[Seen] = []
        try:
            self._vocab = VocabFinder(gpu)
            self.model += " + YOLOE"
        except Exception as exc:  # noqa: BLE001 — 80 classes then
            log.info("YOLOE vocabulary unavailable: %s", exc)

    def to_cpu(self) -> None:
        """The card failed mid-run: keep seeing, on the processor."""
        self._device, self._half, self.gpu = "cpu", False, False
        self._vocab_every = 3
        self.model = self.model.replace("(GPU)", "(CPU)")
        if self._vocab is not None:
            self._vocab.to_cpu()

    def find(self, frame: Any, hands: Sequence[Box] = ()) -> list[Seen]:
        try:
            result = self._model.predict(
                frame, conf=self._score, verbose=False, device=self._device,
                imgsz=self._size, half=self._half,
            )[0]
        except Exception as exc:
            if not self.gpu or not gpu_broken(exc):
                raise
            log.warning("GPU failed (%s): vision moves to the CPU", str(exc)[:120])
            self.to_cpu()
            result = self._model.predict(
                frame, conf=self._score, verbose=False, device="cpu", imgsz=self._size
            )[0]
        names = result.names
        found = []
        for cls, conf, box in zip(
            result.boxes.cls.tolist(), result.boxes.conf.tolist(), result.boxes.xyxyn.tolist()
        ):
            label, kind, species = label_es(names[int(cls)])
            if kind == "objeto" and names[int(cls)] in CONFUSABLE and conf < SURE:
                label = "objeto"
            x0, y0, x1, y1 = box
            found.append(Seen(label, kind, species, float(conf), (x0, y0, x1 - x0, y1 - y0)))
        if self._vocab is not None:
            self._frame += 1
            if self._frame % self._vocab_every == 0:
                try:
                    self._extra = self._vocab.find(frame, self._size)
                except Exception as exc:  # noqa: BLE001
                    if gpu_broken(exc) and self._device != "cpu":
                        self.to_cpu()
                    else:
                        log.exception("YOLOE failed")
                        self._vocab = None
            extra = [Seen(e.label, e.kind, e.species, e.score, e.box) for e in self._extra]
            found = merge_vocab(found, [e for e in extra if vocab_sure(e, hands)])
        return clean_detections(found, hands)


# Things the 80-class detector does not know, found by YOLOE (open
# vocabulary, prompted with these names): English prompt -> Spanish label.
VOCAB = {
    "lipstick": "labial", "pen": "bolígrafo", "pencil": "lápiz", "marker": "marcador",
    "key": "llave", "wallet": "billetera", "eyeglasses": "lentes", "sunglasses": "gafas de sol",
    "headphones": "audífonos", "earbuds": "audífonos", "wristwatch": "reloj de pulsera",
    "notebook": "cuaderno", "window": "ventana", "door": "puerta", "lamp": "lámpara",
    "guitar": "guitarra", "hat": "sombrero", "baseball cap": "gorra", "hoodie": "hoodie",
    "jacket": "chaqueta", "picture frame": "cuadro", "poster": "póster", "flag": "bandera",
    "rubik's cube": "cubo de Rubik", "phone charger": "cargador", "cable": "cable",
    "cardboard box": "caja", "shoe": "zapato", "perfume bottle": "perfume", "drinking glass": "vaso",
    "plate": "plato", "pillow": "almohada", "curtain": "cortina", "mirror": "espejo",
    "speaker": "parlante", "tablet": "tableta", "game controller": "control de videojuego",
    "microphone": "micrófono", "camera": "cámara", "candle": "vela", "toy": "juguete",
    "ring": "anillo", "necklace": "collar", "bracelet": "pulsera", "comb": "peine",
    "hairbrush": "cepillo de pelo", "makeup brush": "brocha de maquillaje",
    "nail polish": "esmalte de uñas", "coin": "moneda", "credit card": "tarjeta",
    "sheet of paper": "papel", "ruler": "regla", "stapler": "engrapadora",
    "calculator": "calculadora", "deodorant": "desodorante", "lighter": "encendedor",
    "usb flash drive": "memoria USB", "medicine bottle": "frasco de medicina",
    "spray bottle": "atomizador", "screwdriver": "destornillador", "hammer": "martillo",
    "glove": "guante",
}  # fmt: skip
# Asked to YOLOE as well, as a second opinion on the species.
VOCAB_ANIMALS = {"dog": "perro", "cat": "gato", "bird": "pájaro", "horse": "caballo"}


class VocabFinder:
    """YOLOE with Sergio's vocabulary (a lipstick is "labial", not "control
    remoto"). The text prompts are encoded ahead of time (models/)."""

    def __init__(self, gpu: bool) -> None:
        import torch
        from ultralytics import YOLOE

        name = "yoloe-11m-seg.pt" if gpu else "yoloe-11s-seg.pt"
        MODEL_URLS.setdefault(name, YOLO_URL.format(name=name))
        self._model = YOLOE(str(ensure_model(name)))
        names = list(VOCAB) + list(VOCAB_ANIMALS)
        # The words are encoded ahead of time and ship with Sergio: encoding
        # them here would download a 572 MB text model.
        data = torch.load(SHIPPED / f"{Path(name).stem}-vocab.pt", map_location="cpu")
        if data.get("names") != names:
            raise RuntimeError("vocabulario de YOLOE desactualizado")
        pe = data["pe"].float()
        self._model.set_classes(names, pe)
        self._device = 0 if gpu else "cpu"
        self._half = gpu

    def to_cpu(self) -> None:
        self._device, self._half = "cpu", False

    def find(self, frame: Any, size: int) -> list[Seen]:
        result = self._model.predict(
            frame, conf=0.35, verbose=False, device=self._device, imgsz=size, half=self._half
        )[0]
        out = []
        for cls, conf, box in zip(
            result.boxes.cls.tolist(), result.boxes.conf.tolist(), result.boxes.xyxyn.tolist()
        ):
            name = result.names[int(cls)]
            x0, y0, x1, y1 = box
            if name in VOCAB_ANIMALS:
                label = VOCAB_ANIMALS[name]
                out.append(Seen(label, "animal", label, float(conf), (x0, y0, x1 - x0, y1 - y0)))
                continue
            label = VOCAB.get(name, name)
            out.append(Seen(label, "objeto", "", float(conf), (x0, y0, x1 - x0, y1 - y0)))
        return out


# Measured on COCO photos: these names, from the open vocabulary, were often
# wrong when not very sure (a ring or necklace on bare skin, a lipstick on a
# smile, a hat on plain hair, a flag on any banner).
TRICKY = {"anillo", "collar", "pulsera", "labial", "sombrero", "gorra", "perfume",
          "desodorante", "billetera", "control de videojuego", "almohada", "póster",
          "parlante", "bandera", "espejo", "juguete", "cable", "papel", "moneda",
          "esmalte de uñas", "brocha de maquillaje", "peine", "encendedor"}  # fmt: skip
VOCAB_HELD, VOCAB_SURE, VOCAB_TRICKY = 0.40, 0.55, 0.82


def vocab_sure(item: Seen, hands: Sequence[Box] = ()) -> bool:
    """Keep an open-vocabulary name only when it is likely right: in your
    hand a softer bar (that is what it is for), elsewhere a strict one."""
    if item.kind == "animal":
        return item.score >= VOCAB_HELD  # only a second opinion on animals
    if any(overlap_small(item.box, hand) > 0.25 for hand in hands):
        return item.score >= VOCAB_HELD
    return item.score >= (VOCAB_TRICKY if item.label in TRICKY else VOCAB_SURE)


def merge_vocab(base: list[Seen], extra: Sequence[Seen]) -> list[Seen]:
    """Add what only the open-vocabulary model saw, and give unsure objects
    ("objeto") the precise name it found in the same place."""
    out = list(base)
    for item in extra:
        twin = next((b for b in out if iou(b.box, item.box) > 0.4), None)
        if item.kind == "animal":
            # Only a second opinion: when the two models disagree (a poodle
            # called "gato"), it says "animal" and Gemini names it.
            if twin is not None and twin.kind == "animal" and twin.label != item.label and item.score >= 0.4:
                twin.label, twin.species = "animal", ""
            continue
        if twin is None:
            out.append(item)
        elif twin.kind == "objeto" and twin.label in ("objeto", *HANDLIKE) and item.score >= 0.4:
            twin.label = item.label
    return out


def best_finder() -> Any:
    """YOLO11 when installed, else MediaPipe's EfficientDet."""
    try:
        return YoloFinder()
    except Exception as exc:  # noqa: BLE001 — not installed / no weights
        log.info("YOLO11 unavailable (%s); using EfficientDet", exc)
        return ObjectFinder()


class FaceMesh:
    """Frame -> faces with the 478-point mesh, head pose and expression."""

    def __init__(self, max_faces: int = 3) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        self._clock = _Clock()
        self._landmarker = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(
                    model_asset_path=str(ensure_model("face_landmarker.task"))
                ),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=max_faces,
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
            )
        )

    def find(self, frame: Any) -> list[FaceInfo]:
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, self._clock())
        faces = []
        for i, marks in enumerate(result.face_landmarks or []):
            pts = [(m.x, m.y) for m in marks]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
            info = FaceInfo(pts, box)
            if result.face_blendshapes and i < len(result.face_blendshapes):
                blend = {c.category_name: c.score for c in result.face_blendshapes[i]}
                info.expressions = expressions(blend)
                info.blend = blend
            matrices = result.facial_transformation_matrixes or []
            if i < len(matrices):
                info.yaw, info.pitch, info.roll = head_angles(matrices[i])
            faces.append(info)
        return faces


# Labels the detector gives that say little: Gemini names them properly.
VAGUE = {"objeto", "botella", "libro", "maleta", "bolso", "celular", "control remoto"}


class AutoNamer:
    """When to let Gemini name what the camera sees, by itself.

    The detector knows 80 kinds of things; Gemini knows anything ("una
    guitarra acústica", "un cubo de Rubik"). Asking on every frame would
    burn the free quota in minutes, so it asks only when something new has
    stayed in view for a moment (or a hand is holding something), never
    more than once every *gap* seconds and *daily* times a day.
    """

    def __init__(self, gap: float = 10.0, daily: int = 200, settle: float = 1.0) -> None:
        self.gap = gap
        self.daily = daily
        self.settle = settle
        self.enabled = True
        self._asked: set[int] = set()  # tracks already described
        self._tried: set[int] = set()  # tracks already sent for a close-up
        self._last = -1e9
        self._day = ""
        self._count = 0

    def due(self, tracks: Sequence[Track], now: float, holding: bool = False, day: str = "") -> bool:
        if not self.enabled or now - self._last < self.gap:
            return False
        if day and day != self._day:
            self._day, self._count = day, 0
        if self._count >= self.daily:
            return False
        fresh = [
            t
            for t in tracks
            if t.id not in self._asked
            and t.kind != "persona"
            and now - t.first_seen >= self.settle
            and not (t.detail and now < t.detail_until)
        ]
        return bool(fresh) or holding

    def pick(self, tracks: Sequence[Track], now: float) -> Track | None:
        """The thing most worth a close-up: unnamed, settled, held/big."""
        options = [
            t
            for t in tracks
            if (t.kind == "objeto" or (t.kind == "animal" and t.label == "animal"))
            and not t.named
            and now - t.first_seen >= self.settle
            and t.id not in self._tried
        ]
        if not options:
            return None
        # Unsure names first ("objeto"), then the biggest (closest) one.
        return max(options, key=lambda t: (t.label in ("objeto", "animal"), t.box[2] * t.box[3]))

    def tried(self, track: Track) -> None:
        self._tried.add(track.id)
        if len(self._tried) > 500:
            self._tried = set(list(self._tried)[-200:])

    def asked(self, tracks: Sequence[Track], now: float) -> None:
        self._last = now
        self._count += 1
        self._asked.update(t.id for t in tracks)
        if len(self._asked) > 500:
            self._asked = set(list(self._asked)[-200:])


def crop_box(box: Box, margin: float = 0.35, min_side: float = 0.18) -> Box:
    """A close-up around *box* (with room around it, for context)."""
    x, y, w, h = box
    cw, ch = max(min_side, w * (1 + 2 * margin)), max(min_side, h * (1 + 2 * margin))
    cx, cy = x + w / 2, y + h / 2
    left = min(max(0.0, cx - cw / 2), max(0.0, 1.0 - cw))
    top = min(max(0.0, cy - ch / 2), max(0.0, 1.0 - ch))
    return left, top, min(cw, 1.0), min(ch, 1.0)


# The craniofacial points the server turns into the 175-measure signature
# (same names and mesh indices as openjarvis/faces/signature.py POINTS).
SIGNATURE_POINTS = {
    "tr": 10, "g": 151, "n": 168, "en_d": 133, "en_i": 362, "ex_d": 33, "ex_i": 263,
    "p_d": 468, "p_i": 473, "prn": 1, "sn": 2, "al_d": 64, "al_i": 294, "zy_d": 234,
    "zy_i": 454, "go_d": 172, "go_i": 397, "gn": 152, "ch_d": 61, "ch_i": 291,
    "ls": 0, "li": 17, "sto": 13, "sci_d": 105, "sci_i": 334, "ps_d": 159, "pi_d": 145,
}  # fmt: skip
_POINT_MESH: list[Any] = []


def face_points(image_bytes: bytes, max_faces: int = 6) -> list[dict]:
    """Every face in a photo -> {"box": [x, y, w, h], "points": {...}} in pixels.

    Measured here (MediaPipe is on Windows) so Sergio's server only does
    the maths. [] when MediaPipe or the photo is not available.
    """
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks.python import BaseOptions, vision

        if not _POINT_MESH:
            _POINT_MESH.append(
                vision.FaceLandmarker.create_from_options(
                    vision.FaceLandmarkerOptions(
                        base_options=BaseOptions(
                            model_asset_path=str(ensure_model("face_landmarker.task"))
                        ),
                        num_faces=max_faces,
                        min_face_detection_confidence=0.3,
                    )
                )
            )
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return []
        h, w = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        found = _POINT_MESH[0].detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    except Exception:  # noqa: BLE001 — the geometry is extra evidence only
        log.info("face points unavailable", exc_info=True)
        return []
    out = []
    for marks in found.face_landmarks or []:
        xs = [m.x * w for m in marks]
        ys = [m.y * h for m in marks]
        out.append(
            {
                "box": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)],
                "points": {
                    k: [marks[i].x * w, marks[i].y * h, marks[i].z * w]
                    for k, i in SIGNATURE_POINTS.items()
                },
            }
        )
    return out


class VisionEngine:
    """Runs the detectors on the camera frames in the background."""

    def __init__(
        self,
        frames: Callable[[], Any],
        *,
        objects_fps: float = 5.0,
        faces_fps: float = 10.0,
        finder_factory: Callable[[], Any] = best_finder,
        hands: Callable[[], Sequence[Box]] = lambda: (),
        mesh_factory: Callable[[], Any] = FaceMesh,
        on_head: Callable[[str], None] = lambda _g: None,
    ) -> None:
        self.frames = frames
        self.objects_fps = objects_fps
        self.faces_fps = faces_fps
        self.finder_factory = finder_factory
        self.mesh_factory = mesh_factory
        self.on_head = on_head
        self.hands = hands  # boxes of your hands now (to never call them things)
        self.detector = ""
        from sergio_escritorio.body import FaceStats, PoseFinder, Posture

        self.pose_factory: Callable[[], Any] = PoseFinder
        self.pose: list = []  # 33 body points of the main person
        self.posture = Posture()
        self.face_stats = FaceStats()
        self.distance_cm: float | None = None  # your face to the screen
        self.tracker = Tracker()
        self.faces: list[FaceInfo] = []
        self.mesh = True  # draw/compute the face mesh
        self.error = ""
        self._running = False
        self._head = HeadGestures()

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._objects_loop, daemon=True).start()
        threading.Thread(target=self._faces_loop, daemon=True).start()
        threading.Thread(target=self._pose_loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        self.faces = []

    def _objects_loop(self) -> None:
        try:
            finder = self.finder_factory()
        except Exception as exc:  # noqa: BLE001 — no mediapipe / no model
            log.exception("object detection unavailable")
            self.error = f"Sin detección de objetos: {exc}"
            return
        self.detector = str(getattr(finder, "model", type(finder).__name__))
        if getattr(finder, "gpu", False):
            self.objects_fps = max(self.objects_fps, 15.0)  # the GPU keeps up
        while self._running:
            started = time.monotonic()
            frame = self.frames()
            if frame is not None:
                try:
                    try:
                        hands = list(self.hands())
                    except Exception:  # noqa: BLE001
                        hands = []
                    try:
                        seen = finder.find(frame, hands)
                    except TypeError:  # an older finder without hands
                        seen = finder.find(frame)
                    self.tracker.update(seen, time.monotonic())
                except Exception:  # noqa: BLE001
                    log.exception("object detection failed")
            time.sleep(max(0.0, 1 / self.objects_fps - (time.monotonic() - started)))

    def _pose_loop(self) -> None:
        """Your body (33 points): posture, shoulders, arms, squats."""
        try:
            finder = self.pose_factory()
        except Exception:  # noqa: BLE001 — no pose model: the rest works
            log.info("pose unavailable", exc_info=True)
            return
        while self._running:
            started = time.monotonic()
            frame = self.frames()
            if frame is not None:
                try:
                    self.pose = finder.find(frame)
                    if self.pose:
                        self.posture.feed(self.pose)
                except Exception:  # noqa: BLE001
                    log.exception("pose failed")
            time.sleep(max(0.0, 1 / 8 - (time.monotonic() - started)))

    def _faces_loop(self) -> None:
        try:
            mesh = self.mesh_factory()
        except Exception as exc:  # noqa: BLE001
            log.exception("face mesh unavailable")
            self.error = self.error or f"Sin malla facial: {exc}"
            return
        while self._running:
            started = time.monotonic()
            frame = self.frames() if self.mesh else None
            if frame is not None:
                try:
                    self.faces = mesh.find(frame)
                    if self.faces:
                        face = max(self.faces, key=lambda f: f.box[2] * f.box[3])
                        from sergio_escritorio.body import iris_distance_cm

                        self.face_stats.feed(face.blend, time.monotonic(), face.yaw, face.pitch)
                        self.distance_cm = iris_distance_cm(face.points, frame.shape[1])
                        said = self._head.feed(time.monotonic(), face.yaw, face.pitch)
                        if said:
                            self.on_head(said)
                except Exception:  # noqa: BLE001
                    log.exception("face mesh failed")
            elif not self.mesh:
                self.faces = []
            time.sleep(max(0.0, 1 / self.faces_fps - (time.monotonic() - started)))


__all__ = [
    "SIGNATURE_POINTS",
    "AutoNamer",
    "FaceInfo",
    "FaceMesh",
    "HeadGestures",
    "ObjectFinder",
    "OUTLINES",
    "Seen",
    "Track",
    "Tracker",
    "VisionEngine",
    "clean_detections",
    "contains",
    "crop_box",
    "expressions",
    "face_points",
    "head_angles",
    "iou",
    "label_es",
    "scene_sentence",
    "summary",
]

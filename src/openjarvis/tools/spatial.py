"""Where things are: depth, real distances between objects, and a logic check.

One webcam has no depth sensor, so distance comes from size: a thing whose
real size we know looks smaller the farther it is (pinhole camera: depth =
focal x real size / size in pixels). Every detected object gets its real
size from a table of common objects or from the vision model's own
estimate, then a 3D position, and the distances between them follow.

The same numbers check the names (logic instead of trusting a label): an
object named «silla» that would measure 6 cm, or a «celular» of 80 cm, is
not what the label says, so it is marked as doubtful. Sizes are checked
against the people in the photo too: their faces (about 15 cm) give the
depth of everything around them.
"""

from __future__ import annotations

import math
import unicodedata
from typing import Any

HFOV_DEG = 70.0  # a typical laptop webcam's horizontal field of view
FACE_CM = 15.0  # height of an adult face (chin to hairline), roughly

# Largest real dimension in cm: (typical, min, max).
SIZES: dict[str, tuple[float, float, float]] = {
    "persona": (170, 50, 210), "cara": (15, 11, 20), "mano": (18, 12, 23),
    "celular": (15, 11, 19), "telefono": (15, 11, 19), "control remoto": (18, 12, 26),
    "control": (18, 12, 26), "taza": (10, 7, 14), "vaso": (12, 7, 18), "botella": (24, 12, 35),
    "botella de agua": (22, 15, 30), "lapiz": (17, 8, 20), "boligrafo": (14, 12, 16),
    "labial": (8, 6, 10), "llave": (6, 4, 9), "llaves": (8, 5, 14), "libro": (24, 15, 35),
    "cuaderno": (24, 15, 32), "laptop": (35, 28, 42), "computadora portatil": (35, 28, 42),
    "teclado": (44, 28, 50), "mouse": (11, 8, 13), "raton": (11, 8, 13), "monitor": (60, 35, 90),
    "pantalla": (60, 30, 120), "televisor": (110, 60, 200), "silla": (95, 70, 130),
    "mesa": (120, 60, 250), "escritorio": (130, 80, 200), "lampara": (50, 20, 180),
    "audifonos": (20, 15, 24), "auriculares": (20, 15, 24), "reloj": (4, 3, 30),
    "gafas": (14, 12, 16), "lentes": (14, 12, 16), "gorra": (28, 22, 32), "mochila": (45, 30, 60),
    "planta": (40, 10, 200), "maceta": (20, 8, 50), "cubo de rubik": (5.7, 5, 7),
    "tijeras": (18, 12, 25), "cuchara": (17, 12, 21), "tenedor": (19, 15, 22), "plato": (26, 15, 32),
    "manzana": (8, 6, 10), "banana": (19, 14, 24), "platano": (19, 14, 24), "naranja": (8, 6, 10),
    "perro": (60, 20, 110), "gato": (45, 30, 60), "loro": (35, 15, 100), "cojin": (45, 30, 60),
    "almohada": (60, 40, 75), "puerta": (205, 190, 240), "ventana": (120, 50, 250),
    "tablet": (25, 18, 33), "tableta": (25, 18, 33), "camara": (12, 8, 25), "billetera": (11, 9, 20),
}  # fmt: skip


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def typical(label: str) -> tuple[float, float, float] | None:
    key = plain(label)
    if key in SIZES:
        return SIZES[key]
    for name, size in SIZES.items():  # «taza azul», «celular negro»
        if key.startswith(name + " ") or key.endswith(" " + name):
            return size
    return None


def focal_px(width_px: float, hfov_deg: float = HFOV_DEG) -> float:
    return width_px / (2 * math.tan(math.radians(hfov_deg) / 2))


def locate(items: list[dict[str, Any]], width: int, height: int, hfov_deg: float = HFOV_DEG) -> list[dict[str, Any]]:
    """Add depth (m), a 3D position (m) and a size check to each item.

    Items carry ``box`` [x, y, w, h] as fractions of the image, a ``label``
    and optionally ``size_cm`` (the vision model's estimate)."""
    f = focal_px(width, hfov_deg)
    out = []
    for item in items:
        x, y, w, h = item["box"]
        px = max(w * width, h * height, 1.0)
        known = typical(item.get("label", ""))
        model_cm = item.get("size_cm")
        if item.get("face_box"):  # a person: the face is the best ruler
            fx, fy, fw, fh = item["face_box"]
            size_cm, px = FACE_CM, max(fh * height, 1.0)
        elif known is not None:
            size_cm = known[0]
        elif isinstance(model_cm, (int, float)) and model_cm > 0:
            size_cm = float(model_cm)
        else:
            out.append({**item, "depth_m": None, "pos_m": None, "doubt": ""})
            continue
        depth = f * size_cm / px / 100.0
        cx, cy = (x + w / 2) * width, (y + h / 2) * height
        pos = ((cx - width / 2) * depth / f, (cy - height / 2) * depth / f, depth)
        out.append({**item, "depth_m": round(depth, 2), "pos_m": tuple(round(v, 3) for v in pos), "doubt": ""})
    _check_sizes(out, width, height, f)
    return out


def _check_sizes(items: list[dict[str, Any]], width: int, height: int, f: float) -> None:
    """Logic: the size a label implies must fit what the scene shows.

    The depth of the scene comes from the objects whose size is certain
    (faces, then known things); an object at a similar depth must measure
    what its name says, or its name is doubtful."""
    anchors = [i["depth_m"] for i in items if i.get("depth_m") and (i.get("face_box") or typical(i.get("label", "")))]
    if not anchors:
        return
    scene_depth = sorted(anchors)[len(anchors) // 2]
    for item in items:
        known = typical(item.get("label", ""))
        model_cm = item.get("size_cm")
        x, y, w, h = item["box"]
        px = max(w * width, h * height, 1.0)
        implied_cm = px * scene_depth / f * 100.0  # its size if it sat at the scene's depth
        if known is not None and isinstance(model_cm, (int, float)) and model_cm > 0:
            low, high = known[1], known[2]
            if not (low / 1.6 <= model_cm <= high * 1.6):
                item["doubt"] = f"un {item['label']} no mide {model_cm:.0f} cm"
        elif known is not None and len(anchors) >= 2 and not item.get("face_box"):
            low, high = known[1], known[2]
            if implied_cm > high * 4 or implied_cm < low / 4:
                item["doubt"] = f"por su tamaño no parece un {item['label']}"


def distance_m(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    if not a.get("pos_m") or not b.get("pos_m"):
        return None
    return math.dist(a["pos_m"], b["pos_m"])


def relations(items: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """The closest pairs, with their real distance."""
    pairs = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            d = distance_m(a, b)
            if d is not None:
                pairs.append({"a": a["label"], "b": b["label"], "m": round(d, 2)})
    return sorted(pairs, key=lambda p: p["m"])[:limit]


def spoken(m: float) -> str:
    return f"{round(m * 100)} cm" if m < 1 else f"{m:.1f} m".replace(".", ",")


def describe_relations(pairs: list[dict[str, Any]]) -> str:
    if not pairs:
        return ""
    return "Distancias aproximadas: " + "; ".join(f"{p['a']} a {spoken(p['m'])} de {p['b']}" for p in pairs[:4]) + "."


__all__ = ["SIZES", "describe_relations", "distance_m", "focal_px", "locate", "relations", "typical"]

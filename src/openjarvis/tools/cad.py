"""Professional CAD files (DXF) from images and from Sergio's 3D models.

* ``image_to_dxf``: an image (a logo, a sketch, a silhouette, a part on a
  plain background) vectorised with OpenCV — threshold, contours, the
  polygon simplified to the tolerance asked — and written with ezdxf as
  closed polylines in millimetres (outer contours and holes on their own
  layers), ready for laser cutting, CNC or AutoCAD.
* ``model_to_dxf``: a Blender model drawn like a technical sheet — front,
  side and top views (third-angle layout) from its real edges (only the
  feature edges: outlines and sharp creases, not every triangle), overall
  dimensions with real dimension entities, and a title block.

Units are millimetres (``$INSUNITS`` = 4), so the file opens at real size.
"""

from __future__ import annotations

import io
import math
import time
from typing import Any

LAYERS = {
    "CONTORNO": 7,  # white/black
    "HUECOS": 1,  # red
    "VISTA_FRONTAL": 7,
    "VISTA_LATERAL": 7,
    "VISTA_SUPERIOR": 7,
    "COTAS": 3,  # green
    "CAJETIN": 8,  # grey
}

# Blender: prints each mesh's feature edges (world coordinates, metres) as
# JSON on one line, for model_to_dxf. A feature edge is a boundary edge or
# one whose faces meet at more than ~25 degrees (creases and outlines).
EDGES_SCRIPT = r'''
import bpy, bmesh, json, math
_out = {}
_deps = bpy.context.evaluated_depsgraph_get()
for _o in bpy.context.scene.objects:
    if _o.type != "MESH" or _o.get("sergio_cutter") or _o.hide_render:
        continue
    _bm = bmesh.new()
    _bm.from_object(_o, _deps)
    _bm.transform(_o.matrix_world)
    _edges = []
    for _e in _bm.edges:
        if len(_e.link_faces) != 2 or _e.calc_face_angle(0.0) > math.radians(25):
            _a, _b = _e.verts
            _edges.append([round(c, 5) for c in (*_a.co, *_b.co)])
    _bm.free()
    if _edges:
        _out[_o.name] = _edges[:20000]
print("SERGIO_EDGES " + json.dumps(_out))
'''


def _doc() -> Any:
    import ezdxf

    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4  # millimetres
    doc.header["$MEASUREMENT"] = 1  # metric
    for name, colour in LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name, color=colour)
    return doc


def _save(doc: Any) -> bytes:
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def vectorise(image: bytes, tolerance_px: float = 1.5, min_area_px: float = 30.0,
              invert: bool | None = None) -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]], tuple[int, int]]:
    """The image's shapes as polygons (pixel coordinates, y up): outer
    contours and holes. A transparent PNG uses its alpha; otherwise Otsu
    picks the threshold and the darker side counts as the shape."""
    import cv2
    import numpy as np

    data = np.frombuffer(image, np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("No pude leer la imagen.")
    if img.ndim == 3 and img.shape[2] == 4 and int(img[:, :, 3].min()) < 250:
        mask = (img[:, :, 3] > 127).astype(np.uint8) * 255
    else:
        gray = img if img.ndim == 2 else cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        border = np.concatenate([mask[0], mask[-1], mask[:, 0], mask[:, -1]])
        dark_shape = invert if invert is not None else float(border.mean()) > 127  # light background: shapes are dark
        if dark_shape:
            mask = 255 - mask
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    height, width = mask.shape[:2]
    outer: list[list[tuple[float, float]]] = []
    holes: list[list[tuple[float, float]]] = []
    for i, contour in enumerate(contours):
        if cv2.contourArea(contour) < min_area_px:
            continue
        approx = cv2.approxPolyDP(contour, tolerance_px, True)
        if len(approx) < 3:
            continue
        pts = [(float(p[0][0]), float(height - p[0][1])) for p in approx]
        is_hole = hierarchy is not None and hierarchy[0][i][3] != -1
        (holes if is_hole else outer).append(pts)
    return outer, holes, (width, height)


def image_to_dxf(image: bytes, width_mm: float = 100.0, tolerance_px: float = 1.5,
                 invert: bool | None = None) -> tuple[bytes, dict[str, Any]]:
    """An image vectorised into a DXF at *width_mm* wide. Returns the file
    and a summary (shapes, holes, size, vertex count)."""
    outer, holes, (w, h) = vectorise(image, tolerance_px, invert=invert)
    if not outer:
        raise ValueError("No encontré formas en la imagen (pruebe con fondo liso y buen contraste).")
    xs = [x for poly in outer for x, _ in poly]
    ys = [y for poly in outer for _, y in poly]
    x0, y0 = min(xs), min(ys)
    scale = width_mm / max(max(xs) - x0, 1.0)
    doc = _doc()
    msp = doc.modelspace()
    count = 0
    for layer, polys in (("CONTORNO", outer), ("HUECOS", holes)):
        for poly in polys:
            msp.add_lwpolyline([((x - x0) * scale, (y - y0) * scale) for x, y in poly], close=True,
                               dxfattribs={"layer": layer})
            count += len(poly)
    size = ((max(xs) - x0) * scale, (max(ys) - y0) * scale)
    _overall_dims(msp, 0.0, 0.0, size[0], size[1])
    return _save(doc), {"shapes": len(outer), "holes": len(holes), "width_mm": round(size[0], 1),
                        "height_mm": round(size[1], 1), "vertices": count, "pixels": [w, h]}


def _overall_dims(msp: Any, x: float, y: float, w: float, h: float) -> None:
    """Overall width (below) and height (left) as real dimension entities."""
    gap = max(w, h) * 0.08 + 5
    text = max(w, h) * 0.035 + 1.5  # readable at any size
    style = {"dimtxt": text, "dimasz": text * 0.8, "dimexo": text * 0.4, "dimexe": text * 0.5,
             "dimgap": text * 0.3, "dimdec": 1, "dimdsep": ord("."), "dimlfac": 1.0}
    msp.add_linear_dim(base=(x, y - gap), p1=(x, y), p2=(x + w, y), dimstyle="EZDXF", override=style,
                       dxfattribs={"layer": "COTAS"}).render()
    msp.add_linear_dim(base=(x - gap, y), p1=(x, y), p2=(x, y + h), angle=90, dimstyle="EZDXF",
                       override=style, dxfattribs={"layer": "COTAS"}).render()


def parse_edges(log: str) -> dict[str, list[list[float]]]:
    """The feature edges Blender printed (EDGES_SCRIPT), in metres."""
    import json

    for line in log.splitlines():
        if line.startswith("SERGIO_EDGES "):
            return json.loads(line[len("SERGIO_EDGES "):])
    raise ValueError("Blender no devolvió las aristas del modelo.")


def _project(edges: list[list[float]], axes: tuple[int, int]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """3D edges -> 2D segments on a view plane (mm), without duplicates or
    edges seen end-on."""
    seen: set[tuple[int, ...]] = set()
    out = []
    a, b = axes
    for e in edges:
        p = (e[a] * 1000, e[b] * 1000)
        q = (e[3 + a] * 1000, e[3 + b] * 1000)
        if math.dist(p, q) < 0.05:
            continue
        key = tuple(sorted((round(p[0], 1), round(p[1], 1), round(q[0], 1), round(q[1], 1))))
        if key in seen:
            continue
        seen.add(key)
        out.append((p, q))
    return out


def model_to_dxf(edges: dict[str, list[list[float]]], name: str = "Modelo", author: str = "Sergio") -> tuple[bytes, dict[str, Any]]:
    """A three-view technical drawing of a Blender model (third-angle:
    front bottom left, top above it, right side to its right), with overall
    dimensions and a title block. Returns the DXF and a summary."""
    all_edges = [e for es in edges.values() for e in es]
    if not all_edges:
        raise ValueError("El modelo no tiene aristas que dibujar.")
    lo = [min(min(e[i], e[i + 3]) for e in all_edges) * 1000 for i in range(3)]
    hi = [max(max(e[i], e[i + 3]) for e in all_edges) * 1000 for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    gap = max(size) * 0.35 + 20
    doc = _doc()
    msp = doc.modelspace()
    views = (
        ("VISTA_FRONTAL", (0, 2), (0.0, 0.0), (lo[0], lo[2]), (size[0], size[2])),
        ("VISTA_SUPERIOR", (0, 1), (0.0, size[2] + gap), (lo[0], lo[1]), (size[0], size[1])),
        ("VISTA_LATERAL", (1, 2), (size[0] + gap, 0.0), (lo[1], lo[2]), (size[1], size[2])),
    )
    segments = 0
    for layer, axes, (ox, oy), (mx, my), (w, h) in views:
        for (p, q) in _project(all_edges, axes):
            msp.add_line((p[0] - mx + ox, p[1] - my + oy), (q[0] - mx + ox, q[1] - my + oy),
                         dxfattribs={"layer": layer})
            segments += 1
        _overall_dims(msp, ox, oy, w, h)
        msp.add_text(layer.replace("_", " ").title(), height=max(size) * 0.03 + 2,
                     dxfattribs={"layer": "COTAS"}).set_placement((ox, oy + h + gap * 0.15))
    _title_block(msp, size, name, author, origin=(size[0] + gap, size[2] + gap))
    return _save(doc), {"views": 3, "segments": segments, "size_mm": [round(v, 1) for v in size],
                        "parts": len(edges)}


def _title_block(msp: Any, size: list[float], name: str, author: str, origin: tuple[float, float]) -> None:
    """A simple title block: name, overall size, scale, units, date, author."""
    w = max(size) * 0.9 + 60
    h = w * 0.32
    x, y = origin
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": "CAJETIN"})
    text_h = h * 0.11
    lines = [
        name,
        f"Medidas: {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm",
        "Escala 1:1 · Unidades: mm · Diédrico (3er diedro)",
        f"{time.strftime('%Y-%m-%d')} · {author}",
    ]
    for i, line in enumerate(lines):
        msp.add_text(line, height=text_h * (1.4 if i == 0 else 1.0),
                     dxfattribs={"layer": "CAJETIN"}).set_placement((x + h * 0.1, y + h - (i + 1) * h * 0.22))


def preview_png(data: bytes, dpi: int = 110) -> bytes:
    """The drawing as a PNG (white sheet), to show the user or the vision check."""
    import ezdxf
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    fig = plt.figure(figsize=(11, 8.5))
    ax = fig.add_axes((0, 0, 1, 1))
    config = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=config).draw_layout(doc.modelspace())
    buf = io.BytesIO()
    fig.savefig(buf, dpi=dpi, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def check_dxf(data: bytes) -> dict[str, int]:
    """Re-open a DXF and count what is inside (for tests and the user)."""
    import ezdxf

    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    counts: dict[str, int] = {}
    for entity in doc.modelspace():
        counts[entity.dxftype()] = counts.get(entity.dxftype(), 0) + 1
    return counts


__all__ = ["EDGES_SCRIPT", "check_dxf", "image_to_dxf", "model_to_dxf", "parse_edges", "preview_png", "vectorise"]

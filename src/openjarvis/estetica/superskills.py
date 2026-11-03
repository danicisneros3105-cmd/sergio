"""The 25 superskills, read from the bundled skill, and choosing the few that fit."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

FILE = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "bundled"
    / "criterio-estetico"
    / "superskills.md"
)

# words that call each superskill (plain, without accents)
KEYWORDS: Dict[int, tuple] = {
    1: ("espacio negativo", "vacio", "aire", "minimal", "producto", "frasco", "limpio"),
    2: ("balance", "equilibrio", "asimetr", "composicion", "masa"),
    3: ("tension", "flotar", "levita", "hueco", "junta"),
    4: ("aureo", "proporcion", "reticula", "tercios", "formato"),
    5: (
        "jerarquia",
        "titulo",
        "cartel",
        "poster",
        "anuncio",
        "landing",
        "pagina",
        "pantalla",
    ),
    6: ("luz suave", "difusa", "ventana", "catalogo", "ceramica", "limpia", "dia"),
    7: ("penumbra", "oscuro", "dramatic", "claroscuro", "noche", "misterio", "lujo"),
    8: ("monocrom", "blanco y negro", "negro sobre negro", "tonal", "gris"),
    9: ("paleta", "color", "colores", "sobrio", "tonos"),
    10: ("metal", "laton", "oro", "plata", "acero", "cromo", "reloj", "joya"),
    11: (
        "vidrio",
        "cristal",
        "frasco",
        "perfume",
        "botella",
        "transparente",
        "liquido",
    ),
    12: ("ceramica", "piedra", "marmol", "travertino", "yeso", "mate", "hormigon"),
    13: ("caja", "packaging", "empaque", "papel", "carton", "etiqueta", "estuche"),
    14: ("tipografia", "letra", "fuente", "texto", "logo", "marca"),
    15: ("tipografias", "fuentes", "pareja", "combinar letras", "familia tipografica"),
    16: (
        "revista",
        "editorial",
        "maqueta",
        "reticula",
        "layout",
        "documento",
        "presentacion",
    ),
    17: ("unboxing", "apertura", "abrir la caja", "ritual", "regalo"),
    18: ("diseno industrial", "producto", "carcasa", "render", "objeto", "superficie"),
    19: ("lampara", "luminaria", "iluminacion", "colgante", "aplique", "encendida"),
    20: (
        "bodegon",
        "still life",
        "foto de producto",
        "fotografia de producto",
        "campana",
    ),
    21: ("sombra", "sombras", "apoyado", "mesa"),
    22: ("serie", "coleccion", "gama", "varios", "grid de productos", "catalogo"),
    23: ("minimal", "minimalista", "simple", "menos"),
    24: ("identidad", "marca", "branding", "sistema", "redes", "campana"),
    25: (),
}


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def all_skills() -> Dict[int, Dict[str, str]]:
    text = FILE.read_text("utf-8")
    out: Dict[int, Dict[str, str]] = {}
    for block in re.split(r"(?m)^(?=## Superskill )", text):
        m = re.match(r"## Superskill (\d+): (.+)", block)
        if not m:
            continue
        n = int(m.group(1))
        sections = dict(
            re.findall(r"\*\*([^*]+?)\.\*\* (.+?)(?=\n\n\*\*|\Z)", block, re.S)
        )
        out[n] = {"numero": str(n), "nombre": m.group(2).strip(), "texto": block.strip(), **{
            "parametros": next((v for k, v in sections.items() if k.startswith("Prompting")), ""),
            "rechazo": next((v for k, v in sections.items() if k.startswith("Patrón")), ""),
            "matriz": next((v for k, v in sections.items() if k.startswith("Matriz")), ""),
        }}  # fmt: skip
    return out


def pick(brief: str, n: int = 3) -> List[int]:
    """The superskills that fit *brief*, best first; at most *n* plus the curation (25)."""
    text = _plain(brief)
    scores = {
        k: sum(1 for w in words if w in text) for k, words in KEYWORDS.items() if words
    }
    best = [
        k for k, v in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0
    ][:n]
    if not best:
        best = [1, 5, 9][:n]  # composition, hierarchy, palette: always useful
    return best + [25]


# Subject-agnostic directions for an image prompt (the examples in the
# superskills name objects; these never add an object the person did not ask for).
DIRECTIVES: Dict[int, str] = {
    1: "generous negative space (55-75% of the frame) as one calm background field",
    2: "asymmetric balance, main subject off-centre on a golden line with a small counterweight",
    3: "no accidental tangents between shapes or with the frame edge",
    4: "main subject on golden-ratio lines",
    5: "one clear focal point, nothing competing with it",
    6: "large soft key light from one side, soft-edged shadows, no clipped highlights",
    7: "low-key chiaroscuro, a single pool of light on the subject, shadows keep detail, no fog, no glow",
    8: "tonal monochrome, separation by value and texture rather than colour",
    9: "restrained low-saturation palette drawn from real materials, at most one small accent colour",
    10: "metal reflections shaped by large white and black cards, no lens flare",
    11: "glass with crisp continuous edges and believable refraction, no reflections of a room",
    12: "matte mineral surfaces with fine visible texture under raking light",
    13: "paper and print finishes revealed by raking light, precise corners",
    14: "no text or lettering in the image",
    15: "no text or lettering in the image",
    16: "leave clean space for a layout, no text in the image",
    17: "interior of the open box lit and readable",
    18: "continuous surface reflections, consistent radii, precise parting lines",
    19: "lamp diffuser texture readable and unclipped, warm 2700 K glow, room 2-4 stops darker",
    20: "at most five objects, each with a purpose, no scattered props",
    21: "dense contact shadow and a single light direction",
    22: "same light, camera height and surface as the rest of the series",
    23: "minimal: no element without a function",
    24: "consistent house style",
}


def brief_for_images(brief: str, n: int = 3) -> str:
    """A short art-direction note for an image prompt, from the superskills that
    fit *brief* (models follow short notes; never the 25 at once)."""
    text = _plain(brief)
    if not any(w in text for words in KEYWORDS.values() for w in words):
        return ""  # a brief with no design intent (a meme, a crowded party) keeps its own look
    picked = [k for k in pick(brief, n) if k in DIRECTIVES][:n]
    return "; ".join(DIRECTIVES[k] for k in picked)


__all__ = ["DIRECTIVES", "KEYWORDS", "all_skills", "brief_for_images", "pick"]

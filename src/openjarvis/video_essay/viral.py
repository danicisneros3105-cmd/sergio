"""What makes the owner's reference Shorts work, measured, and the rules that
follow from it (owner, 3 Nov 2026: «Sergio debe conocer las tendencias al pie
de la letra: qué música usar, cuándo usarla, qué videos poner, qué clips, de
qué películas…»).

``REFERENCIAS`` holds what was measured on 3 Nov 2026 from the public data of
the owner's references (``referencias.json``): views, likes, comments,
length, the format, and from the transcripts the narration pace (words per
second), the length of the opening line and where the turn lands. Only
numbers and the structure are kept, never their words beyond the title.
The second-by-second picture analysis at 30 fps (cuts, zoom, colour) runs on
the owner's computer (``escuela.py``); this module is what can be read from
the outside, and says so.

``guide(idea, genre)`` writes a short note for the director and the planner:
which of the measured formats fits, its timing, and the music cues. The music
map is craft practice (it is labelled as such), not a measurement.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List

MEASURED_ON = "2026-11-03"

# Public numbers on the measuring day; «wps»: narrated words per second.
REFERENCIAS: List[Dict[str, object]] = [
    {"id": "DQnqfT0LO3A", "formato": "clip-reencuadrado", "vistas": 22_435_248, "me_gusta": 485_289,
     "comentarios": 682, "segundos": 40, "titulo": "How Chris Pratt Was Stealing Food",
     "nota": "momento de un programa de entrevistas, 9:16 con seguimiento de cara, color y subtítulos"},
    {"id": "bHDHsR9w_ME", "formato": "clip-reencuadrado", "vistas": 17_418_268, "me_gusta": 247_212,
     "comentarios": 572, "segundos": 25, "titulo": "IShowSpeed Really SENT His Brother $1!",
     "nota": "momento de un directo; el título promete el remate"},
    {"id": "S0G6pqnZgqc", "formato": "escena-de-pelicula", "vistas": 8_940_136, "me_gusta": 92_382,
     "comentarios": 125, "segundos": 38, "titulo": "$4 auction ended up $50K | White Chicks (2004)",
     "nota": "una escena de comedia entera con el giro en números en el título y la película con su año"},
    {"id": "CmzZkmPLCSU", "formato": "escena-de-serie", "vistas": 364_165, "me_gusta": 7_958,
     "comentarios": 11, "segundos": 43, "titulo": "MARGE LE REGALA UN CELULAR A BART !?",
     "nota": "escena de serie animada doblada al español, título en pregunta"},
    {"id": "ZD1saam9tKY", "formato": "lista-de-datos-raros", "vistas": 1_754_233, "me_gusta": 32_479,
     "comentarios": 76, "segundos": 39, "titulo": "Weirdly LEGAL Things You Can Do on a Cruise",
     "wps": 3.0, "frase_inicial_palabras": 9, "puntos": 3,
     "nota": "el título se dice en la primera frase; tres datos con nombre o cifra; cierra con una broma"},
    {"id": "tFiLRzIjvM4", "formato": "lista-de-datos-raros", "vistas": 1_698_284, "me_gusta": 31_405,
     "comentarios": 68, "segundos": 30, "titulo": "These outfits were never meant to be worn easily",
     "wps": 3.0, "frase_inicial_palabras": 9, "puntos": 4,
     "nota": "cuatro casos reales con nombre propio; cada uno termina en una consecuencia física"},
    {"id": "jXq9de0aJuM", "formato": "mini-historia-con-giro", "vistas": 2_435_027, "me_gusta": 48_646,
     "comentarios": 737, "segundos": 27, "titulo": "School cafeteria scam", "wps": 3.7, "puntos": 0,
     "nota": "empieza en la acción (segundo 0), conflicto a los 7 s, giro a los 15 s, castigo al final; "
             "la historia que provoca opinión trae diez veces más comentarios por vista"},
    {"id": "dFbUovi4WNk", "formato": "ranking-sin-narrador", "vistas": 2_700_977, "me_gusta": 19_219,
     "comentarios": 35, "segundos": 25, "titulo": "Ranking Craziest Rock Thrown In Water",
     "nota": "sin voz en off; números en pantalla de menor a mayor; el audio es el de los clips"},
    {"id": "p7LDk4D3Q3U", "formato": "animacion-musical", "vistas": 11_773_135, "me_gusta": 578_554,
     "comentarios": 16_104, "segundos": 207, "titulo": "The Turning Point",
     "nota": "sátira sin diálogo; una canción lleva todo el corto; una sola idea que escala"},
    {"id": "3pxrECZYEAA", "formato": "animacion-musical", "vistas": 4_482_407, "me_gusta": 129_768,
     "comentarios": 2_970, "segundos": 467, "titulo": "Cosmohedron | Animated Short",
     "nota": "viaje surrealista; música y diseño de sonido hechos por personas distintas, al nivel de la imagen"},
]  # fmt: skip

# Not readable from here (Instagram needs a session): measured on his PC.
PENDIENTES_EN_SU_PC = [
    "https://www.instagram.com/reels/DdjwUyxBc5k/",
    "https://www.instagram.com/p/DfI65MZRCkn/",
    "https://www.instagram.com/reels/Del0IKQCjQL/",
    "https://www.instagram.com/reels/De3IuvyhMVD/",
    "https://www.instagram.com/reels/De79fyPBf5j/",
]

# What each format asks for, from the measures above.
FORMATOS: Dict[str, Dict[str, object]] = {
    "lista-de-datos-raros": {
        "nombre": "Lista de datos raros narrada",
        "palabras": ("cosas", "datos", "legal", "raro", "raros", "sabias", "things", "facts", "weird", "curiosidades"),
        "segundos": (30, 40), "wps": 3.0, "puntos": (3, 4),
        "reglas": (
            "La primera frase ES el título dicho en voz alta (unas 9 palabras): nada antes.",
            "3 o 4 datos; cada uno con un nombre propio o una cifra y una consecuencia concreta.",
            "Un dato por toma o dos tomas; imagen literal de lo que se dice (SAY = SHOW).",
            "El último remata con una broma o un giro de 1 frase; no hay despedida ni «suscríbete».",
        ),
    },
    "mini-historia-con-giro": {
        "nombre": "Mini historia con giro",
        "palabras": ("historia", "estafa", "scam", "le paso", "story", "venganza", "karma", "se vengo"),
        "segundos": (25, 35), "wps": 3.6, "puntos": (0, 0),
        "reglas": (
            "Empieza en la acción en el segundo 0 (sin presentación).",
            "Conflicto antes del segundo 7, giro hacia el segundo 15, castigo o premio en la última frase.",
            "Frases largas de narrador rápido (~3,6 palabras por segundo); diálogo citado en 1 línea.",
            "Que el final deje una opinión dividida: eso trae comentarios.",
        ),
    },
    "ranking-sin-narrador": {
        "nombre": "Ranking sin narrador",
        "palabras": ("ranking", "top", "mejores", "peores", "mas loco", "craziest", "best", "worst"),
        "segundos": (20, 30), "wps": 0.0, "puntos": (4, 6),
        "reglas": (
            "Sin voz en off: el número grande en pantalla y el sonido real de cada clip.",
            "De menor a mayor; el último es el más fuerte y dura más.",
            "Corte al golpe de la música en cada número.",
        ),
    },
    "clip-reencuadrado": {
        "nombre": "Momento reencuadrado",
        "palabras": ("momento", "entrevista", "podcast", "stream", "directo", "show", "clip"),
        "segundos": (25, 45), "wps": 0.0, "puntos": (0, 0),
        "reglas": (
            "Un solo momento con principio y remate; el título promete el remate sin contarlo.",
            "9:16 siguiendo la cara, subtítulos dinámicos, color corregido.",
            "Solo con material propio, con permiso o con comentario que lo transforme (ver derechos.py).",
        ),
    },
    "escena-de-pelicula": {
        "nombre": "Escena de película o serie",
        "palabras": ("pelicula", "escena", "serie", "movie", "scene", "film"),
        "segundos": (25, 45), "wps": 0.0, "puntos": (0, 0),
        "reglas": (
            "Título con el giro en números o en pregunta y «| Película (año)».",
            "Es el formato con más reclamos: solo con comentario propio encima y trozos cortos (derechos.py).",
        ),
    },
    "animacion-musical": {
        "nombre": "Animación llevada por la música",
        "palabras": ("animacion", "animado", "animated", "corto animado", "cartoon"),
        "segundos": (60, 480), "wps": 0.0, "puntos": (0, 0),
        "reglas": (
            "Una sola idea que escala de principio a fin; sin diálogo o casi.",
            "La música manda: los cortes caen en los compases y el clímax en el estribillo o el drop.",
            "El diseño de sonido cuenta tanto como la imagen: cada objeto suena.",
        ),
    },
}  # fmt: skip

# The music map (craft practice, not a measurement).
MUSICA = (
    "Gancho (0-1,5 s): sin música o un solo golpe; la música entra en el primer tiempo después de la primera frase.",
    "Con narrador: instrumental sin letra (la letra pelea con las palabras), baja bajo la voz.",
    "Antes del giro o del remate: la música se corta 0,3-0,6 s (silencio), se dice el remate, y vuelve o cae el drop.",
    "Sin narrador (ranking, animación): la música alta y los cortes en el tiempo; lo más fuerte en el drop.",
    "Canciones de moda: se ponen al subir, desde la biblioteca de sonidos de la propia red (TikTok, Reels, Shorts), "
    "que tiene la licencia; en el archivo, Sergio usa solo música con licencia para ganar dinero.",
)


def _plain(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def pick(idea: str, genre: str = "") -> str:
    """The measured format that fits *idea* best (a list of facts by default)."""
    text = " " + re.sub(r"[^a-z0-9 ]+", " ", _plain(idea)) + " "
    if genre == "animacion":
        return "animacion-musical"
    best, hits = "lista-de-datos-raros", 0
    for key, f in FORMATOS.items():
        n = sum(1 for w in f["palabras"] if f" {w}" in text)
        if n > hits:
            best, hits = key, n
    return best


def evidence(fmt: str) -> List[Dict[str, object]]:
    return [
        r
        for r in REFERENCIAS
        if r["formato"] == fmt
        or (fmt.startswith("escena") and "escena" in str(r["formato"]))
    ]


def guide(idea: str, genre: str = "", vertical: bool = True) -> str:
    """The note for the director and the planner (a few lines, never all)."""
    if not vertical and genre != "animacion":
        return ""
    fmt = pick(idea, genre)
    f = FORMATOS[fmt]
    refs = evidence(fmt)
    proof = "; ".join(
        f"{r['titulo']} ({int(r['vistas']) / 1e6:.1f} M vistas, {r['segundos']} s)"
        for r in refs[:2]
    )
    lo, hi = f["segundos"]
    lines = [
        f'<shorts_virales formato="{fmt}" medido="{MEASURED_ON}">',
        f"Formato que mejor encaja: {f['nombre']} ({lo}-{hi} s). Medido en las referencias del dueño: {proof}.",
    ]
    if f["wps"]:
        lines.append(f"Ritmo de narración medido: ~{f['wps']} palabras por segundo.")
    lines += [f"- {r}" for r in f["reglas"]]
    lines.append("Música: " + " ".join(MUSICA[:4]))
    lines.append(
        "Lo que se muestra se toma de material propio, libre o con comentario; nunca se inventa un dato."
    )
    lines.append("</shorts_virales>")
    return "\n".join(lines)  # fmt: skip


def report() -> str:
    """The analysis for a person: what was measured, per format."""
    rows = []
    for key, f in FORMATOS.items():
        refs = evidence(key)
        if not refs:
            continue
        rows.append(f"{f['nombre']}:")
        for r in refs:
            ratio = 100 * int(r["me_gusta"]) / max(1, int(r["vistas"]))
            talk = 1e6 * int(r["comentarios"]) / max(1, int(r["vistas"]))
            rows.append(f"  - «{r['titulo']}»: {int(r['vistas']):,} vistas, {r['segundos']} s, "
                        f"{ratio:.1f} % me gusta, {talk:.0f} comentarios por millón. {r['nota']}.")  # fmt: skip
    rows.append(
        "Pendiente en su PC (Instagram pide sesión): " + ", ".join(PENDIENTES_EN_SU_PC)
    )
    return "\n".join(rows)


__all__ = ["FORMATOS", "MUSICA", "REFERENCIAS", "guide", "pick", "report"]

"""Clips of films and series: what the law really allows and what lowers the
risk (owner, 3 Nov 2026: «vacíos legales para poner clips de películas»).

There is **no loophole that guarantees** anything, and Sergio never says there
is. What exists:

* **Fair use** (United States, 17 U.S.C. § 107) and the **right of quotation**
  (derecho de cita, in most Spanish-speaking countries) are *defences* a
  judge weighs case by case: the purpose (commentary, criticism, parody,
  teaching: transformation), the nature of the work, how much is taken and
  whether it is the heart of it, and the harm to the market for the original.
* The «Copyright Disclaimer Under Section 107…» text many channels paste in
  their descriptions has **no legal effect**: it changes nothing.
* Platforms match automatically (YouTube Content ID, Meta Rights Manager)
  whatever the law says: the usual result is a **claim** (the money goes to
  the owner of the film), sometimes a block, and a **strike** when the owner
  asks for a takedown. A claim can be disputed when the use is transformative.

What lowers the risk (never to zero): short pieces, commentary or narration
that changes the meaning, Sergio's own structure (ranking, analysis), never
the climax or the whole scene, never the film's own music under it, a credit
(courtesy, not a licence). Reframing, colour and captions **alone** do not
make a use transformative.

What carries **no** risk: public-domain films (in the US, published before
1931 as of 2026) and films with a free licence, such as the Blender Foundation
open movies (CC BY).

``review`` checks the film and web clips of a finished plan against these
rules and says the risk in plain words; it never says «legal».
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

MAX_PIECE = 5.0  # seconds of one clip in a row
MAX_SAME_FILM = 15.0  # seconds of one film in the whole video
PUBLIC_DOMAIN_YEAR = 1931  # published in the US before this: public domain (2026)

FREE_FILMS = (
    {"titulo": "Big Buck Bunny (2008)", "licencia": "CC BY 3.0, Blender Foundation"},
    {"titulo": "Sintel (2010)", "licencia": "CC BY 3.0, Blender Foundation"},
    {"titulo": "Tears of Steel (2012)", "licencia": "CC BY 3.0, Blender Foundation"},
    {"titulo": "Elephants Dream (2006)", "licencia": "CC BY 2.5, Blender Foundation"},
    {"titulo": "Spring (2019)", "licencia": "CC BY 4.0, Blender Foundation"},
    {
        "titulo": "Night of the Living Dead (1968)",
        "licencia": "Dominio público en EE. UU. (sin aviso de copyright)",
    },
    {"titulo": "Nosferatu (1922)", "licencia": "Dominio público en EE. UU."},
    {"titulo": "The General (1926)", "licencia": "Dominio público en EE. UU."},
)

RULES = (
    "Trozos de pocos segundos (5 como mucho seguidos, 15 de una misma película en todo el video).",
    "Encima o entre los trozos, su comentario o su narración: que el video diga algo propio.",
    "Nunca la escena entera, el clímax ni el final; nunca la música de la película debajo.",
    "Crédito con título y año (es cortesía, no una licencia).",
    "El texto «Copyright Disclaimer Under Section 107» no protege: no lo use como escudo.",
    "Sin riesgo: películas de dominio público o con licencia libre (las de la Blender Foundation).",
)


def review(clips: Iterable[Dict[str, Any]], narrated: bool) -> Dict[str, Any]:
    """*clips*: ``{"film": title or "", "seconds": float, "free": bool}`` for
    each film or web clip in the cut. Returns the risk and what to change."""
    pieces = [c for c in clips if not c.get("free")]
    if not pieces:
        return {"riesgo": "ninguno", "avisos": [], "segundos": 0.0}
    advice: List[str] = []
    long = [c for c in pieces if float(c.get("seconds") or 0) > MAX_PIECE]
    if long:
        advice.append(
            f"{len(long)} trozo(s) de más de {MAX_PIECE:.0f} s seguidos: córtelos."
        )
    per_film: Dict[str, float] = {}
    for c in pieces:
        key = str(c.get("film") or "").strip().lower()
        if key:
            per_film[key] = per_film.get(key, 0.0) + float(c.get("seconds") or 0)
    heavy = [k for k, s in per_film.items() if s > MAX_SAME_FILM]
    if heavy:
        advice.append(
            f"Más de {MAX_SAME_FILM:.0f} s de una misma película ({', '.join(heavy[:3])})."
        )
    if not narrated:
        advice.append(
            "Sin narración ni comentario propio: es el caso que más reclamos recibe."
        )
    total = round(sum(float(c.get("seconds") or 0) for c in pieces), 1)
    level = (
        "alto"
        if (not narrated or heavy)
        else ("medio" if long or total > 20 else "bajo")
    )
    return {"riesgo": level, "avisos": advice, "segundos": total}


def line(result: Dict[str, Any]) -> str:
    """One sentence for the person (never «legal», never «seguro»)."""
    if result.get("riesgo") in (None, "ninguno"):
        return ""
    text = f"Riesgo de reclamo por clips de terceros: {result['riesgo']} ({result['segundos']} s de material ajeno)."
    if result.get("avisos"):
        text += " " + " ".join(result["avisos"])
    return (
        text + " Un reclamo suele mandar el dinero del video al dueño de la película."
    )


__all__ = ["FREE_FILMS", "MAX_PIECE", "MAX_SAME_FILM", "RULES", "line", "review"]

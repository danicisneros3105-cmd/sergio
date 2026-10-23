"""What makes each Node different in what it *does*, not only in how it talks.

The four had complete characters (``team.py``) but the same tools, the same
model and the same kind of answer, so they hardly differed in practice. Now
each one has:

* **its own instruments**, always in its hands: Hous makes pictures and
  videos, Manchas searches and reads the web, Tennessee calculates and
  forecasts, Rihno reads the calendar, the files and the memory. None of
  these changes anything of the owner's; whatever does (files, code, his
  PC) still goes through his rules;
* **its own way of thinking**: Tennessee thinks long and coldly (high
  effort, low temperature), Hous loosely (more temperature), Rihno fast;
* **its own deliverable, checked by code**: Tennessee always gives a
  verdict with numbers, Manchas cites its sources, Hous shows the visual,
  Rihno says first what is ready. An answer without it goes back once with
  «te faltó…» before it reaches the owner.

This is not retraining the model (that needs data and a training run); it
is everything short of that, and it is enforced, not only asked for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Tuple

_VISUAL = re.compile(
    r"\b(imagen|im[aá]genes|foto|logo|logotipo|dise[ñn]\w*|p[oó]ster|portada|"
    r"banner|ilustra\w*|identidad|visual\w*|video|v[ií]deo|miniatura|mockup|maqueta)\b",
    re.IGNORECASE,
)
_LINK = re.compile(r"https?://\S+")
_MEDIA = "/v1/creator/media/"
_NUMBER = re.compile(r"\d")


@dataclass(frozen=True)
class Specialty:
    key: str
    does: str  # one line for the page: what only this Node does
    toolkit: Tuple[str, ...]
    effort: str  # thinking: "low" | "medium" | "high"
    temperature: float
    check: Callable[[str, str, frozenset], Optional[str]]


def _rihno(request: str, answer: str, used: frozenset) -> Optional[str]:
    first = answer.strip().splitlines()[0] if answer.strip() else ""
    if not first or len(first) > 180:
        return (
            "empezar con UNA línea corta que diga qué está listo (o qué falta), "
            "y después el detalle"
        )
    return None


def _manchas(request: str, answer: str, used: frozenset) -> Optional[str]:
    searched = bool(used & {"web_search", "http_request", "browser_navigate"})
    if searched and len(set(_LINK.findall(answer))) < 2:
        return (
            "citar al menos dos fuentes con su enlace (https://…) de lo que "
            "encontraste, al final, bajo «Fuentes:»"
        )
    return None


def _hous(request: str, answer: str, used: frozenset) -> Optional[str]:
    if not _VISUAL.search(request):
        return None
    if _MEDIA in answer or used & {"image_generate", "video_create"}:
        return None
    return (
        "mostrar el visual de verdad: créalo con image_generate (o video_create "
        "si es un video) y pon la imagen en tu respuesta, no solo la describas"
    )


def _tennessee(request: str, answer: str, used: frozenset) -> Optional[str]:
    if not re.search(r"(?im)^\W*veredicto\s*:", answer):
        return (
            "terminar con una línea «Veredicto: …» que diga sin rodeos si conviene "
            "o no y por qué"
        )
    if not _NUMBER.search(answer):
        return "poner números concretos (cifras, porcentajes, costos o plazos)"
    return None


SPECIALTIES = {
    "rihno": Specialty(
        key="rihno",
        does="Ordena sus archivos y su agenda, reparte el trabajo y le entrega todo listo.",
        toolkit=(
            "calendar_upcoming",
            "calendar_search",
            "knowledge_search",
            "memory_search",
            "file_read",
        ),
        effort="low",
        temperature=0.4,
        check=_rihno,
    ),
    "manchas": Specialty(
        key="manchas",
        does="Investiga a fondo en internet y arma campañas, con fuentes.",
        toolkit=("web_search", "http_request"),
        effort="medium",
        temperature=0.8,
        check=_manchas,
    ),
    "hous": Specialty(
        key="hous",
        does="Diseña: hace imágenes, logos y videos de verdad, no solo ideas.",
        toolkit=("image_generate", "video_create", "web_search"),
        effort="medium",
        temperature=1.0,
        check=_hous,
    ),
    "tennessee": Specialty(
        key="tennessee",
        does="Hace las cuentas y le dice la verdad: veredicto con números.",
        toolkit=("calculator", "verified_math", "kronos_forecast", "web_search"),
        effort="high",
        temperature=0.2,
        check=_tennessee,
    ),
}


def specialty(key: str) -> Optional[Specialty]:
    return SPECIALTIES.get(key or "")


def tools_with_toolkit(key: str, allowed: Iterable[str]) -> list[str]:
    """The tools of a run: what the owner's rules allow, plus its own."""
    tools = list(allowed)
    own = specialty(key)
    for name in own.toolkit if own else ():
        if name not in tools:
            tools.append(name)
    return tools


def missing(key: str, request: str, answer: str, used: Iterable[str]) -> Optional[str]:
    """What this Node's answer lacks, or None when it delivers what it must."""
    own = specialty(key)
    if own is None or not answer.strip():
        return None
    return own.check(request or "", answer, frozenset(used))


def retry_prompt(prompt: str, name: str, lack: str, answer: str) -> str:
    return (
        f"{prompt}\n\nTU RESPUESTA ANTERIOR (no llegó al señor):\n{answer[:4000]}\n\n"
        f"REVISIÓN — como {name}, te faltó {lack}. Rehaz la respuesta completa "
        "cumpliéndolo; no menciones esta revisión."
    )


__all__ = [
    "SPECIALTIES",
    "Specialty",
    "missing",
    "retry_prompt",
    "specialty",
    "tools_with_toolkit",
]

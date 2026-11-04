"""Only one job: a content calendar a creator can follow.

The owner (4 Nov 2026): «mejora las herramientas de creadores un 2x». Posting
on a rhythm beats posting a lot once. This plans *semanas* weeks of posts:

* the ideas come from the person's topic and, when asked, from **real** trend
  signals (:mod:`automatiza.tendencias`); one model call writes them with a
  hook each, and **code** judges every hook with the same rules as the scripts
  (one breath, something concrete or a question) and the titles (no lies, no
  shouting);
* the days are spread across the week (never two posts the same day) and the
  formats rotate so the feed does not repeat itself;
* no posting hour is invented: the calendar says to use the hour the person's
  own statistics show, because no general «best hour» is true for everyone.

It can be saved as a real .xlsx. Nothing is posted.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

FORMATOS = ("historia con giro", "lista de datos", "cómo hacerlo", "opinión contraria",
            "detrás de cámaras", "pregunta al público", "antes y después")  # fmt: skip
DAYS = {1: (2,), 2: (1, 4), 3: (0, 2, 4), 4: (0, 1, 3, 5), 5: (0, 1, 2, 3, 4),
        6: (0, 1, 2, 3, 4, 5), 7: tuple(range(7))}  # fmt: skip
WEEKDAY = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

PROMPT = """You plan a content calendar in {idioma} about: {tema}.
{extra}Write {n} DIFFERENT post ideas for {plataforma}. Each has a concrete angle (no two alike),
a hook (the first line said on screen: at most 12 words, something concrete or a question, no
lies, no shouting, no emojis) and one sentence of what the post shows. Use these formats in
rotation: {formatos}.
Answer ONLY JSON: {{"ideas": [{{"titulo": "...", "gancho": "...", "formato": "...", "que": "..."}}]}}"""


def days(start: dt.date, weeks: int, per_week: int) -> List[dt.date]:
    """Post days: spread over each week, never two the same day."""
    per_week = max(1, min(7, int(per_week)))
    monday = start - dt.timedelta(days=start.weekday())
    if start.weekday() > 0:
        monday += dt.timedelta(days=7)  # plans start on a fresh week
    out = []
    for w in range(max(1, min(12, int(weeks)))):
        for d in DAYS[per_week]:
            out.append(monday + dt.timedelta(days=7 * w + d))
    return out


def judge_hook(hook: str) -> List[str]:
    """What is wrong with a hook (empty = fine)."""
    from openjarvis.estudio import titulos
    from openjarvis.video_essay import partes

    problems = list(partes.hook_problems(hook))
    if titulos.LIES.search(hook or ""):
        problems.append("promete de más")
    if sum(1 for w in (hook or "").split() if len(w) > 3 and w.isupper()) >= 2:
        problems.append("grita (mayúsculas)")
    if re.search(r"[\U0001f300-\U0001faff]", hook or ""):
        problems.append("tiene emojis")
    return problems


def plan(
    tema: str,
    *,
    semanas: int = 4,
    por_semana: int = 3,
    plataforma: str = "shorts",
    idioma: str = "Spanish",
    tendencias: Optional[List[str]] = None,
    ask: Optional[Callable[..., str]] = None,
    hoy: Optional[dt.date] = None,
) -> Dict[str, Any]:
    tema = " ".join(str(tema or "").split())[:300]
    if len(tema) < 3:
        raise ValueError("Diga de qué trata su canal o su cuenta.")
    when = days(hoy or dt.date.today(), semanas, por_semana)
    if ask is None:
        from openjarvis.creator.llm import ask as llm_ask

        def ask(p: str, **kw: Any) -> str:
            return llm_ask(p, json_mode=True, max_tokens=6000)

    extra = (
        "Real searches rising now (use the ones that fit; never invent others): "
        + ", ".join(tendencias[:15])
        + "\n"
        if tendencias
        else ""
    )
    raw = ask(PROMPT.format(idioma=idioma, tema=tema, n=len(when), plataforma=plataforma,
                            formatos=", ".join(FORMATOS), extra=extra))  # fmt: skip
    ideas = [i for i in (json.loads(raw).get("ideas") or []) if isinstance(i, dict)]
    if not ideas:
        raise RuntimeError("El modelo no devolvió ideas; inténtelo otra vez.")
    rows = []
    seen: set = set()
    for k, day in enumerate(when):
        idea = ideas[k % len(ideas)]
        title = " ".join(str(idea.get("titulo") or "").split())[:120]
        if title.lower() in seen and len(ideas) > k:
            continue
        seen.add(title.lower())
        hook = " ".join(str(idea.get("gancho") or "").split())[:160]
        rows.append({
            "fecha": day.isoformat(), "dia": WEEKDAY[day.weekday()],
            "formato": str(idea.get("formato") or FORMATOS[k % len(FORMATOS)])[:40],
            "titulo": title, "gancho": hook, "que": str(idea.get("que") or "")[:240],
            "revisar_gancho": judge_hook(hook),
        })  # fmt: skip
    return {
        "tema": tema,
        "plataforma": plataforma,
        "publicaciones": rows,
        "hora": "Publique a la hora en que su público está conectado según sus propias estadísticas "
        "(YouTube Studio, Instagram o TikTok): no hay una hora que sirva para todos.",
        "tendencias_usadas": bool(tendencias),
    }


def save_xlsx(result: Dict[str, Any], folder: Optional[Path] = None) -> str:
    """The calendar as a real .xlsx in the person's Documents."""
    from openjarvis.asistente import xlsx

    folder = folder or (Path.home() / "Documents" / "Sergio")
    folder.mkdir(parents=True, exist_ok=True)
    path = (
        folder
        / f"calendario-{re.sub(r'[^a-z0-9]+', '-', result['tema'].lower())[:40].strip('-')}.xlsx"
    )
    header = ["Fecha", "Día", "Formato", "Título", "Gancho", "Qué muestra", "Revisar"]
    rows = [[r["fecha"], r["dia"], r["formato"], r["titulo"], r["gancho"], r["que"],
             "; ".join(r["revisar_gancho"]) or "bien"] for r in result["publicaciones"]]  # fmt: skip
    return str(xlsx.write(path, [{"nombre": "Calendario", "columnas": header, "filas": rows,
                                  "formatos": {"Fecha": "fecha"}}]))  # fmt: skip


def texto(result: Dict[str, Any]) -> str:
    rows = result["publicaciones"]
    lines = [
        f"Calendario de {len(rows)} publicaciones sobre «{result['tema']}» ({result['plataforma']}):"
    ]
    for r in rows:
        flag = (
            f"  [gancho a revisar: {', '.join(r['revisar_gancho'])}]"
            if r["revisar_gancho"]
            else ""
        )
        lines.append(
            f"- {r['dia']} {r['fecha']} · {r['formato']}: «{r['gancho']}»{flag}"
        )
    lines.append(result["hora"])
    return "\n".join(lines)


__all__ = ["FORMATOS", "days", "judge_hook", "plan", "save_xlsx", "texto"]

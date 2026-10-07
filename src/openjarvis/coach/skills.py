"""Permanent skills: rules that load themselves when the topic comes up.

A model's weights cannot be changed from here, so this is the closest thing
to skills «rooted» in Sergio: each skill is a short rule file with its key
words; every plan and every agent step whose request matches gets those
rules in its instructions, always, without being asked.

* Built in: ``knowledge/skills/*.md`` (Blender de producción, Color y
  entrega de video, Enjambre de agentes).
* Learned: «Sergio, aprende este PDF …» turns a manual into a rule file in
  ``~/.openjarvis/skills`` (Gemini reads it and distils the rules; only the rules are kept).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

BUILT_IN = Path(__file__).parent / "knowledge" / "skills"
LEARNED = Path.home() / ".openjarvis" / "skills"
MAX_CHARS = 2400  # rules injected per request (token budget)


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _parse(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta: dict[str, str] = {}
    body = text
    found = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if found:
        for line in found.group(1).splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        body = found.group(2)
    keys = [plain(k.strip()) for k in meta.get("claves", "").split(",") if k.strip()]
    return {"nombre": meta.get("nombre") or path.stem, "claves": keys, "reglas": body.strip(), "archivo": str(path)}


def all_skills(dirs: tuple[Path, ...] | None = None) -> list[dict[str, Any]]:
    out = []
    for folder in dirs or (BUILT_IN, LEARNED):
        if folder.is_dir():
            out += [s for s in (_parse(p) for p in sorted(folder.glob("*.md"))) if s]
    return out


def match(request: str, dirs: tuple[Path, ...] | None = None) -> list[dict[str, Any]]:
    """The skills whose key words appear in the request (best first)."""
    words = plain(request)
    scored = []
    for skill in all_skills(dirs):
        hits = sum(1 for k in skill["claves"] if re.search(r"(?<!\w)" + re.escape(k), words))
        if hits:
            scored.append((hits, skill))
    return [s for _, s in sorted(scored, key=lambda x: -x[0])]


def rules_for(request: str, dirs: tuple[Path, ...] | None = None) -> str:
    """The text added to a plan or an agent step (within MAX_CHARS)."""
    parts, used = [], 0
    for skill in match(request, dirs):
        block = f"Skill «{skill['nombre']}»:\n{skill['reglas']}"
        if used + len(block) > MAX_CHARS:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


LEARN_PROMPT = """Convierte este manual en una skill para un asistente: reglas \
concretas y verificables (valores exactos, pasos, prohibiciones), en español, \
máximo 14 viñetas cortas. Descarta marketing, historia y cifras que no sirvan \
para actuar.
Devuelve SOLO JSON: {{"nombre": "nombre corto", "claves": ["8 a 20 palabras \
clave en minúsculas con las que alguien pediría esto"], "reglas": ["..."]}}
Manual ({name}):
{text}"""


def learn(
    text: str,
    name: str,
    ask: Callable[..., Any] | None = None,
    folder: Path | None = None,
    pdf: bytes = b"",
) -> dict[str, Any]:
    """A manual (its text, or the PDF itself, which Gemini reads directly,
    scans included) -> a saved rule file that loads by itself."""
    if ask is None:
        from openjarvis.coach.brain import ask
    text = " ".join(text.split())[:60000]
    if len(text) < 80 and not pdf:
        raise ValueError("El documento no tiene texto que aprender.")
    prompt = LEARN_PROMPT.format(name=name, text=text or "(el PDF adjunto)")
    extra = {"media": [(pdf, "application/pdf")]} if pdf else {}
    data = ask(prompt, effort="medium", deep=True, **extra)
    data = data if isinstance(data, dict) else {}
    rules = [" ".join(str(r).split()) for r in data.get("reglas") or [] if str(r).strip()][:20]
    keys = [plain(str(k)).strip() for k in data.get("claves") or [] if str(k).strip()][:24]
    if not rules or not keys:
        raise RuntimeError("No pude sacar reglas claras de ese documento.")
    title = " ".join(str(data.get("nombre") or name).split())[:60]
    folder = folder or LEARNED
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", plain(title)).strip("-") or "skill"
    path = folder / f"{slug}.md"
    path.write_text(
        f"---\nnombre: {title}\nclaves: {', '.join(keys)}\n---\n" + "\n".join(f"- {r}" for r in rules) + "\n",
        encoding="utf-8",
    )
    return {"nombre": title, "claves": keys, "reglas": len(rules), "archivo": str(path)}


__all__ = ["all_skills", "learn", "match", "rules_for"]

"""Blender Pro's own worked examples: the closest thing to fine-tuning.

The model's weights can't be trained from here (and Gemini's newer models
are not tunable with an API key), so Sergio does what tuning would teach,
in context: before writing a script, the model studies one or two complete
scripts that really built correct models (zero mesh errors, every planned
part in place, nothing floating). It learns the technique (spatial plan,
helpers, lathe profiles, linked duplicates, closed meshes) from working
code, not from rules alone.

* Seeds: verified scripts that ship with Sergio (``*.py`` here: a table
  with linked-duplicate legs, a cup made on a lathe with a closed handle).
* Learned: every Blender Pro build that passes the strict check is kept in
  ``~/.openjarvis/blender_ejemplos`` (the 60 most recent), so the library
  grows with the user's own objects and the best technique keeps coming back.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

SEEDS = Path(__file__).parent
LEARNED = Path.home() / ".openjarvis" / "blender_ejemplos"
SEED_REQUESTS = {
    "mesa": "una mesa de madera de roble con cuatro patas y faldón, 120 x 70 cm",
    "taza": "una taza de cerámica blanca con asa y su plato",
    "telefono": "un teléfono móvil moderno con cámaras, botones y puerto",
}
KEEP = 60
STOP = {"de", "la", "el", "un", "una", "con", "y", "en", "los", "las", "del", "al", "su", "sus", "para", "por", "hazme",
        "haz", "crea", "modela", "blender", "en", "3d", "modelo", "objeto", "muy", "ultra", "detallado", "detallada"}


def _words(text: str) -> set[str]:
    plain = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", plain) if len(w) > 2 and w not in STOP}


def all_examples(folder: Path | None = None) -> list[dict[str, Any]]:
    out = [{"request": SEED_REQUESTS.get(p.stem, p.stem), "script": p.read_text(encoding="utf-8"), "seed": True}
           for p in sorted(SEEDS.glob("*.py")) if p.stem != "__init__"]
    folder = folder or LEARNED
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return out


def similar(request: str, k: int = 2, max_chars: int = 9000, folder: Path | None = None) -> list[dict[str, Any]]:
    """The examples closest to the request (shared words), then the seeds,
    within *max_chars* of script."""
    want = _words(request)
    scored = []
    for ex in all_examples(folder):
        overlap = len(want & _words(ex["request"]))
        scored.append((overlap, not ex.get("seed"), ex))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    chosen, used = [], 0
    for _, _, ex in scored:
        if len(chosen) >= k or used + len(ex["script"]) > max_chars:
            continue
        chosen.append(ex)
        used += len(ex["script"])
    return chosen


def prompt_block(request: str, folder: Path | None = None) -> str:
    examples = similar(request, folder=folder)
    if not examples:
        return ""
    parts = ["Worked examples: complete scripts that really built correct models in Blender (0 mesh errors, "
             "every planned part in place). Study their technique — the SERGIO_LAYOUT plan first, helpers, one "
             "function per part, exact numbers — and apply it to the new object; do not copy their shapes."]
    for ex in examples:
        parts.append(f"Example for «{ex['request']}»:\n```python\n{ex['script'].strip()}\n```")
    return "\n\n".join(parts) + "\n\n"


def quality(log: str) -> dict[str, Any]:
    """What the log says about a build (for the strict check)."""
    def num(pattern: str) -> int:
        found = re.search(pattern, log)
        return int(found.group(1)) if found else -1

    return {
        "saved": "SERGIO_SAVED" in log,
        "step_errors": sum(1 for ln in log.splitlines() if ln.startswith("SERGIO_STEP_ERROR")),
        "parts": num(r"SERGIO_PARTS (\d+)"),
        "bad_edges": num(r"non-manifold edges (\d+)"),
        "loose": num(r"loose vertices (\d+)"),
        "planned": num(r"SERGIO_SPATIAL planned (\d+)"),
        "in_place": num(r"in place (\d+)"),
        "floating": num(r"floating (\d+)"),
        "below": num(r"below ground (\d+)"),
    }


def good_enough(log: str, min_parts: int = 4) -> tuple[bool, str]:
    q = quality(log)
    if not q["saved"] or q["step_errors"]:
        return False, "no se guardó o tuvo pasos fallidos"
    if q["parts"] < min_parts:
        return False, f"solo {q['parts']} piezas"
    if q["bad_edges"] != 0 or q["loose"] != 0:
        return False, "malla con errores"
    if q["planned"] < 2 or q["in_place"] < 0.8 * q["planned"] or q["floating"] or q["below"]:
        return False, "piezas fuera de su sitio o sin plan espacial"
    return True, "ok"


def remember(request: str, script: str, log: str, folder: Path | None = None) -> dict[str, Any]:
    """Keep a build as an example if it passes the strict check."""
    if not script.strip():
        return {"saved": False, "why": "la revisión visual no lo aprobó"}
    ok, why = good_enough(log)
    if not ok:
        return {"saved": False, "why": why}
    folder = folder or LEARNED
    folder.mkdir(parents=True, exist_ok=True)
    slug = "-".join(sorted(_words(request)))[:60] or "modelo"
    path = folder / f"{slug}.json"
    path.write_text(json.dumps({"request": request, "script": script, "time": time.time()}, ensure_ascii=False),
                    encoding="utf-8")
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for old in files[:-KEEP]:
        old.unlink(missing_ok=True)
    return {"saved": True, "why": "ok", "path": str(path)}


__all__ = ["all_examples", "good_enough", "prompt_block", "quality", "remember", "similar"]

"""Every night Sergio fixes one real failure of its own code (owner, 3 Nov
2026: «que cada vez sea más inteligente, independientemente del modelo… que
siempre esté editándose a sí mismo para mejorar»).

What it works from is evidence, never a guess: videos that stopped with an
error and Node routines that keep failing, from the last seven days. The most
repeated failure is taken, the module that does that stage is read, and the
model proposes ONE small change (``automejora.Change``). ``automejora.improve``
then tries it in a separate copy and applies it only if ruff and the tests
pass; it never touches keys, never pushes to GitHub and can be undone. A
failure whose files were already rejected twice is left alone (it needs a
person). One try a night; ``SERGIO_AUTOMEJORA_NOCHE=0`` turns it off.

Every night's result is kept in ``~/.openjarvis/automejora/noches.json``.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

WEEK = 7 * 86400
# The module that does each stage of a video (where its errors come from).
STAGE_FILES = {
    "estudio": "src/openjarvis/video_essay/style.py",
    "guion": "src/openjarvis/video_essay/director.py",
    "voz": "src/openjarvis/video_essay/script.py",
    "tiempos": "src/openjarvis/video_essay/plan.py",
    "plan": "src/openjarvis/video_essay/plan.py",
    "imagenes": "src/openjarvis/video_essay/media.py",
    "revision": "src/openjarvis/video_essay/review.py",
    "sonido": "src/openjarvis/video_essay/mezcla.py",
    "render": "src/openjarvis/video_essay/render.py",
    "acabado": "src/openjarvis/video_essay/finish.py",
}
NEVER = ("sergio.env", "secrets", "cifrado", "pagos/", "accounts/", "security/")
PROMPT = """You maintain this Python project. A real failure repeated {count} time(s) this week:
{error}
It happens in the stage «{stage}», whose code is {path}:
```python
{code}
```
Propose ONE small, safe change to {path} that prevents this failure without changing what the
module does when it works (handle the bad input, add the missing fallback, fix the bug). Keep the
style. Never remove a safety check. If you cannot see the cause in this code, answer {{"cambios": []}}.
Answer ONLY JSON: {{"razon": "one line", "cambios": [{{"old": "exact text that appears once", "new": "..."}}]}}"""


def _home() -> Path:
    from openjarvis.evolution import automejora

    return automejora.home()


def evidence(
    now: Optional[float] = None, home: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """The real failures of the last week, most repeated first."""
    now = now or time.time()
    if home is None:
        from openjarvis.core.config import get_config_dir

        home = Path(get_config_dir())
    found: Counter = Counter()
    where: Dict[str, str] = {}
    for st in (home / "video_jobs").glob("*/state.json"):
        try:
            if now - st.stat().st_mtime > WEEK:
                continue
            data = json.loads(st.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("status") != "error":
            continue
        stage = str(data.get("stage") or "")
        if stage not in STAGE_FILES:
            continue
        error = " ".join(str(data.get("error") or "").split())[:300]
        key = f"{stage}|{error}"
        found[key] += 1
        where[key] = STAGE_FILES[stage]
    return [
        {
            "stage": k.split("|", 1)[0],
            "error": k.split("|", 1)[1],
            "count": n,
            "path": where[k],
        }
        for k, n in found.most_common()
        if k.split("|", 1)[1]
    ]


def _ask() -> Callable[..., str]:
    from openjarvis.creator import llm

    def ask(prompt: str, **kw: Any) -> str:
        return llm.ask(prompt, effort="high", **kw)

    return ask


def night(
    *,
    ask: Optional[Callable[..., str]] = None,
    improve: Optional[Callable[..., Any]] = None,
    root: Optional[Path] = None,
    now: Optional[float] = None,
    home: Optional[Path] = None,
) -> Dict[str, Any]:
    """One night's try: what was found, what was proposed and what happened."""
    from openjarvis.evolution import automejora as A

    if os.environ.get("SERGIO_AUTOMEJORA_NOCHE", "1") == "0":
        return _record(
            {"hecho": False, "motivo": "apagado (SERGIO_AUTOMEJORA_NOCHE=0)"}
        )
    root = Path(root or A.repo_root())
    for item in evidence(now, home):
        path = item["path"]
        if any(n in path for n in NEVER) or A.failed_before([path]) >= 2:
            continue
        try:
            code = (root / path).read_text("utf-8")
        except OSError:
            continue
        ask = ask or _ask()
        try:
            raw = ask(
                PROMPT.format(count=item["count"], error=item["error"], stage=item["stage"], path=path,
                              code=code[:14000]),
                json_mode=True, max_tokens=3000,
            )  # fmt: skip
            data = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 — no model tonight: said, nothing touched
            return _record(
                {
                    "hecho": False,
                    "fallo": item,
                    "motivo": f"sin modelo: {str(exc)[:120]}",
                }
            )
        changes = [A.Change(path, str(c.get("old") or ""), str(c.get("new") or ""))
                   for c in (data.get("cambios") or [])[:3] if c.get("old") and c.get("new")]  # fmt: skip
        if not changes:
            return _record(
                {
                    "hecho": False,
                    "fallo": item,
                    "motivo": "el modelo no vio la causa en el código",
                }
            )
        reason = (
            f"noche: {item['stage']}: {str(data.get('razon') or item['error'])[:200]}"
        )
        try:
            m = (improve or A.improve)(reason, changes, root=root)
        except A.AutomejoraError as exc:
            return _record({"hecho": False, "fallo": item, "motivo": str(exc)[:200]})
        state = getattr(m, "state", "")
        return _record({"hecho": state == "aplicada", "fallo": item, "estado": state,
                        "mejora": getattr(m, "id", ""), "razon": reason})  # fmt: skip
    return _record({"hecho": False, "motivo": "sin fallos reales esta semana"})


def _record(result: Dict[str, Any]) -> Dict[str, Any]:
    result["cuando"] = time.time()
    path = _home() / "noches.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        rows = []
    rows = (rows + [result])[-60:]
    try:
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    except OSError:
        pass
    return result


def nights(limit: int = 7) -> List[Dict[str, Any]]:
    try:
        return json.loads((_home() / "noches.json").read_text("utf-8"))[-limit:]
    except (OSError, ValueError):
        return []


__all__ = ["STAGE_FILES", "evidence", "night", "nights"]

"""Who Sergio is talking to, and how they want it: one small file per user.

Sergio was built for one owner who likes «señor». To be usable by anyone,
anywhere, the person chooses (``~/.openjarvis/perfil_usuario.json``):

* how to be addressed — «señor», «señora», by name, neutral (no gendered
  words) or «tú» — and the name Sergio uses;
* language and country (answers, dates, emergency lines);
* the line above the chat («¡Ana ha vuelto!», «El micrófono es tuyo, Ana»):
  its tone, or their own phrases;
* which of Sergio's skills he may use (a skill switched off never reaches
  the model: :func:`blocked_tools`).

With no file, the owner's defaults hold: «señor», Spanish, every skill on.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

ADDRESS = ("señor", "señora", "nombre", "neutro", "tu")
TONES = ("formal", "cercano", "divertido")
DEFAULTS: Dict[str, Any] = {
    "nombre": "",
    "trato": "señor",
    "idioma": "auto",
    "pais": "",
    "tono_saludo": "formal",
    "saludos_propios": [],
    "habilidades_apagadas": [],
}
_LOCK = threading.Lock()


def _path(home: Optional[Path] = None) -> Path:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    return Path(home) / "perfil_usuario.json"


def load(home: Optional[Path] = None) -> Dict[str, Any]:
    try:
        raw = json.loads(_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in raw.items() if k in DEFAULTS})
    return out


def save(changes: Dict[str, Any], home: Optional[Path] = None) -> Dict[str, Any]:
    with _LOCK:
        now = load(home)
        for key, value in changes.items():
            if key not in DEFAULTS:
                continue
            if key == "trato" and value not in ADDRESS:
                raise ValueError(f"trato: uno de {', '.join(ADDRESS)}")
            if key == "tono_saludo" and value not in TONES:
                raise ValueError(f"tono_saludo: uno de {', '.join(TONES)}")
            if key == "nombre":
                value = " ".join(str(value or "").split())[:40]
            if key == "saludos_propios":
                value = [
                    " ".join(str(v).split())[:80]
                    for v in (value or [])
                    if str(v).strip()
                ][:12]
            if key == "habilidades_apagadas":
                value = sorted({str(v) for v in (value or [])})
            now[key] = value
        path = _path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(now, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        return now


def address_line(profile: Optional[Dict[str, Any]] = None) -> str:
    """How Sergio addresses this person, as an instruction for the model."""
    p = profile or load()
    name = p.get("nombre") or ""
    how = p.get("trato", "señor")
    if how == "señor":
        return ""  # the persona's own default («señor», de usted)
    if how == "señora":
        return "Trato: a esta persona le dices «señora» y la tratas de usted (nunca «señor»)."
    if how == "nombre":
        who = f"«{name}»" if name else "por su nombre"
        return f"Trato: le llamas {who}, de usted; nunca «señor» ni «señora»."
    if how == "tu":
        who = f" y le llamas «{name}»" if name else ""
        return f"Trato: le tuteas{who}; nunca «señor» ni «señora»."
    return (
        "Trato: neutro y respetuoso, sin palabras de género («señor», «señora», "
        "«bienvenido/a»…)" + (f"; le llamas «{name}»." if name else ".")
    )


def blocked_tools(profile: Optional[Dict[str, Any]] = None) -> FrozenSet[str]:
    """Tools of the skills the person switched off."""
    p = profile or load()
    off = p.get("habilidades_apagadas") or []
    if not off:
        return frozenset()
    from openjarvis.connectome import neurons

    return frozenset(t for key in off for t in neurons.tools_of(key))


def skills(profile: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Every skill Sergio has, and whether it is on."""
    from openjarvis.connectome import neurons

    p = profile or load()
    off = set(p.get("habilidades_apagadas") or [])
    return [
        {"clave": n.key, "nombre": n.label, "hace": n.job, "activa": n.key not in off}
        for n in neurons.NEURONS.values()
    ]


__all__ = [
    "ADDRESS",
    "DEFAULTS",
    "TONES",
    "address_line",
    "blocked_tools",
    "load",
    "save",
    "skills",
]

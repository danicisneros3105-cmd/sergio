"""AdaptiveScrutiny: how closely Sergio must watch each step of a Cowork task.

Every planned step is scored 0-3 on ten axes. The scores, the owner's chosen
autonomy and what the owner approved or refused before decide whether the
step runs on its own (``allow``), waits for the owner (``ask``) or is not
done at all (``block``).

Hard rules that no autonomy level and no learned trust can relax:

* acting through other people (messages, calls, posts, invitations) is never
  done in Cowork: sending stays a direct request from the owner;
* money and credentials always wait for the owner, every time;
* a step the owner refused twice in the same shape is blocked from then on.

Trust is learned per *signature* (the step's tools and its risky axes): after
three approvals and no refusal, that kind of step stops asking at the
``normal`` level. A run that keeps failing tightens scrutiny for the rest of
the run.
"""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

AXES: Tuple[str, ...] = (
    "privacy",
    "destructive",
    "external_actor",
    "financial",
    "credentials",
    "system",
    "network",
    "irreversible",
    "scope",
    "uncertainty",
)
AXIS_LABELS_ES = {
    "privacy": "datos personales",
    "destructive": "borra o sobrescribe",
    "external_actor": "actúa ante otras personas",
    "financial": "dinero",
    "credentials": "contraseñas o claves",
    "system": "cambia el sistema",
    "network": "saca datos del equipo",
    "irreversible": "no se puede deshacer",
    "scope": "se aparta del objetivo",
    "uncertainty": "incierto o sin verificar",
}
AUTONOMY = ("cauteloso", "normal", "autonomo")
ALIASES = {"cautious": "cauteloso", "autonomous": "autonomo", "autónomo": "autonomo"}
# Highest score each level lets through on its own (per axis).
THRESHOLD = {"cauteloso": 0, "normal": 1, "autonomo": 2}
# Axes that never relax: any score here means the owner decides.
ALWAYS_ASK = ("financial", "credentials", "external_actor")
TRUST_AFTER = 3  # approvals of one signature before it stops asking
BLOCK_AFTER = 2  # refusals of one signature before it is blocked

# Keyword evidence per axis: (pattern, score). Spanish and English.
_RULES: Dict[str, List[Tuple[str, int]]] = {
    "privacy": [
        (r"\b(contrasena|password|historial de navegacion|browsing history)\w*", 2),
        (r"\b(ubicacion|location|gps|contactos?|contacts?|correos?|emails?)\b", 2),
        (r"\b(mensajes|messages|chats?|whatsapp|fotos|photos|rostros?|faces)\b", 2),
        (r"\b(salud|health|medic\w*|banco|bank|dni|pasaporte|passport)\b", 2),
        (
            r"\b(documentos|documents|escritorio|desktop|descargas|downloads|perfil)\b",
            1,
        ),
    ],
    "destructive": [
        (r"\b(formatea|format)\w*", 3),
        (r"\b(borra|elimina|suprime|delete|remove|erase|wipe|purge|rm\s+-)\w*", 3),
        (
            r"\b(sobrescrib|overwrit|reemplaz|replace|vac[ií]a|empty|trunca|truncat)\w*",
            2,
        ),
        (r"\b(mueve|move|renombra|rename|cierra|close|mata|kill|termina)\w*", 1),
    ],
    "external_actor": [
        # To a person or a social network: never in Cowork.
        (
            r"\b(envia|manda|reenvia|escribe)\w*\s+(un |una |el |la )?"
            r"(mensaje|correo|email|e-mail|whatsapp|sms|dm|mail)\w*",
            3,
        ),
        (
            r"\b(send|forward|text|email|message|dm)\s+(it |this |a |an |the )?\w*\s*to\s+\w",
            3,
        ),
        (r"\b(llama|llamar|marca|marcar)\s+a\s+\w", 3),
        (r"\b(phone|call|ring)\s+(my|him|her|them|mom|dad|\+?\d)", 3),
        (
            r"\b(publica|postea|tuitea|post|tweet)\w*\s+(\w+\s+){0,3}"
            r"(en|on|to)\s+(twitter|x|facebook|instagram|linkedin|tiktok|youtube|reddit|"
            r"redes|mi muro|el blog|my blog|my wall)",
            3,
        ),
        (r"\b(comparte|share)\w*\s+(\w+\s+){0,3}(con|with)\s+\w", 3),
        (r"\b(responde a|reply to|invita a|invite)\s+\w", 3),
        # Sending something somewhere unnamed: the owner decides.
        (r"\b(envia|manda|reenvia|send|forward)\w*", 2),
        (r"\b(agenda|schedule)\w*\s+(una |a )?(reunion|meeting|cita)", 2),
    ],
    "financial": [
        (
            r"\b(paga|pay|compra|buy|purchase|transfiere|transfer|suscr[ií]b|subscribe)\w*",
            3,
        ),
        (
            r"\b(tarjeta|card|factura|invoice|cripto|crypto|bitcoin|checkout|carrito|cart)\w*",
            2,
        ),
        (r"\b(precio|price|cotiza|quote|presupuesto|budget)\w*", 0),
    ],
    "credentials": [
        (
            r"\b(contrasenas?|passwords?|api[ _-]?keys?|tokens? de acceso|access tokens?)\b",
            3,
        ),
        (r"\b(secretos?|secrets?|credenciales|credentials|2fa|otp)\b", 3),
        (r"\b(inicia sesi|log ?in|sign ?in|autentic|authenticat)\w*", 2),
    ],
    "system": [
        (
            r"\b(desinstala|uninstall|registro de windows|registry|driver|controlador)\w*",
            3,
        ),
        (
            r"\b(instala|install|actualiza el sistema|update the system|servicio|service)\w*",
            2,
        ),
        (
            r"\b(sudo|admin|configuraci[oó]n del sistema|system settings|inicio autom|startup)\w*",
            2,
        ),
        (r"\b(pip|npm|apt|winget|choco)\b", 2),
    ],
    "network": [
        (r"\b(sube|upload|publica|publish|sincroniza|sync|exporta a|export to)\w*", 2),
        (r"\b(post|put|webhook|api externa|external api)\b", 2),
        (r"\b(busca|search|descarga|download|consulta|look ?up|navega|browse)\w*", 1),
    ],
    "irreversible": [
        (
            r"\b(definitivamente|permanent|para siempre|forever|sin papelera|no trash)\w*",
            3,
        ),
        (r"\b(envia|send|publish|paga|pay|borra|delete|formatea|format)\w*", 2),
    ],
}
_TOOL_PRIORS: Dict[str, Dict[str, int]] = {
    "web_search": {"network": 1},
    "http_request": {"network": 2},
    "file_write": {"destructive": 1},
    "files_organize": {"destructive": 2},
    "python_run": {"system": 1},
    "terminal_run": {"system": 2},
    "code_interpreter": {"system": 1},
    "desktop_action": {"uncertainty": 1},
    "calendar_upcoming": {"privacy": 1},
    "pdf_extract": {"privacy": 1},
    "video_edit": {"destructive": 1},
    "video_pro": {"destructive": 1},
}
# Tools that act through other people: never run in Cowork.
EXTERNAL_TOOLS = frozenset(
    {"whatsapp_send", "phone_call", "channel_send", "email_send", "sms_send"}
)
_STOP = frozenset(
    "a al con de del el en la las lo los para por que se su sus un una y o the of to "
    "and for in on with my mi mis me haz hacer crea crear".split()
)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", _norm(text)) if w not in _STOP}


@dataclass
class Verdict:
    """What scrutiny decided about one step, and why."""

    decision: str  # allow | ask | block
    scores: Dict[str, int]
    reasons: List[str] = field(default_factory=list)
    signature: str = ""
    level: str = "normal"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def risky_axes(self) -> List[str]:
        return [a for a in AXES if self.scores.get(a, 0) > 0]


def normalize_autonomy(level: str | None) -> str:
    level = _norm(level or "normal").strip()
    level = ALIASES.get(level, level)
    return level if level in AUTONOMY else "normal"


def score_step(
    text: str,
    *,
    goal: str = "",
    tools: Iterable[str] = (),
    where: str = "fondo",
    check: str = "",
    invented: Iterable[str] = (),
) -> Dict[str, int]:
    """The ten axis scores (0-3) for one step."""
    tools = [t for t in tools if t]
    low = _norm(text)
    scores = {axis: 0 for axis in AXES}
    for axis, rules in _RULES.items():
        for pattern, value in rules:
            if value and re.search(pattern, low):
                scores[axis] = max(scores[axis], value)
    for tool in tools:
        for axis, value in _TOOL_PRIORS.get(tool, {}).items():
            scores[axis] = max(scores[axis], value)
        if tool in EXTERNAL_TOOLS:
            scores["external_actor"] = 3
            scores["irreversible"] = max(scores["irreversible"], 2)
    # A step that only reads or searches cannot destroy or send anything.
    if scores["destructive"] == 1 and not any(
        t in ("file_write", "files_organize", "video_edit", "video_pro") for t in tools
    ):
        scores["destructive"] = 0
    # Scope: a step sharing no words with the goal may have drifted from it.
    if goal:
        overlap = _words(text) & _words(goal)
        scores["scope"] = 0 if overlap else (1 if len(_words(text)) > 3 else 0)
    uncertainty = 0
    if list(invented):
        uncertainty = 2  # the planner named tools that do not exist
    elif not check.strip():
        uncertainty = 1  # nothing says how to verify the step
    if where == "pantalla":
        uncertainty = max(uncertainty, 1)
    scores["uncertainty"] = max(scores["uncertainty"], uncertainty)
    return scores


def signature(scores: Dict[str, int], tools: Iterable[str]) -> str:
    """The *kind* of step, for learned trust: tools plus risky axes."""
    risky = ",".join(f"{a}:{scores[a]}" for a in AXES if scores.get(a, 0) >= 2)
    return f"{'+'.join(sorted(set(tools))) or 'sin-herramientas'}|{risky or 'leve'}"


class TrustStore:
    """Owner decisions per step signature, kept in ``~/.openjarvis/cowork``."""

    def __init__(self, path: Optional[Path] = None) -> None:
        if path is None:
            home = Path(
                os.environ.get("OPENJARVIS_HOME") or Path.home() / ".openjarvis"
            )
            path = home / "cowork" / "trust.json"
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, Dict[str, int]]:
        try:
            data = json.loads(self.path.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, sig: str) -> Dict[str, int]:
        with self._lock:
            entry = self._load().get(sig) or {}
        return {
            "approved": int(entry.get("approved", 0)),
            "denied": int(entry.get("denied", 0)),
        }

    def record(self, sig: str, approved: bool) -> Dict[str, int]:
        with self._lock:
            data = self._load()
            entry = data.setdefault(sig, {"approved": 0, "denied": 0})
            if approved:
                entry["approved"] = int(entry.get("approved", 0)) + 1
            else:
                entry["denied"] = int(entry.get("denied", 0)) + 1
                entry["approved"] = 0  # trust is earned again from zero
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
            tmp.replace(self.path)
            return dict(entry)


class AdaptiveScrutiny:
    """Decide allow / ask / block for each step of one Cowork run."""

    def __init__(
        self,
        autonomy: str = "normal",
        trust: Optional[TrustStore] = None,
    ) -> None:
        self.autonomy = normalize_autonomy(autonomy)
        self.trust = trust if trust is not None else TrustStore()
        self.failures_in_a_row = 0

    @property
    def level(self) -> str:
        """The autonomy in force now: two failures in a row step it down."""
        if self.failures_in_a_row >= 2 and self.autonomy != "cauteloso":
            return AUTONOMY[AUTONOMY.index(self.autonomy) - 1]
        return self.autonomy

    def note_outcome(self, ok: bool) -> None:
        self.failures_in_a_row = 0 if ok else self.failures_in_a_row + 1

    def review(
        self,
        text: str,
        *,
        goal: str = "",
        tools: Iterable[str] = (),
        where: str = "fondo",
        check: str = "",
        invented: Iterable[str] = (),
    ) -> Verdict:
        tools = list(tools)
        scores = score_step(
            text, goal=goal, tools=tools, where=where, check=check, invented=invented
        )
        sig = signature(scores, tools)
        level = self.level
        reasons: List[str] = []
        if scores["external_actor"] >= 3 or any(t in EXTERNAL_TOOLS for t in tools):
            reasons.append(
                "Cowork nunca envía mensajes, llama ni publica a nombre suyo: "
                "eso queda como un pedido directo suyo."
            )
            return Verdict("block", scores, reasons, sig, level)
        history = self.trust.get(sig)
        if history["denied"] >= BLOCK_AFTER:
            reasons.append(f"Usted rechazó {history['denied']} veces pasos así.")
            return Verdict("block", scores, reasons, sig, level)
        hard = [a for a in ALWAYS_ASK if scores[a] > 0]
        if hard:
            reasons.append(
                "Siempre le pregunto: "
                + ", ".join(AXIS_LABELS_ES[a] for a in hard)
                + "."
            )
            return Verdict("ask", scores, reasons, sig, level)
        limit = THRESHOLD[level]
        over = [a for a in AXES if scores[a] > limit]
        if not over:
            return Verdict("allow", scores, reasons, sig, level)
        trusted = (
            level != "cauteloso"
            and history["approved"] >= TRUST_AFTER
            and history["denied"] == 0
            and max(scores[a] for a in over) < 3
        )
        if trusted:
            reasons.append(f"Ya aprobó {history['approved']} pasos así: sigo solo.")
            return Verdict("allow", scores, reasons, sig, level)
        reasons.append(
            "Necesita su visto bueno: "
            + ", ".join(f"{AXIS_LABELS_ES[a]} ({scores[a]})" for a in over)
            + "."
        )
        if level != self.autonomy:
            reasons.append("Más cuidado: los dos últimos pasos fallaron.")
        return Verdict("ask", scores, reasons, sig, level)


__all__ = [
    "AXES",
    "AXIS_LABELS_ES",
    "AUTONOMY",
    "AdaptiveScrutiny",
    "EXTERNAL_TOOLS",
    "TrustStore",
    "Verdict",
    "normalize_autonomy",
    "score_step",
    "signature",
]

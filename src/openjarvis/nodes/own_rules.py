"""The owner's own rules for a Node, in plain words, and the automatic review.

Like Dots' custom rules: the owner writes «Pídeme permiso antes de borrar
archivos» or «Nunca publiques nada en redes» and every action the Node
proposes is reviewed against them before it runs. The review is code, not a
second model: a rule is read once into an effect (ask / block) and the
action verbs it covers (with their synonyms in Spanish and English), so the
same action always gets the same answer, instantly, and the owner can see
exactly what each rule was understood to cover.
"""

from __future__ import annotations

import json
import re
import secrets
import unicodedata
from typing import Any, Dict, Iterable, List, Optional

MAX_RULES = 30

# Each action family: a pattern that finds it in a rule, and one that finds it
# in an action (its description, command, tool or API call). Both run on
# lower-case text without accents, with word boundaries, so «comprobar» is
# not «comprar» and «environment» is not «enviar».
FAMILIES: Dict[str, Dict[str, str]] = {
    "borrar": {
        "rule": r"\b(borr|elimin|suprim|vaci[ae]|delete|remove|erase)",
        "action": r"\b(borr|elimin|suprim|delete|remove|erase|rmdir|unlink|trash|papelera|purge)"
        r"|\brm\s|method=delete|\"delete\"",
    },
    "enviar": {
        "rule": r"\b(envi[aeo]|mand[aeo]|respond|contest|send|reply|e-?mail|correo|mensaje)",
        "action": r"\b(envi[aeo]|send|reply|e-?mail|correo|mensaje|whatsapp|sms|slack|telegram)",
    },
    "publicar": {
        "rule": r"\b(public|tuit|redes|post(e|ea|ee)|share)",
        "action": r"\b(public|tweet|tuit|linkedin|instagram|facebook)|/posts\b",
    },
    "comprar": {
        "rule": r"\b(compr(a|as|ar|e|es|en|o)\b|pag(o|ar|ue|ues)\b|gast|suscrib|reserv"
        r"|buy|purchase|pay\b|dinero|tarjeta)",
        "action": r"\b(compr(a|as|ar|e|es|en|o)\b|pag(o|ar|ue)\b|payment|gast|suscrib|reserv|buy|purchase"
        r"|checkout|invoice|charge|stripe|paypal|tarjeta)",
    },
    "instalar": {
        "rule": r"\b(instal|install|upgrade)",
        "action": r"\b(instal|install|upgrade|winget|choco)",
    },
    "modificar": {
        "rule": r"\b(modific|edit|cambi|sobrescrib|reescrib|renombr|mover|muev)",
        "action": r"\b(modific|edit|sobrescrib|renombr|rename|update|patch)|(write|escrib)"
        r"|method=(put|patch)|\bmv\s",
    },
    "ejecutar": {
        "rule": r"\b(ejecut|corr(e|er|as)\b|lanz|run\b|script|comando|terminal)",
        "action": r"\b(ejecut|run\b|exec|python|bash|powershell|cmd)|\"kind\": \"cli\"",
    },
    "llamar": {
        "rule": r"\b(llam|telefon|call\b)",
        "action": r"\b(llam|telefon|call\b|twilio|dial)",
    },
    "git": {
        "rule": r"\b(git|push|commit|merge|repositorio|pull request)",
        "action": r"\b(git|push|commit|merge|pull request|github|gitlab)\b",
    },
    "compartir": {
        "rule": r"\b(compart|invit|share|dar acceso)",
        "action": r"\b(compart|invit|share|permission|grant)",
    },
}
_RULE = {k: re.compile(v["rule"]) for k, v in FAMILIES.items()}
_ACTION = {k: re.compile(v["action"]) for k, v in FAMILIES.items()}

BLOCK_WORDS = re.compile(
    r"\b(nunca|jam[aá]s|prohib\w*|no\s+(?:puedes|debes|hagas|toques|uses|tienes|se\s+puede)|"
    r"never|don'?t|do\s+not|forbid\w*|block\w*|bloque\w*)\b",
    re.I,
)
CONDITIONAL = re.compile(
    r"\bsin\s+(?:mi\s+|su\s+)?(?:permiso|aprob\w*|pregunt\w*|consult\w*|avis\w*|confirm\w*)"
    r"|\bwithout\s+(?:my\s+)?(?:asking|permission|approval|checking)"
)
ASK_WORDS = re.compile(
    r"\b(p[ií]de(?:me)?|pregunt\w*|consult\w*|permiso|aprob\w*|confirm\w*|av[ií]s\w*|ask|approval)\b",
    re.I,
)
# Words that name a category of tools the Node may use by itself during a turn.
CATEGORY_HINTS = {
    "computer": ["archiv", "fichero", "carpeta", "document", "file", "disco"],
    "web": ["internet", "web", "naveg", "busc", "google", "pagina", "sitio"],
    "code": ["codig", "script", "program", "python"],
    "workspace": ["workspace", "notas", "pagina del workspace"],
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def compile_rule(text: str) -> Dict[str, Any]:
    """«Pídeme permiso antes de borrar archivos» -> what it covers, as data."""
    text = " ".join(str(text or "").split())[:300]
    if len(text) < 6:
        raise ValueError("Escriba la regla en una frase («Pídeme permiso antes de…»).")
    plain = _norm(text)
    # «sin preguntarme / sin mi permiso» makes any rule an «ask» one;
    # «nunca…», «no compres…» on their own forbid.
    if CONDITIONAL.search(plain):
        effect = "ask"
    elif BLOCK_WORDS.search(plain) or re.match(r"^\s*no\s+\w+", plain):
        effect = "block"
    else:
        effect = "ask"
    families = [name for name, pattern in _RULE.items() if pattern.search(plain)]
    quoted = [
        _norm(q).strip()
        for q in re.findall(r"[«\"“']([^»\"”']{2,60})[»\"”']", text)
        if q.strip()
    ]
    categories = [
        cat for cat, hints in CATEGORY_HINTS.items() if any(h in plain for h in hints)
    ]
    if not families and not quoted:
        raise ValueError(
            "No entendí qué acción cubre la regla. Diga el verbo: borrar, enviar, "
            "publicar, comprar, instalar, modificar, ejecutar, llamar, compartir…"
        )
    return {
        "id": secrets.token_hex(4),
        "text": text,
        "effect": effect,
        "families": families,
        "words": quoted,
        "categories": categories,
    }


def explain(rule: Dict[str, Any]) -> str:
    """What the rule was understood to do, in one line for the owner."""
    what = ", ".join(rule.get("families") or []) or ""
    words = ", ".join(f"«{w}»" for w in rule.get("words") or [])
    covers = " y ".join(x for x in (what, words) if x)
    verb = "Bloquea" if rule.get("effect") == "block" else "Pide su permiso para"
    return f"{verb}: {covers}"


def action_text(action: Dict[str, Any], description: str = "") -> str:
    flat = json.dumps(action, ensure_ascii=False)
    method = str(action.get("method") or "").lower()
    extra = f" method={method}" if method else ""
    return _norm(f" {description} {flat}{extra} ")


def review(
    rules: Iterable[Dict[str, Any]], action: Dict[str, Any], description: str = ""
) -> Optional[Dict[str, Any]]:
    """The strictest rule this action falls under (block beats ask), or None."""
    text = action_text(action, description)
    hit: Optional[Dict[str, Any]] = None
    for rule in rules or []:
        families = [f for f in rule.get("families") or [] if f in _ACTION]
        if any(_ACTION[f].search(text) for f in families) or any(
            w and w in text for w in rule.get("words") or []
        ):
            if rule.get("effect") == "block":
                return rule
            hit = hit or rule
    return hit


def blocked_categories(rules: Iterable[Dict[str, Any]]) -> List[str]:
    """Tool categories a rule takes away from the Node's own turn: it cannot
    ask in the middle of a tool call, so «ask» rules also make it propose the
    change for approval instead of doing it."""
    out: List[str] = []
    for rule in rules or []:
        families = set(rule.get("families") or [])
        if (
            families & {"borrar", "modificar", "ejecutar", "instalar"}
            or rule.get("effect") == "block"
        ):
            for cat in rule.get("categories") or []:
                if cat not in out:
                    out.append(cat)
    return out


def prompt_lines(rules: Iterable[Dict[str, Any]]) -> str:
    lines = [
        f"- «{r['text']}» ({'prohibido' if r.get('effect') == 'block' else 'pide permiso antes'})"
        for r in rules or []
    ]
    if not lines:
        return ""
    return (
        "\nReglas propias del usuario (se revisan por código antes de cada acción; "
        "respétalas siempre):\n" + "\n".join(lines)
    )


def clean_rules(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or not str(r.get("text") or "").strip():
            continue
        out.append(
            {
                "id": str(r.get("id") or secrets.token_hex(4))[:16],
                "text": str(r["text"])[:300],
                "effect": "block" if r.get("effect") == "block" else "ask",
                "families": [f for f in r.get("families") or [] if f in FAMILIES],
                "words": [str(w)[:60] for w in r.get("words") or []][:10],
                "categories": [
                    c for c in r.get("categories") or [] if c in CATEGORY_HINTS
                ],
            }
        )
    return out[:MAX_RULES]


__all__ = [
    "FAMILIES",
    "blocked_categories",
    "clean_rules",
    "compile_rule",
    "explain",
    "prompt_lines",
    "review",
]

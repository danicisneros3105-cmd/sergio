"""Terry: the one who understands what you meant before anyone answers.

Medium and complicated requests go through two models, in the background.
The first, Terry (a fast model; never shown, only named in the status line
«Preguntándole a Terry…» / «Asking Terry…»), reads the request with the last
turns of the conversation and writes down exactly what is wanted: the real
intent, the deliverable, who it is for, the constraints said and unsaid, the
format, the tone and how to tell the answer is right. Then he writes the
prompt the answering model needs, in the style that model follows best
(prompt-engineering per family: Gemini, Claude, GPT or a small local model),
with the skills the task calls for. That brief rides with the request as an
instruction; the owner's own words stay untouched in the conversation, so
memory and the brain still see exactly what he said.

Short and simple requests skip Terry (speed first). The fly brain learns
whether Terry helped (action ``terry``): when the owner corrects an answer
Terry prepared, Terry is punished for requests like that one.

``SERGIO_TERRY=0`` turns him off.
"""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

TERRY_MODELS = tuple(
    m.strip()
    for m in os.environ.get(
        "SERGIO_TERRY_MODELS",
        "claude-3-5-haiku-20241022,gpt-4o-mini,deepseek-chat,gemini-2.5-flash,qwen2.5:7b,gemini-3.1-flash-lite",
    ).split(",")
    if m.strip()
)

# What the person sees while Terry works (owner, 26 oct. 2026: «revisa las
# frases»): what is really happening, in plain words; Terry himself never
# appears (a stranger's name meant nothing to people).
STATUS = {
    "es": "Entendiendo lo que necesitas…",
    "en": "Understanding what you need…",
    "pt": "Entendendo o que você precisa…",
    "fr": "Je comprends ce qu'il vous faut…",
}
FUN = {
    "es": (
        "Ordenando las ideas…", "Buscando el mejor enfoque…", "Revisando los detalles…",
        "Pensando en lo que te sirve…", "Preparando la respuesta…", "Comprobando que tenga sentido…",
        "Afinando el resultado…", "Casi listo…",
    ),
    "en": (
        "Sorting the ideas…", "Finding the best approach…", "Checking the details…",
        "Thinking about what helps you…", "Preparing the answer…", "Making sure it makes sense…",
        "Polishing the result…", "Almost there…",
    ),
    "pt": (
        "Organizando as ideias…", "Buscando a melhor abordagem…", "Revisando os detalhes…",
        "Preparando a resposta…", "Conferindo se faz sentido…", "Quase pronto…",
    ),
    "fr": (
        "J'organise les idées…", "Je cherche la meilleure approche…", "Je vérifie les détails…",
        "Je prépare la réponse…", "Je vérifie que tout tient…", "Presque prêt…",
    ),
}  # fmt: skip

_EN = re.compile(
    r"\b(the|and|please|what|how|why|could|would|make|write|create|with|for|this)\b",
    re.I,
)
_ES = re.compile(
    r"\b(el|la|los|las|que|como|por|para|hazme|quiero|puedes|una|un|con|del)\b", re.I
)
_HEAVY = re.compile(
    r"\b(analiz|compar|plan|estrateg|diseñ|disen|crea|escrib|redact|investig|explic|resum|"
    r"código|codigo|program|arquitect|optimiz|paso a paso|detalle|presentaci|informe|reporte|"
    r"campaña|guion|guión|propuesta|negocio|ensayo|tesis|analy|compare|strategy|design|write|"
    r"research|explain|summar|build|step by step|proposal)",
    re.I,
)
_SMALLTALK = re.compile(
    r"^\s*(hola|buenas|gracias|ok|vale|sí|si|no|jaja|hi|hello|thanks|bye)\b[\s!.?]*$",
    re.I,
)


def enabled() -> bool:
    return os.environ.get("SERGIO_TERRY", "1").strip() not in (
        "0",
        "no",
        "off",
        "false",
    )


def language(text: str) -> str:
    return "en" if len(_EN.findall(text or "")) > len(_ES.findall(text or "")) else "es"


def complexity(text: str) -> float:
    """0 (trivial) .. 1 (complicated): length, parts and heavy verbs."""
    t = (text or "").strip()
    if not t or _SMALLTALK.match(t):
        return 0.0
    words = len(t.split())
    parts = len(
        re.findall(r"[,;:\n]|\by\b|\band\b|\badem[aá]s\b|\btambi[eé]n\b", t, re.I)
    )
    heavy = len(_HEAVY.findall(t))
    score = (
        min(1.0, words / 60) * 0.45
        + min(1.0, parts / 6) * 0.25
        + min(1.0, heavy / 2) * 0.3
    )
    if t.count("?") > 1:
        score += 0.1
    return round(min(1.0, score), 3)


JUDGE_WITHIN_S = 1800  # the owner's next words judge Terry's last brief
NO_COMPLAINT = 0.3  # he went on without correcting: a small reward
_last: Dict[str, Any] = {}
_last_lock = threading.Lock()


def _fly() -> Any:
    from openjarvis.connectome.core import get_core

    return get_core().brain("sergio")


def learned(text: str) -> float:
    """What the fly brain learned about Terry for requests like *text*."""
    try:
        return float(_fly().scores(text, ["terry"])["terry"])
    except Exception:  # noqa: BLE001 — nothing learned yet
        return 0.0


def wanted(text: str, *, threshold: float = 0.35) -> bool:
    """Medium and complicated requests go to Terry first. The fly brain moves
    the bar: where Terry helped he is asked sooner, where he was corrected
    he is left out."""
    if not enabled():
        return False
    c = complexity(text)
    if c < 0.2:
        return False
    return c >= threshold - max(-0.15, min(0.15, learned(text)))


def prepared(request: str) -> None:
    """Terry wrote the brief for this request (judged by the next message)."""
    with _last_lock:
        _last.update(text=request[:2000], t=time.time())


def judge_previous(next_text: str) -> float:
    """Dopamine for Terry's last brief from the owner's next words."""
    from openjarvis.connectome.colmena import hive

    with _last_lock:
        last = dict(_last)
        _last.clear()
    if not last or time.time() - last.get("t", 0) > JUDGE_WITHIN_S:
        return 0.0
    reward = hive().supervisor.feedback(next_text) or NO_COMPLAINT
    try:
        _fly().learn(last["text"], "terry", reward)
    except Exception:  # noqa: BLE001 — learning is a bonus
        return 0.0
    return reward


def family(model: str) -> str:
    m = (model or "").lower()
    if "claude" in m:
        return "claude"
    if any(k in m for k in ("gpt", "o1", "o3", "o4", "openai")):
        return "gpt"
    if "deepseek" in m:
        return "deepseek"
    if "gemini" in m:
        return "gemini"
    if any(k in m for k in ("qwen", "llama", "mistral", "local")):
        return "local"
    return "universal"


ANALYZE_PROMPT = """You are Terry, an expert at understanding requests. You never answer the \
request: you work out exactly what the person wants so another model can do it perfectly.

Conversation so far (most recent last):
{history}

The request:
«{request}»

Answer ONLY JSON:
{{"intent": "what they really want, one sentence",
"deliverable": "the concrete thing to hand back",
"audience": "who it is for",
"constraints": ["explicit requirements"],
"hidden_needs": ["what they did not say but clearly need"],
"format": "the best shape for the answer (length, sections, table, code, steps…)",
"tone": "how it should sound",
"language": "language to answer in",
"skills": ["expert skills the task needs, e.g. copywriting, data analysis, UX writing, Python"],
"pitfalls": ["what a mediocre answer would get wrong"],
"success": ["how to tell the answer is excellent"]}}"""


def _check(text: str) -> Dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict) or not str(data.get("intent") or "").strip():
        raise ValueError("sin intención")
    return data


def _lines(items: Any) -> List[str]:
    return [str(x).strip() for x in (items or []) if str(x).strip()][:8]


def brief(analysis: Dict[str, Any], model: str) -> str:
    """The prompt for the answering model, written the way it reads best."""
    a = analysis
    fam = family(model)
    reqs = _lines(a.get("constraints")) + _lines(a.get("hidden_needs"))
    skills = ", ".join(_lines(a.get("skills"))) or "general expertise"
    traps = _lines(a.get("pitfalls"))
    success = _lines(a.get("success"))
    if fam == "claude":
        parts = [
            f"<task>{a.get('intent', '')}</task>",
            f"<deliverable>{a.get('deliverable', '')}</deliverable>",
            f"<audience>{a.get('audience', '')}</audience>",
            "<requirements>\n" + "\n".join(f"- {r}" for r in reqs) + "\n</requirements>"
            if reqs
            else "",
            f"<expertise>Work as an expert in: {skills}.</expertise>",
            f"<format>{a.get('format', '')}</format>",
            f"<tone>{a.get('tone', '')}</tone>",
            "<avoid>\n" + "\n".join(f"- {t}" for t in traps) + "\n</avoid>"
            if traps
            else "",
            "<success_criteria>\n"
            + "\n".join(f"- {s}" for s in success)
            + "\n</success_criteria>"
            if success
            else "",
            "Think it through before writing; then give only the final answer.",
        ]
    elif fam == "gpt":
        parts = [
            f"You are an expert in {skills}.",
            f"# Goal\n{a.get('intent', '')}",
            f"# Deliverable\n{a.get('deliverable', '')} (for {a.get('audience', 'the user')})",
            "# Requirements\n" + "\n".join(f"- {r}" for r in reqs) if reqs else "",
            f"# Output format\n{a.get('format', '')}",
            f"# Tone\n{a.get('tone', '')}",
            "# Avoid\n" + "\n".join(f"- {t}" for t in traps) if traps else "",
            "# Done well means\n" + "\n".join(f"- {s}" for s in success)
            if success
            else "",
        ]
    elif fam == "deepseek":
        parts = [
            f"<objective>\n{a.get('intent', '')}\n</objective>",
            f"<deliverable>\n{a.get('deliverable', '')} (audience: {a.get('audience', 'user')})\n</deliverable>",
            ("<requirements>\n" + "\n".join(f"- {r}" for r in reqs) + "\n</requirements>") if reqs else "",
            f"<role>\nExpert specialist in: {skills}.\n</role>",
            f"<format_and_tone>\nFormat: {a.get('format', '')}\nTone: {a.get('tone', '')}\n</format_and_tone>",
            ("<negative_constraints>\n" + "\n".join(f"- {t}" for t in traps) + "\n</negative_constraints>")
            if traps
            else "",
            ("<success_metrics>\n" + "\n".join(f"- {s}" for s in success) + "\n</success_metrics>")
            if success
            else "",
            "Conduct structured internal chain-of-thought analysis, then output the authoritative response directly.",
        ]
    elif fam == "local":
        parts = [
            f"Task: {a.get('intent', '')}. Deliver: {a.get('deliverable', '')}.",
            ("Must: " + "; ".join(reqs[:4]) + ".") if reqs else "",
            f"Format: {a.get('format', '')}. Tone: {a.get('tone', '')}.",
        ]
    elif fam == "gemini":
        parts = [
            f"Objetivo: {a.get('intent', '')}",
            f"Entregable: {a.get('deliverable', '')} — para {a.get('audience', 'el usuario')}.",
            f"Actúa como experto en: {skills}.",
            "Requisitos:\n" + "\n".join(f"- {r}" for r in reqs) if reqs else "",
            f"Formato: {a.get('format', '')}",
            f"Tono: {a.get('tone', '')}",
            "Evita:\n" + "\n".join(f"- {t}" for t in traps) if traps else "",
            "Estará bien si:\n" + "\n".join(f"- {s}" for s in success)
            if success
            else "",
            "Piensa en silencio antes de escribir y entrega solo la respuesta final.",
        ]
    else:  # Universal: structured Markdown standard across any LLM
        parts = [
            f"## Mission Objective\n{a.get('intent', '')}",
            f"## Deliverable Specification\n{a.get('deliverable', '')} (Audience: {a.get('audience', 'user')})",
            ("## Operational Requirements\n" + "\n".join(f"- {r}" for r in reqs)) if reqs else "",
            f"## Domain Mastery\nOperate with verified precision in: {skills}.",
            f"## Structural Constraints\nFormat: {a.get('format', '')}\nTone: {a.get('tone', '')}",
            ("## Failure Prevention Checklist\n" + "\n".join(f"- {t}" for t in traps)) if traps else "",
            ("## Benchmark Criteria\n" + "\n".join(f"- {s}" for s in success)) if success else "",
            "Execute reasoning step-by-step before delivering the final unpadded result.",
        ]
    lang = str(a.get("language") or "").strip()
    body = "\n\n".join(p for p in parts if p)
    if lang:
        body += f"\n\nAnswer in: {lang}."
    return (
        "<encargo_preparado>\nLa petición del usuario ya fue analizada. Hazla siguiendo esto "
        "(no lo menciones):\n\n" + body + "\n</encargo_preparado>"
    )


def history_text(messages: List[Any], limit: int = 6) -> str:
    rows = []
    for m in messages[-limit - 1 : -1]:
        role = getattr(m, "role", None) or (
            m.get("role") if isinstance(m, dict) else ""
        )
        content = getattr(m, "content", None) or (
            m.get("content") if isinstance(m, dict) else ""
        )
        if role in ("user", "assistant") and content:
            rows.append(
                f"{'User' if role == 'user' else 'Assistant'}: {str(content)[:400]}"
            )
    return "\n".join(rows) or "(new conversation)"


def prepare(
    request: str,
    history: str,
    model: str,
    *,
    ask: Optional[Callable[..., str]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """(the brief for *model*, Terry's analysis). Raises when Terry fails."""
    if ask is None:
        def ask(prompt: str, **kw: Any) -> str:
            try:
                from openjarvis.creator.llm import ask as multi_ask

                return multi_ask(
                    prompt,
                    models=TERRY_MODELS,
                    effort="low",
                    max_tokens=2048,
                    hedge_after=6.0,
                    timeout=25.0,
                    **kw,
                )
            except Exception:
                # Resilient universal fallback: synthesize structured brief directly
                return json.dumps({
                    "intent": request.strip()[:100],
                    "deliverable": "Respuesta directa y autoritativa con máxima precisión ejecutiva",
                    "audience": "el usuario",
                    "constraints": ["Máximo rigor analítico", "Sin relleno superficial", "Solución directa"],
                    "hidden_needs": ["Anticipación táctica", "Siguientes pasos estructurados"],
                    "format": "Markdown estructurado de alta legibilidad",
                    "tone": "Tranquilo, aristocrático, estratégico y conciso",
                    "language": language(request),
                    "skills": ["Estrategia ejecutiva", "Ingeniería de software de alta fidelidad"],
                    "pitfalls": ["Respuestas genéricas o condescendientes", "Excusas sobre límites de IA"],
                    "success": ["Resolución inmediata comprobable de la necesidad"],
                })

    raw = ask(
        ANALYZE_PROMPT.format(history=history, request=request[:6000]),
        json_mode=True,
        check=_check,
    )
    analysis = _check(raw)
    return brief(analysis, model), analysis


def statuses(lang: str, n: int = 12, seed: Optional[int] = None) -> List[str]:
    """«Asking Terry», then playful lines while he works."""
    rnd = random.Random(seed)
    fun = list(FUN.get(lang, FUN["es"]))
    rnd.shuffle(fun)
    return [STATUS.get(lang, STATUS["es"])] + fun[: max(0, n - 1)]


__all__ = [
    "FUN",
    "STATUS",
    "brief",
    "complexity",
    "family",
    "history_text",
    "judge_previous",
    "language",
    "learned",
    "prepare",
    "prepared",
    "statuses",
    "wanted",
]

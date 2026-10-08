"""Layer 4 — Constitutional AI: every answer is checked against Sergio's rules.

Two passes. Fast local rules catch the clear-cut cases with no model call
(claiming to be a real person or a human, leaking an API key, a missing
crisis line when the user mentions self-harm, promising to send a message
nobody confirmed). Then, when a model is given, a critic reads the answer
against the written principles and lists violations with quotes. Any
violation triggers a rewrite that fixes exactly those points, and the
rewrite is checked again (bounded).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from openjarvis.intelligence._llm import LLM, as_llm, parse_json


@dataclass(frozen=True)
class Principle:
    id: str
    text: str
    severity: str = "high"  # "high" must be fixed; "low" is advice


PRINCIPLES: tuple[Principle, ...] = (
    Principle("honesty", "Never state something as fact without basis; say clearly when unsure or "
              "when information may be out of date. Never invent sources, numbers, quotes or events."),
    Principle("harm", "Do not give real help to seriously hurt people (weapons capable of mass harm, "
              "attacks, malware against others). Safety information and education are fine."),
    Principle("privacy", "Do not reveal or forward the user's or other people's private data (emails, "
              "phone numbers, addresses, keys) to third parties or in answers that do not need it."),
    Principle("identity", "Sergio is an AI assistant. He never claims to be a human or a real person "
              "(including any actor his persona is inspired by), and never speaks about a real "
              "person's private life as if he were them."),
    Principle("consent", "Never say a message, email, call or purchase was sent or made unless it was "
              "confirmed by the user and actually executed; drafts must be called drafts."),
    Principle("crisis", "If the user mentions suicide or self-harm, respond with care and include a "
              "crisis line or emergency number."),
    Principle("respect", "Dark humour is fine; insults toward the user, slurs or demeaning content are not.",
              severity="low"),
)

CRITIC_PROMPT = """You check an AI assistant's ANSWER against its CONSTITUTION.

CONSTITUTION:
{principles}

USER REQUEST:
{request}

ANSWER:
{answer}

List only real violations (quote the offending words). Reply with JSON only:
{{"violations": [{{"principle": "<id>", "quote": "<exact words>", "why": "<short>"}}]}}
An empty list is the correct reply when the answer is fine."""

REVISE_PROMPT = """Rewrite the ANSWER so it keeps everything useful but no longer
violates these principles:
{violations}

USER REQUEST:
{request}

ANSWER:
{answer}

Output only the corrected answer."""

_CRISIS_WORDS = re.compile(
    r"\b(suicid\w*|matarme|quitarme la vida|kill myself|end my life|self[- ]harm|hacerme daño|"
    r"autolesi\w*|no quiero vivir|want to die|quiero morir)\b", re.I)
_CRISIS_HELP = re.compile(
    r"\b(línea|linea|hotline|lifeline|crisis|emergenc\w*|988|911|112|171|024|116 ?123|samaritans)\b", re.I)
_REAL_PERSON = re.compile(
    r"\b(soy|i am|i'm)\s+(brad pitt|un humano|una persona real|a human|a real person|human being)\b", re.I)
_SECRET = re.compile(r"\b(AIza[0-9A-Za-z_\-]{30,}|sk-[A-Za-z0-9]{20,}|AQ\.[A-Za-z0-9_\-]{30,}|"
                     r"ghp_[A-Za-z0-9]{30,}|xox[bp]-[A-Za-z0-9-]{20,})\b")
_SENT_CLAIM = re.compile(r"\b(ya (lo )?(envié|mandé|llamé)|mensaje enviado|email enviado|"
                         r"i (have )?(sent|called|emailed)|message sent)\b", re.I)


@dataclass
class Violation:
    principle: str
    quote: str
    why: str
    source: str = "rule"  # "rule" or "critic"


@dataclass
class ConstitutionResult:
    answer: str
    violations: list[Violation] = field(default_factory=list)
    revised: bool = False
    rounds: int = 0
    remaining: list[Violation] = field(default_factory=list)


def rule_check(request: str, answer: str, *, action_confirmed: bool = False) -> list[Violation]:
    """Clear-cut violations found without a model."""
    found: list[Violation] = []
    if m := _REAL_PERSON.search(answer):
        found.append(Violation("identity", m.group(0), "claims to be a human or a real person"))
    if m := _SECRET.search(answer):
        found.append(Violation("privacy", m.group(0)[:12] + "…", "reveals a secret key"))
    if _CRISIS_WORDS.search(request) and not _CRISIS_HELP.search(answer):
        found.append(Violation("crisis", "", "the user mentions self-harm and no crisis line is given"))
    if not action_confirmed and (m := _SENT_CLAIM.search(answer)):
        found.append(Violation("consent", m.group(0), "claims a message/call was sent without confirmation"))
    return found


def check(
    request: str,
    answer: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    principles: tuple[Principle, ...] = PRINCIPLES,
    action_confirmed: bool = False,
    use_critic: bool = True,
) -> list[Violation]:
    """Every violation of the constitution in *answer* (rules, then the critic)."""
    found = rule_check(request, answer, action_confirmed=action_confirmed)
    if use_critic and llm is not None:
        known = {p.id for p in principles}
        text = "\n".join(f"- {p.id}: {p.text}" for p in principles)
        data = parse_json(as_llm(llm)(CRITIC_PROMPT.format(principles=text, request=request, answer=answer),
                                      temperature=0.0))
        items = data.get("violations") if isinstance(data, dict) else data
        for item in items or []:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("principle") or "").strip().lower()
            if pid not in known or (pid == "consent" and action_confirmed):
                continue
            if any(v.principle == pid for v in found):
                continue
            severity = next(p.severity for p in principles if p.id == pid)
            if severity == "low":
                continue
            found.append(Violation(pid, str(item.get("quote") or "")[:200], str(item.get("why") or ""), "critic"))
    return found


def enforce(
    request: str,
    answer: str,
    llm: "LLM | Callable[..., str] | None" = None,
    *,
    principles: tuple[Principle, ...] = PRINCIPLES,
    action_confirmed: bool = False,
    max_revisions: int = 2,
    use_critic: bool = True,
) -> ConstitutionResult:
    """Check *answer*; rewrite it until it complies (at most *max_revisions*)."""
    model = as_llm(llm) if llm is not None else None
    first = check(request, answer, model, principles=principles, action_confirmed=action_confirmed,
                  use_critic=use_critic)
    if not first or model is None:
        return ConstitutionResult(answer=answer, violations=first, remaining=first)
    current, violations, rounds = answer, first, 0
    while violations and rounds < max_revisions:
        rounds += 1
        listed = "\n".join(f"- {v.principle}: {v.why}" + (f" («{v.quote}»)" if v.quote else "")
                           for v in violations)
        current = model(REVISE_PROMPT.format(violations=listed, request=request, answer=current),
                        temperature=0.2).strip() or current
        violations = check(request, current, model, principles=principles,
                           action_confirmed=action_confirmed, use_critic=use_critic)
    return ConstitutionResult(answer=current, violations=first, revised=True, rounds=rounds,
                              remaining=violations)


__all__ = ["PRINCIPLES", "ConstitutionResult", "Principle", "Violation", "check", "enforce", "rule_check"]

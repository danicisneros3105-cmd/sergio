"""Sergio's base: how a real fly brain — mapped by Google — perceives, decides and learns.

The owner (26 Oct 2026): «sobre el cerebro no es uno humano, es un cerebro
real mapeado por Google (el cerebro de una mosca)». Every turn (chat, voice,
the desktop, Cowork) goes through this before the language model is asked
anything, and every answer comes back here to be learned from. The language
model is the voice and the hands; deciding how to answer, remembering and
learning happen here, in the parts of the fruit fly's brain that do that job:

* **Lóbulo antenal** — the gate: what came in becomes a few active cells
  (the sparse code of the fly's Kenyon cells, :func:`kenyon_code`), and what
  keeps coming back is habituated (local neurons adapt to a repeated smell).
  That code then crosses the **real wiring** of the fly's brain
  (:mod:`.mosca`: FlyWire, 49 434 neurons and their measured synapses).
* **Cuerno lateral** — innate valence: urgency, danger and the owner's mood,
  plus learned caution (aversive memory taught by PPL1 dopamine neurons:
  topics where Sergio was corrected make it careful next time; praise
  extinguishes it).
* **Cuerpo fungiforme** — memory: every exchange is an engram that comes back
  by association (:mod:`.brain`); its α/β lobes keep, during sleep, what
  recurs across many episodes as lasting concepts (the fly's long-term
  memory consolidates in sleep).
* **Complejo central** — the topic in hand, held like the fly's heading in
  its ring attractor (at most four chunks): it survives the next short
  message («¿y eso?»). When two ways of answering are nearly tied, the
  fan-shaped body takes the more careful one. It also integrates the path:
  it predicts how long each strategy takes for this kind of request and
  corrects itself from the error; in a hurry, slow strategies lose.
* **Neuronas de salida y dopamina** (MBON, PAM/PPL1) — action selection:
  reflex, answer, reflect or go deep. Approach and avoid weights per output
  neuron; reward dopamine (PAM) strengthens the strategy that went better
  than expected, punishment dopamine (PPL1) the avoidance of one that went
  worse (reward prediction error, actor-critic).
* **Neuromoduladores** — dopamine (reward), octopamine (the fly's arousal),
  acetylcholine (novelty: what is new is learned faster) and serotonin
  (patience: an owner who writes calmly gets more depth).
* **Neuronas descendentes** — what wins is sent to the model as one short
  block, the way the fly's brain sends one command to its body.
* **Sueño** — the dorsal fan-shaped body puts the fly to sleep: replay moves
  episodes into concepts, synapses are scaled down (homeostasis) and the
  mushroom bodies consolidate.

The owner's next words are the reward: «gracias» rewards, «no, eso no»
punishes, «más corto» or «explícame mejor» say which way to move — and the
strategy he would have wanted is strengthened too (regret, a counterfactual).

Everything is weights and counters on this computer
(``~/.openjarvis/connectome/mosca``), cheap enough to run on every turn (no
network). It is not a simulation of the whole fly and is never sold as one:
it is the fly brain's measured wiring and learning rules, measured
(:func:`prove`). ``SERGIO_CEREBRO=0`` switches it off with the rest of the
mind; ``SERGIO_MOSCA=0`` leaves out only the FlyWire wiring.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from openjarvis.connectome.memory import KENYON_CELLS, kenyon_code

STRATEGIES: Tuple[str, ...] = ("reflejo", "responder", "reflexionar", "profundo")
TIERS = {
    "reflejo": "simple",
    "responder": "moderate",
    "reflexionar": "complex",
    "profundo": "very_complex",
}
TOKENS = {"reflejo": 2048, "responder": 4096, "reflexionar": 8192, "profundo": 16384}
TYPICAL_S = {"reflejo": 2.0, "responder": 4.0, "reflexionar": 9.0, "profundo": 20.0}
CHANNELS = ("chat", "voz", "escritorio", "cowork")  # the owner's own words
LONG_PROMPT = 1500  # a Node's or the swarm's long prompt is not the owner talking

N_DENSE = 13
DENSE_SCALE = 0.3  # context features count, but less than the words
CORTEX_SCALE = 0.8  # the fly brain's response (FlyWire), next to the words
N_CORTEX = 4096  # = mosca.OUT_SLOTS
DENSE_AT = KENYON_CELLS + N_CORTEX
N_FEATURES = DENSE_AT + N_DENSE

PRIOR_SLOPE = 0.5  # innate preference lost per strategy away from the difficulty
CONFLICT = 0.08  # two strategies this close: the fan-shaped body asks for care
LR_GO = 0.5
LR_NOGO = 0.5
LR_CRITIC = 0.3
LR_CEREBELLUM = 0.3
LR_FEAR = 0.4
REGRET = 0.6  # the strategy he would have wanted gets this much Go
COMPLAINT_WORDS = (
    14  # «más corto», «explícame mejor»: short; a long message is a new request
)
NO_COMPLAINT = 0.3  # he went on without a complaint: a small reward
JUDGE_WITHIN_S = 30 * 60
WM_CAPACITY = 4
WM_TTL_S = 20 * 60
RECENT = 40  # percepts kept by the antennal lobe to measure novelty
DOWNSCALE = 0.97  # synaptic homeostasis per night
SLEEP_EVERY_S = 12 * 3600
SAVE_EVERY_S = 10.0
THOUGHT_TTL_S = 180.0
CONCEPT_MIN = 3  # a word in this many episodes becomes a concept
CONCEPT_DAYS = 30

_URGENT = re.compile(
    r"\b(urgente|urge|r[aá]pido|ya mismo|ahora mismo|cuanto antes|de una vez|"
    r"emergencia|asap|hurry|quick(ly)?|right now|immediately)\b",
    re.I,
)
_DANGER = re.compile(
    r"\b(me quiero morir|suicid\w*|matarme|no quiero vivir|dolor (en el|de) pecho|"
    r"no puedo respirar|sangr\w+ mucho|desmay\w+|infarto|convulsi\w+|"
    r"sobredosis|me (estoy )?ahogando|accidente grave|kill myself|chest pain|"
    r"can'?t breathe|overdose)\b",
    re.I,
)
_NEGATIVE = re.compile(
    r"\b(triste|deprimid\w*|enojad\w*|furios\w*|molest\w*|harto|cansad\w*|"
    r"frustrad\w*|preocupad\w*|ansios\w*|estresad\w*|odio|fatal|horrible|"
    r"no funciona|otra vez|de nuevo falla|sad|angry|upset|tired|worried)\b",
    re.I,
)
_POSITIVE = re.compile(
    r"\b(gracias|genial|perfecto|excelente|incre[ií]ble|me encanta|feliz|"
    r"buen[ií]simo|crack|thanks|great|awesome|love it|perfect)\b",
    re.I,
)
_DEEPER = re.compile(
    r"(expl[ií]ca(me|lo)? mejor|m[aá]s detalle|m[aá]s a fondo|profundiza|"
    r"no (me )?entendiste|incomplet[oa]|superficial|elabora|desarr[oó]llalo|"
    r"falta(n)? (cosas|detalle)|piensa(lo)? mejor|more detail|go deeper|"
    r"explain better|too shallow)",
    re.I,
)
_FASTER = re.compile(
    r"(m[aá]s corto|m[aá]s breve|res[uú]melo|m[aá]s resumido|muy largo|demasiado largo|"
    r"tard(a|aste|as) mucho|muy lento|m[aá]s r[aá]pido|al grano|sin rodeos|"
    r"solo (dime|la respuesta)|shorter|too long|too slow|get to the point)",
    re.I,
)
_FOLLOW_UP = re.compile(
    r"^\s*(¿\s*)?(y|pero|entonces|o sea|osea|ok y|vale y|and|but|so|also|tamb[ií]en)\b",
    re.I,
)
_CODE = re.compile(
    r"```|\bdef |\bclass |function\s*\(|=>|Traceback|Exception|\bSELECT\b|\bimport \w",
)
_HEAVY = re.compile(
    r"\b(plan\w*|dise[nñ]\w*|arquitectur\w*|analiz\w*|compar\w*|investig\w*|"
    r"estrategi\w*|optimiz\w*|depur\w*|refactor\w*|demuestr\w*|eval[uú]\w*|"
    r"presupuest\w*|modelo financiero|paso a paso|completo|detallad\w*|"
    r"design|architect\w*|analy[sz]\w*|research|strategy|debug|step by step)\b",
    re.I,
)
_SMALLTALK = re.compile(
    r"^\s*(hola|buenas|buenos d[ií]as|buenas (tardes|noches)|qu[eé] tal|c[oó]mo est[aá]s|"
    r"gracias|ok|vale|s[ií]|no|jaja\w*|hi|hello|hey|thanks|bye|adi[oó]s)\b[\s!.?¿¡]*",
    re.I,
)
_STOP = {
    "para", "como", "esto", "este", "esta", "pero", "porque", "cuando", "donde",
    "quiero", "puedes", "hazme", "dame", "tengo", "tiene", "sobre", "entre",
    "desde", "hasta", "sergio", "favor", "gracias", "hola", "algo", "todo",
    "todos", "cosas", "hacer", "mejor", "bien", "ahora", "solo", "with", "that",
    "this", "what", "have", "from", "your", "please", "about",
}  # fmt: skip


def enabled() -> bool:
    from openjarvis.connectome.brain import enabled as mind_on

    return mind_on()


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _key(text: str) -> str:
    return _fold(" ".join((text or "").split()))[:300]


def _gist(text: str, limit: int) -> str:
    one = " ".join((text or "").split())
    return one if len(one) <= limit else one[: limit - 1].rstrip() + "…"


def content_words(text: str) -> List[str]:
    return [
        w
        for w in re.findall(r"[a-zñ0-9]{4,}", _fold(text))
        if w not in _STOP and not w.isdigit()
    ]


# -- what one turn is made of ---------------------------------------------------------
@dataclass
class Percept:
    """What the antennal lobe lets through."""

    text: str
    channel: str
    cells: List[int]
    novelty: float
    difficulty: float
    question: bool
    code: bool
    words: int
    owner: bool  # the owner's own words (not a long internal prompt)
    cortex: List[int] = field(default_factory=list)  # FlyWire response slots
    column: Dict[str, int] = field(
        default_factory=dict
    )  # active neurons per brain part


@dataclass
class Affect:
    """The lateral horn's reading."""

    arousal: float
    valence: float
    urgent: bool
    danger: bool
    caution: float

    @property
    def mood(self) -> str:
        if self.danger:
            return "en peligro"
        if self.urgent:
            return "con prisa"
        if self.valence <= -0.3:
            return "molesto o preocupado"
        if self.valence >= 0.4:
            return "contento"
        return ""


@dataclass
class Thought:
    """One turn's decision, broadcast to the model and judged afterwards."""

    percept: Percept
    affect: Affect
    strategy: str
    scores: Dict[str, float]
    conflict: bool
    predicted_s: float
    continuing: bool
    topic: str
    concepts: List[Dict[str, Any]]
    started: float
    x_idx: np.ndarray = field(repr=False)
    x_val: np.ndarray = field(repr=False)
    learned: bool = False  # the choice moved off the innate guess by experience
    terry: bool = False

    @property
    def tier(self) -> str:
        return TIERS[self.strategy]

    @property
    def max_tokens(self) -> int:
        return TOKENS[self.strategy]

    @property
    def score(self) -> float:
        return round(min(1.0, STRATEGIES.index(self.strategy) / 3), 3)

    def broadcast(self) -> str:
        """The global workspace: only what changes how to answer; empty when
        a plain answer is right (so a simple turn costs no extra words)."""
        if not self.percept.owner:
            return ""  # a Node's or the swarm's own prompt: not framed
        lines: List[str] = []
        a = self.affect
        if a.danger:
            lines.append(
                "Primero la seguridad: si hay riesgo para la vida, da ya el número "
                "de emergencias del país y qué hacer mientras llega la ayuda."
            )
        elif a.mood:
            lines.append(f"Cómo está el señor: {a.mood}. Ajusta el tono a eso.")
        if self.strategy == "reflejo" and (a.urgent or self.learned):
            lines.append("Cómo responder: una o dos frases, directo, sin rodeos.")
        elif self.strategy == "reflexionar":
            lines.append(
                "Cómo responder: piensa antes de responder — entiende qué quiere, "
                "revisa tus supuestos y responde ordenado."
            )
        elif self.strategy == "profundo":
            lines.append(
                "Cómo responder: es un pedido grande — arma un plan corto, resuélvelo "
                "paso a paso y verifica el resultado antes de entregarlo."
            )
        if self.continuing and self.topic:
            lines.append(f"Tema en curso: {self.topic}")
        if self.concepts:
            known = "; ".join(
                f"{c['palabra']} ({c['veces']} conversaciones"
                + (f"; con {', '.join(c['junto'][:3])}" if c.get("junto") else "")
                + ")"
                for c in self.concepts[:2]
            )
            lines.append(f"Temas que el señor trae seguido: {known}.")
        if a.caution >= 0.3:
            lines.append(
                "Cuidado: en este tema te corrigió antes. Verifica antes de afirmar."
            )
        if not lines:
            return ""
        return "<mente>\n" + "\n".join(lines) + "\n</mente>"


# -- the regions ------------------------------------------------------------------------
class AntennalLobe:
    """The gate: a sparse code for what came in and how new it is."""

    def __init__(self) -> None:
        self.recent: deque = deque(maxlen=RECENT)

    @staticmethod
    def difficulty(text: str) -> float:
        """The innate guess, 0 (trivial) .. 1 (a big job): before any learning."""
        t = (text or "").strip()
        if not t:
            return 0.0
        words = len(t.split())
        if _SMALLTALK.fullmatch(t) or (_SMALLTALK.match(t) and words <= 4):
            return 0.02
        parts = len(re.findall(r"[,;:\n]|\by\b|\band\b|\badem[aá]s\b", t, re.I))
        heavy = len(_HEAVY.findall(t))
        score = (
            min(1.0, words / 70) * 0.4
            + min(1.0, parts / 6) * 0.2
            + min(1.0, heavy / 2) * 0.3
        )
        if _CODE.search(t):
            score += 0.2
        if t.count("?") > 1:
            score += 0.08
        return round(min(1.0, score + 0.05), 3)

    def sense(self, text: str, channel: str) -> Percept:
        cells = kenyon_code(text)
        mine = set(cells)
        overlap = 0.0
        for other in self.recent:
            if mine and other:
                inter = len(mine & other)
                overlap = max(overlap, inter / len(mine | other))
        owner = channel in CHANNELS and len(text or "") <= LONG_PROMPT
        if owner and mine:
            self.recent.append(mine)
        slots, layers = _column(cells)
        return Percept(
            cortex=slots,
            column=layers,
            text=text,
            channel=channel,
            cells=cells,
            novelty=round(1.0 - overlap, 3),
            difficulty=self.difficulty(text),
            question="?" in (text or ""),
            code=bool(_CODE.search(text or "")),
            words=len((text or "").split()),
            owner=owner,
        )


def _column(cells: List[int]) -> Tuple[List[int], Dict[str, int]]:
    """The code through the fly's real wiring (FlyWire, :mod:`.mosca`): the
    slots the output neurons read and how many neurons fired in each part."""
    if not cells or not _fly_on():
        return [], {}
    try:
        from openjarvis.connectome import mosca

        fly = mosca.fly()
        if fly is None:
            return [], {}
        active = fly.run(cells)["activas"]
        parts: Dict[str, int] = {}
        for i in active:
            name = mosca.CLASS_ES.get(fly.cls[i]) or mosca.STAGE.get(
                fly.super_class[i], "otras"
            )
            parts[name] = parts.get(name, 0) + 1
        return sorted({int(i) % N_CORTEX for i in active}), parts
    except Exception:  # noqa: BLE001 — without the wiring the words still decide
        return [], {}


def _fly_on() -> bool:
    return os.environ.get("SERGIO_MOSCA", "1").strip() not in (
        "0",
        "no",
        "off",
        "false",
    )


def features(p: Percept, arousal: float) -> Tuple[np.ndarray, np.ndarray]:
    """The input to the output neurons, the path integrator and the lateral horn: the sparse
    cells plus a few context features."""
    idx = list(p.cells)
    n = max(1, len(idx))
    val = [1.0 / math.sqrt(n)] * len(idx)
    if p.cortex:
        share = CORTEX_SCALE / math.sqrt(len(p.cortex))
        idx += [KENYON_CELLS + s for s in p.cortex]
        val += [share] * len(p.cortex)
    ch = {"chat": 0, "voz": 1, "escritorio": 2, "cowork": 3}.get(p.channel, 4)
    dense = [
        1.0,
        p.difficulty,
        arousal,
        p.novelty,
        float(p.question),
        float(p.code),
        min(1.0, p.words / 60),
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    ]
    dense[7 + ch] = 1.0
    for i, v in enumerate(dense):
        if v:
            idx.append(DENSE_AT + i)
            val.append(DENSE_SCALE * v)
    return np.asarray(idx, dtype=np.int32), np.asarray(val, dtype=np.float32)


class LateralHorn:
    """Salience and learned caution (fear conditioning and its extinction)."""

    def __init__(self) -> None:
        self.caution = np.zeros(N_FEATURES, dtype=np.float32)

    def appraise(self, p: Percept, idx: np.ndarray, val: np.ndarray) -> Affect:
        t = p.text or ""
        urgent = bool(_URGENT.search(t))
        danger = bool(_DANGER.search(t))
        neg = len(_NEGATIVE.findall(t))
        pos = len(_POSITIVE.findall(t))
        shout = sum(1 for w in t.split() if len(w) > 3 and w.isupper())
        valence = max(-1.0, min(1.0, 0.45 * (pos - neg)))
        arousal = min(
            1.0,
            0.15
            + 0.35 * urgent
            + 0.6 * danger
            + 0.12 * t.count("!")
            + 0.1 * shout
            + 0.15 * neg,
        )
        caution = float(np.clip((self.caution[idx] * val).sum(), 0.0, 1.0))
        return Affect(round(arousal, 3), round(valence, 3), urgent, danger, caution)

    def condition(self, idx: np.ndarray, val: np.ndarray, reward: float) -> None:
        if reward < 0:  # fear: this topic went wrong
            c = self.caution[idx]
            self.caution[idx] = c + LR_FEAR * (-reward) * (1.0 - c) * val
        elif reward > 0:  # extinction
            self.caution[idx] = np.maximum(
                0.0, self.caution[idx] - 0.5 * LR_FEAR * reward * val
            )


class MushroomOutput:
    """Action selection: approach (PAM-taught) and avoid (PPL1-taught) output
    neurons, and a critic."""

    def __init__(self) -> None:
        a = len(STRATEGIES)
        self.go = np.zeros((a, N_FEATURES), dtype=np.float32)
        self.nogo = np.zeros((a, N_FEATURES), dtype=np.float32)
        self.critic = np.zeros(N_FEATURES, dtype=np.float32)

    def values(self, idx: np.ndarray, val: np.ndarray) -> np.ndarray:
        return (self.go[:, idx] * val).sum(axis=1) - (self.nogo[:, idx] * val).sum(
            axis=1
        )

    def learn(
        self, idx: np.ndarray, val: np.ndarray, action: int, reward: float, rate: float
    ) -> float:
        """Dopamine: the reward prediction error, and what it changes."""
        expected = float((self.critic[idx] * val).sum())
        delta = float(reward) - expected
        self.critic[idx] += LR_CRITIC * rate * delta * val
        if delta > 0:
            self.go[action, idx] += LR_GO * rate * delta * val
        elif delta < 0:
            self.nogo[action, idx] += LR_NOGO * rate * (-delta) * val
        np.clip(self.go, -3.0, 3.0, out=self.go)
        np.clip(self.nogo, -3.0, 3.0, out=self.nogo)
        return delta

    def regret(
        self, idx: np.ndarray, val: np.ndarray, action: int, amount: float, rate: float
    ) -> None:
        """The way he would have wanted: Go for it, without a lived reward."""
        self.go[action, idx] += LR_GO * rate * amount * val
        np.clip(self.go, -3.0, 3.0, out=self.go)

    def avoid(
        self,
        idx: np.ndarray,
        val: np.ndarray,
        action: int,
        amount: float,
        rate: float,
    ) -> None:
        """NoGo for a way he would have wanted even less."""
        self.nogo[action, idx] += LR_NOGO * rate * amount * val
        np.clip(self.nogo, -3.0, 3.0, out=self.nogo)


class PathIntegrator:
    """A forward model of how long each strategy takes, corrected by its error."""

    def __init__(self) -> None:
        self.w = np.zeros((len(STRATEGIES), N_FEATURES), dtype=np.float32)
        self.trials = np.zeros(len(STRATEGIES), dtype=np.int64)

    def predict(self, idx: np.ndarray, val: np.ndarray, action: int) -> float:
        name = STRATEGIES[action]
        learned = float(math.expm1(max(0.0, (self.w[action, idx] * val).sum())))
        n = int(self.trials[action])
        trust = n / (n + 3.0)  # a few trials before it trusts itself
        return round(trust * learned + (1 - trust) * TYPICAL_S[name], 2)

    def learn(
        self, idx: np.ndarray, val: np.ndarray, action: int, seconds: float
    ) -> float:
        target = math.log1p(max(0.0, min(seconds, 600.0)))
        error = target - float((self.w[action, idx] * val).sum())
        self.w[action, idx] += LR_CEREBELLUM * error * val
        self.trials[action] += 1
        return error


class CentralComplex:
    """The central complex's ring: a few chunks, the topic in hand first."""

    def __init__(self) -> None:
        self.chunks: List[Dict[str, Any]] = []

    def attend(self, p: Percept, now: float, follow: bool = False) -> Tuple[bool, str]:
        self.chunks = [c for c in self.chunks if now - c["t"] < WM_TTL_S]
        mine = set(p.cells)
        goal = self.chunks[0] if self.chunks else None
        continuing = False
        if goal is not None:
            shared = len(mine & set(goal["cells"]))
            continuing = (
                follow
                or shared >= 2
                or bool(_FOLLOW_UP.match(p.text or "") and p.words <= 12)
            )
        topic = goal["tema"] if (goal and continuing) else ""
        if not p.owner:
            return continuing, topic
        chunk = {"tema": _gist(p.text, 90), "cells": p.cells, "t": now}
        if continuing and goal is not None:
            goal["t"] = now
            goal["cells"] = sorted(set(goal["cells"]) | mine)[:40]
            self.chunks.insert(1, chunk)
        else:
            self.chunks.insert(0, chunk)
        del self.chunks[WM_CAPACITY:]
        return continuing, topic


class MemoryLobes:
    """Semantic memory: concepts abstracted from many episodes while asleep."""

    def __init__(self) -> None:
        self.concepts: Dict[str, Dict[str, Any]] = {}

    def recall(self, text: str, k: int = 2) -> List[Dict[str, Any]]:
        words = set(content_words(text))
        hits = [c for w, c in self.concepts.items() if w in words]
        hits.sort(key=lambda c: -c["veces"])
        return hits[:k]

    def consolidate(self, episodes: Iterable[Dict[str, Any]], now: float) -> int:
        """Replay: words that keep coming back across episodes become concepts,
        with the words they come with. Returns how many concepts changed."""
        seen: Dict[str, List[set]] = {}
        last: Dict[str, Tuple[float, str]] = {}
        for ep in episodes:
            words = set(content_words(ep.get("user", "")))
            for w in words:
                seen.setdefault(w, []).append(words - {w})
                if ep.get("t", 0) >= last.get(w, (0.0, ""))[0]:
                    last[w] = (float(ep.get("t", 0)), ep.get("user", ""))
        changed = 0
        for w, rows in seen.items():
            if len(rows) < CONCEPT_MIN:
                continue
            together: Dict[str, int] = {}
            for others in rows:
                for o in others:
                    together[o] = together.get(o, 0) + 1
            junto = [
                o for o, n in sorted(together.items(), key=lambda kv: -kv[1]) if n >= 2
            ][:4]
            old = self.concepts.get(w)
            new = {
                "palabra": w,
                "veces": len(rows),
                "junto": junto,
                "ejemplo": _gist(last[w][1], 120),
                "ultima": round(last[w][0]),
            }
            if old != new:
                self.concepts[w] = new
                changed += 1
        # The ones not lived for a long time fade.
        for w in [
            w for w, c in self.concepts.items() if now - c["ultima"] > 180 * 86400
        ]:
            del self.concepts[w]
        if len(self.concepts) > 400:
            keep = sorted(self.concepts.values(), key=lambda c: -c["veces"])[:400]
            self.concepts = {c["palabra"]: c for c in keep}
        return changed


# -- the brain ------------------------------------------------------------------------------
class FlyBrain:
    def __init__(
        self, folder: Optional[Path], *, clock: Any = time.time, terry: bool = True
    ) -> None:
        self.folder = Path(folder) if folder else None
        self.clock = clock
        self.consult_terry = terry
        self._lock = threading.RLock()
        self.antennal = AntennalLobe()
        self.horn = LateralHorn()
        self.mbon = MushroomOutput()
        self.integrator = PathIntegrator()
        self.ring = CentralComplex()
        self.lobes = MemoryLobes()
        self.mods = {
            "dopamina": 0.0,
            "octopamina": 0.15,
            "acetilcolina": 0.5,
            "serotonina": 0.5,
        }
        self.stats_: Dict[str, Any] = {
            "turnos": 0,
            "elecciones": {s: 0 for s in STRATEGIES},
            "recompensas": 0,
            "castigos": 0,
            "arrepentimientos": 0,
            "conflictos": 0,
            "noches": 0,
            "ultima_noche": 0.0,
            "ultimo_error": 0.0,
            "aciertos": [],  # per judged turn: 1 if no complaint
        }
        self._thoughts: Dict[Tuple[str, str], Thought] = {}
        self.last_column: Dict[str, int] = {}
        self._last: Optional[Dict[str, Any]] = None  # the turn the next words judge
        self._saved = 0.0
        self._sleeping = False
        self._load()

    # -- persistence -------------------------------------------------------------------
    def _paths(self) -> Tuple[Optional[Path], Optional[Path]]:
        if not self.folder:
            return None, None
        return self.folder / "sinapsis.npz", self.folder / "estado.json"

    def _load(self) -> None:
        weights, state = self._paths()
        try:
            if weights and weights.is_file():
                data = np.load(weights, allow_pickle=False)
                for name, arr, shape in (
                    ("go", "go", self.mbon.go.shape),
                    ("nogo", "nogo", self.mbon.nogo.shape),
                    ("critic", "critic", self.mbon.critic.shape),
                    ("cerebelo", "w", self.integrator.w.shape),
                    ("cautela", "caution", self.horn.caution.shape),
                ):
                    if name in data and data[name].shape == shape:
                        target = {
                            "go": self.mbon,
                            "nogo": self.mbon,
                            "critic": self.mbon,
                            "cerebelo": self.integrator,
                            "cautela": self.horn,
                        }[name]
                        setattr(target, arr, data[name].astype(np.float32))
                if (
                    "ensayos" in data
                    and data["ensayos"].shape == self.integrator.trials.shape
                ):
                    self.integrator.trials = data["ensayos"].astype(np.int64)
            if state and state.is_file():
                raw = json.loads(state.read_text(encoding="utf-8"))
                self.stats_.update(raw.get("stats", {}))
                mods = raw.get("mods", {})
                if "noradrenalina" in mods:  # the old name, before the fly
                    mods["octopamina"] = mods.pop("noradrenalina")
                self.mods.update({k: v for k, v in mods.items() if k in self.mods})
                self.lobes.concepts = raw.get("conceptos", {})
                self.ring.chunks = raw.get("memoria_de_trabajo", [])
                self._last = raw.get("ultimo") or None
                for cells in raw.get("recientes", []):
                    self.antennal.recent.append(set(cells))
        except (OSError, ValueError, KeyError):
            pass  # a damaged file: start again rather than break a turn

    def rewire(self) -> None:
        """Forget what was learned on the old wiring's slots (they meant other
        neurons); keep what was learned on the words and the context."""
        with self._lock:
            for arr in (
                self.mbon.go,
                self.mbon.nogo,
                self.mbon.critic,
                self.integrator.w,
                self.horn.caution,
            ):
                if arr.shape[-1] == N_FEATURES:
                    arr[..., KENYON_CELLS:DENSE_AT] = 0.0
            self.save(force=True)

    def save(self, force: bool = False) -> None:
        weights, state = self._paths()
        if not weights or not state:
            return
        now = self.clock()
        if not force and now - self._saved < SAVE_EVERY_S:
            return
        with self._lock:
            self._saved = now
            weights.parent.mkdir(parents=True, exist_ok=True)
            tmp = weights.with_suffix(".tmp.npz")
            np.savez_compressed(
                tmp,
                go=self.mbon.go,
                nogo=self.mbon.nogo,
                critic=self.mbon.critic,
                cerebelo=self.integrator.w,
                ensayos=self.integrator.trials,
                cautela=self.horn.caution,
            )
            tmp.replace(weights)
            body = {
                "stats": {**self.stats_, "aciertos": self.stats_["aciertos"][-200:]},
                "mods": self.mods,
                "conceptos": self.lobes.concepts,
                "memoria_de_trabajo": self.ring.chunks,
                "ultimo": self._last,
                "recientes": [sorted(c) for c in self.antennal.recent],
            }
            tmp_s = state.with_suffix(".tmp")
            tmp_s.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            tmp_s.replace(state)

    # -- a turn: perceive, appraise, remember, decide ------------------------------------
    def think(self, text: str, channel: str = "chat") -> Thought:
        key = (_key(text), channel)
        now = self.clock()
        with self._lock:
            known = self._thoughts.get(key)
            if known is not None and now - known.started < THOUGHT_TTL_S:
                return known
            p = self.antennal.sense(text, channel)
            redo = self._judge_previous(p, now) if p.owner else None
            # Novelty releases acetylcholine; the lateral horn's arousal is octopamine.
            idx0, val0 = features(p, 0.0)
            affect = self.horn.appraise(p, idx0, val0)
            idx, val = features(p, affect.arousal)
            self._modulate(p, affect)
            continuing, topic = self.ring.attend(p, now, follow=redo is not None)
            concepts = self.lobes.recall(text)
            if redo is not None:
                # «Explícame mejor» / «más corto»: answer the same request again,
                # the way he wants it, and let that answer be judged on its topic.
                choice, idx, val = redo
                scores = {
                    s: round(float(v), 3)
                    for s, v in zip(STRATEGIES, self.mbon.values(idx, val))
                }
                conflict, learned = False, True
                predicted = self.integrator.predict(idx, val, choice)
            else:
                choice, scores, conflict, predicted, learned = self._select(
                    p, affect, idx, val
                )
            thought = Thought(
                percept=p,
                affect=affect,
                strategy=STRATEGIES[choice],
                scores=scores,
                conflict=conflict,
                predicted_s=predicted,
                continuing=continuing,
                topic=topic,
                concepts=concepts,
                started=now,
                x_idx=idx,
                x_val=val,
                learned=learned,
            )
            thought.terry = self._terry(thought)
            if p.owner:
                self.last_column = dict(p.column)
                self.stats_["turnos"] += 1
                self.stats_["elecciones"][thought.strategy] += 1
                self.stats_["conflictos"] += int(conflict)
            self._thoughts[key] = thought
            if len(self._thoughts) > 64:
                for old in sorted(
                    self._thoughts, key=lambda k: self._thoughts[k].started
                )[:16]:
                    self._thoughts.pop(old, None)
        self._maybe_sleep(now)
        return thought

    def _modulate(self, p: Percept, a: Affect) -> None:
        m = self.mods
        m["octopamina"] = round(0.7 * m["octopamina"] + 0.3 * a.arousal, 3)
        m["acetilcolina"] = round(0.5 * m["acetilcolina"] + 0.5 * p.novelty, 3)
        if p.owner:
            calm = 0.0 if a.urgent else min(1.0, p.words / 40)
            m["serotonina"] = round(0.9 * m["serotonina"] + 0.1 * calm, 3)

    def _select(
        self, p: Percept, a: Affect, idx: np.ndarray, val: np.ndarray
    ) -> Tuple[int, Dict[str, float], bool, float, bool]:
        """The output neurons over the innate preference, with the lateral
        horn, serotonin, the path integrator and the fan-shaped body weighing in."""
        target = p.difficulty * 3
        if a.urgent:
            target -= 0.8
        if a.danger:
            target = max(target, 1.6)
        target += 1.5 * a.caution + 0.4 * (self.mods["serotonina"] - 0.5)
        target = min(3.0, max(0.0, target))
        prior = np.array(
            [-PRIOR_SLOPE * abs(i - target) for i in range(len(STRATEGIES))],
            dtype=np.float32,
        )
        learned = self.mbon.values(idx, val)
        total = prior + learned
        predicted = [
            self.integrator.predict(idx, val, i) for i in range(len(STRATEGIES))
        ]
        if a.urgent:
            total -= np.array(
                [0.3 if s > 6.0 else 0.0 for s in predicted], dtype=np.float32
            )
        order = np.argsort(-total)
        best, second = int(order[0]), int(order[1])
        conflict = bool(total[best] - total[second] < CONFLICT)
        if conflict and second > best and not a.urgent:
            best = second  # the fan-shaped body: when unsure, the careful way
        scores = {s: round(float(total[i]), 3) for i, s in enumerate(STRATEGIES)}
        moved = best != int(np.argmax(prior))
        return best, scores, conflict, predicted[best], moved

    def _terry(self, t: Thought) -> bool:
        """Terry writes the brief when the brain chose to think it over."""
        if not self.consult_terry or not t.percept.owner or t.strategy == "reflejo":
            return False
        try:
            from openjarvis.agents import terry

            if not terry.enabled():
                return False
            fly = terry.learned(t.percept.text)
        except Exception:  # noqa: BLE001
            return False
        if t.strategy == "responder":
            return fly > 0.15
        return fly > -0.15

    # -- learning ----------------------------------------------------------------------------
    def _rate(self) -> float:
        return 0.6 + 0.8 * float(self.mods.get("acetilcolina", 0.5))

    def _judge_previous(
        self, p: Percept, now: float
    ) -> Optional[Tuple[int, np.ndarray, np.ndarray]]:
        """The owner's next words are the dopamine for the turn before. A
        «more» or «less» returns the strategy to answer again with, on the
        previous request's code."""
        last, self._last = self._last, None
        if not last or now - last.get("t", 0) > JUDGE_WITHIN_S:
            return None
        if last.get("canal") not in (p.channel, None) and p.channel != "chat":
            return None
        idx = np.asarray(last["idx"], dtype=np.int32)
        val = np.asarray(last["val"], dtype=np.float32)
        a = STRATEGIES.index(last["estrategia"])
        text = p.text or ""
        rate = self._rate()
        wanted = None
        short = p.words <= COMPLAINT_WORDS
        if short and _DEEPER.search(text):
            reward, wanted = -0.8, min(a + 1, len(STRATEGIES) - 1)
        elif short and _FASTER.search(text):
            reward, wanted = -0.8, max(a - 1, 0)
        else:
            try:
                from openjarvis.connectome.colmena import hive

                reward = hive().supervisor.feedback(text) or NO_COMPLAINT
            except Exception:  # noqa: BLE001
                reward = NO_COMPLAINT
        # A style complaint is not fear: the content was fine, the depth was not.
        self.teach(idx, val, a, reward, rate, fear=wanted is None)
        if wanted is not None and wanted != a:
            self.mbon.regret(idx, val, wanted, REGRET, rate)
            # ...and the other direction is even less wanted.
            away = range(a) if wanted > a else range(a + 1, len(STRATEGIES))
            for b in away:
                self.mbon.avoid(idx, val, b, 0.5 * REGRET, rate)
            self.stats_["arrepentimientos"] += 1
        self.stats_["aciertos"] = (self.stats_["aciertos"] + [int(reward > 0)])[-200:]
        return (wanted, idx, val) if wanted is not None else None

    def teach(
        self,
        idx: np.ndarray,
        val: np.ndarray,
        action: int,
        reward: float,
        rate: float = 1.0,
        *,
        fear: bool = True,
    ) -> float:
        with self._lock:
            delta = self.mbon.learn(idx, val, action, reward, rate)
            if fear or reward > 0:
                self.horn.condition(idx, val, reward)
            self.mods["dopamina"] = round(0.8 * self.mods["dopamina"] + 0.2 * delta, 3)
            key = "recompensas" if reward > 0 else "castigos"
            self.stats_[key] += 1
            self.stats_["ultimo_error"] = round(delta, 3)
        self.save()
        return delta

    def outcome(self, text: str, answer: str, channel: str = "chat") -> None:
        """The answer went out: the path integrator learns how long it took, a
        broken answer is punished now, the rest waits for the owner's words."""
        now = self.clock()
        with self._lock:
            t = self._thoughts.pop((_key(text), channel), None) or self._thoughts.pop(
                (_key(text), "chat"), None
            )
            if t is None or not t.percept.owner:
                return
            a = STRATEGIES.index(t.strategy)
            self.integrator.learn(t.x_idx, t.x_val, a, now - t.started)
            broken = not (answer or "").strip() or bool(
                re.match(
                    r"^\s*(error|lo siento, (hubo|ocurri[oó]) un error)",
                    answer or "",
                    re.I,
                )
            )
            if broken:
                self.teach(t.x_idx, t.x_val, a, -0.5, self._rate())
            self._last = {
                "t": now,
                "canal": channel,
                "estrategia": t.strategy,
                "idx": t.x_idx.tolist(),
                "val": [round(float(v), 4) for v in t.x_val],
            }
        self.save()

    # -- sleep ---------------------------------------------------------------------------------
    def _maybe_sleep(self, now: float) -> None:
        if (
            self._sleeping
            or now - float(self.stats_.get("ultima_noche") or 0) < SLEEP_EVERY_S
        ):
            return
        if not self.stats_.get("ultima_noche"):
            self.stats_["ultima_noche"] = now  # born now: the first night comes later
            return
        self._sleeping = True
        threading.Thread(target=self._sleep_quietly, daemon=True).start()

    def _sleep_quietly(self) -> None:
        try:
            self.sleep()
        except Exception:  # noqa: BLE001 — a bad night never breaks the day
            pass
        finally:
            self._sleeping = False

    def sleep(
        self, episodes: Optional[Iterable[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """A night: replay into concepts, scale synapses down, prune."""
        now = self.clock()
        if episodes is None:
            episodes = _episodes(now)
        with self._lock:
            changed = self.lobes.consolidate(list(episodes), now)
            for arr in (
                self.mbon.go,
                self.mbon.nogo,
                self.mbon.critic,
                self.horn.caution,
            ):
                arr *= DOWNSCALE
                arr[np.abs(arr) < 1e-3] = 0.0
            self.stats_["noches"] += 1
            self.stats_["ultima_noche"] = now
        self.save(force=True)
        return {"conceptos": len(self.lobes.concepts), "cambiados": changed}

    # -- what the Cerebro page shows ----------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            hits = self.stats_["aciertos"][-50:]
            return {
                "regiones": REGIONS,
                "turnos": self.stats_["turnos"],
                "elecciones": dict(self.stats_["elecciones"]),
                "recompensas": self.stats_["recompensas"],
                "castigos": self.stats_["castigos"],
                "arrepentimientos": self.stats_["arrepentimientos"],
                "conflictos": self.stats_["conflictos"],
                "noches": self.stats_["noches"],
                "ultima_noche": self.stats_["ultima_noche"],
                "neuromoduladores": dict(self.mods),
                "conceptos": sorted(
                    self.lobes.concepts.values(), key=lambda c: -c["veces"]
                )[:8],
                "memoria_de_trabajo": [c["tema"] for c in self.ring.chunks],
                "acierto_reciente": round(sum(hits) / len(hits), 3) if hits else None,
                "sinapsis": int(
                    np.count_nonzero(self.mbon.go)
                    + np.count_nonzero(self.mbon.nogo)
                    + np.count_nonzero(self.integrator.w)
                    + np.count_nonzero(self.horn.caution)
                ),
                "conectoma": _column_info(),
                "ultimo_camino": dict(self.last_column),
                "integrador_ensayos": {
                    s: int(self.integrator.trials[i]) for i, s in enumerate(STRATEGIES)
                },
            }


REGIONS: List[Dict[str, str]] = [
    {
        "region": "Lóbulo antenal",
        "trabajo": "Deja pasar lo que llega y mide si es nuevo.",
    },
    {
        "region": "Cableado real (FlyWire)",
        "trabajo": "Lo que llega cruza las sinapsis medidas de una mosca.",
    },
    {
        "region": "Cuerno lateral",
        "trabajo": "Siente la prisa, el peligro y el ánimo; aprende cautela.",
    },
    {
        "region": "Cuerpo fungiforme",
        "trabajo": "Guarda cada conversación y la trae cuando hace falta.",
    },
    {
        "region": "Lóbulos α/β",
        "trabajo": "Convierte lo que se repite en recuerdos que duran.",
    },
    {
        "region": "Complejo central",
        "trabajo": "Sostiene el tema en curso y, si duda, toma el camino cuidadoso.",
    },
    {
        "region": "Neuronas de salida",
        "trabajo": "Eligen: reflejo, responder, reflexionar o a fondo.",
    },
    {
        "region": "Integrador de camino",
        "trabajo": "Predice cuánto tardará y se corrige con el error.",
    },
    {"region": "Dopamina", "trabajo": "Lo que usted dice después premia o castiga."},
    {
        "region": "Sueño",
        "trabajo": "Repasa, guarda lo importante y poda lo que no sirve.",
    },
]


def _column_info() -> Dict[str, Any]:
    if not _fly_on():
        return {"verificado": False}
    try:
        from openjarvis.connectome import mosca

        return mosca.describe()
    except Exception:  # noqa: BLE001
        return {"verificado": False}


def column_proof() -> Dict[str, Any]:
    """Does the fly's wiring keep like with like? Requests that mean the same
    should light up overlapping neurons, unrelated ones should not."""
    pairs_same = [
        (
            "explícame cómo funciona la inflación",
            "explícame cómo funciona la inflación en Ecuador",
        ),
        ("pon música para dormir", "pon música tranquila para dormir"),
        ("qué tiempo hará mañana en Cuenca", "qué tiempo hará el sábado en Cuenca"),
    ]
    pairs_other = [
        ("explícame cómo funciona la inflación", "pon música para dormir"),
        ("qué tiempo hará mañana en Cuenca", "diseña la arquitectura de mi app"),
        ("pon música para dormir", "revisa este código de Python"),
    ]

    def overlap(a: str, b: str) -> float:
        ca, _ = _column(kenyon_code(a))
        cb, _ = _column(kenyon_code(b))
        if not ca or not cb:
            return 0.0
        sa, sb = set(ca), set(cb)
        return len(sa & sb) / len(sa | sb)

    same = [overlap(a, b) for a, b in pairs_same]
    other = [overlap(a, b) for a, b in pairs_other]
    _slots, layers = _column(kenyon_code(pairs_same[0][0]))
    return {
        "parecidos": round(sum(same) / len(same), 3),
        "distintos": round(sum(other) / len(other), 3),
        "zonas_encendidas": layers,
    }


def _episodes(now: float) -> List[Dict[str, Any]]:
    """The mushroom body's recent engrams (the fly's memory zone)."""
    try:
        from openjarvis.connectome.brain import get_brain

        brain = get_brain()
        since = now - CONCEPT_DAYS * 86400
        return [
            e
            for e in brain.engrams.values()
            if e.get("t", 0) >= since and e.get("channel", "chat") in CHANNELS
        ]
    except Exception:  # noqa: BLE001
        return []


# -- one brain per home ------------------------------------------------------------------------
_BRAINS: Dict[str, FlyBrain] = {}
_BRAINS_LOCK = threading.Lock()


def get_brain(home: Optional[Path] = None) -> FlyBrain:
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    folder = Path(home) / "connectome" / "mosca"
    with _BRAINS_LOCK:
        if str(folder) not in _BRAINS:
            moved = _move_old(Path(home) / "connectome" / "humano", folder)
            brain = FlyBrain(folder)
            if moved:
                brain.rewire()
            _BRAINS[str(folder)] = brain
        return _BRAINS[str(folder)]


def _move_old(old: Path, new: Path) -> bool:
    """What the owner taught before the fly (the old «humano» folder) moves
    over: his taste in words and context stays, the old wiring's part goes."""
    if new.exists() or not old.is_dir():
        return False
    import shutil

    try:
        new.mkdir(parents=True, exist_ok=True)
        for name in ("sinapsis.npz", "estado.json"):
            if (old / name).is_file():
                shutil.copy2(old / name, new / name)
        return True
    except OSError:
        return False


def forget(home: Optional[Path] = None) -> None:
    """Back to a newborn fly brain: everything it learned is erased."""
    if home is None:
        from openjarvis.core.paths import get_config_dir

        home = get_config_dir()
    folder = Path(home) / "connectome" / "mosca"
    with _BRAINS_LOCK:
        _BRAINS.pop(str(folder), None)
    for name in ("sinapsis.npz", "estado.json"):
        try:
            (folder / name).unlink()
        except OSError:
            pass


def think(text: str, channel: str = "chat") -> Optional[Thought]:
    """The brain's decision for this turn (None when the mind is off)."""
    if not enabled() or not (text or "").strip():
        return None
    try:
        return get_brain().think(text, channel)
    except Exception:  # noqa: BLE001 — a turn never breaks for the brain
        return None


def workspace(text: str, channel: str = "chat") -> str:
    t = think(text, channel)
    return t.broadcast() if t is not None else ""


def outcome(text: str, answer: str, channel: str = "chat") -> None:
    if not enabled() or not (text or "").strip():
        return
    try:
        get_brain().outcome(text, answer, channel or "chat")
    except Exception:  # noqa: BLE001
        pass


# -- the proof: measured, not described --------------------------------------------------------
LESSONS: Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    # (what this owner wants, what he says while it learns, what it never saw)
    ("reflejo", ("hola sergio", "qué hora es en Madrid", "cuánto es 15 por ciento de 80"),
     ("hola, ¿qué tal?", "qué hora es en Tokio", "cuánto es 20 por ciento de 50")),
    ("reflexionar", ("explícame cómo funciona la inflación", "explícame por qué sube el dólar",
                     "explícame cómo funciona una hipoteca"),
     ("explícame cómo funciona la bolsa", "explícame por qué baja el euro")),
    ("profundo", ("arma un plan de negocio completo para mi cafetería con finanzas",
                  "diseña la arquitectura completa de mi app con pagos y usuarios"),
     ("arma un plan de negocio completo para mi tienda de ropa",
      "diseña la arquitectura completa de mi web con pagos")),
)  # fmt: skip


def _owner_says(chosen: str, wanted: str) -> str:
    a, w = STRATEGIES.index(chosen), STRATEGIES.index(wanted)
    if a < w:
        return "explícame mejor, más a fondo"
    if a > w:
        return "más corto, al grano"
    return "gracias, perfecto"


def prove(rounds: int = 4) -> Dict[str, Any]:
    """A newborn fly brain meets an owner with his own taste: it starts from
    the innate guess, is judged by what he says next, and is tested every
    round on requests it never saw. Then it sleeps and forms concepts."""
    brain = FlyBrain(None, clock=_Clock(), terry=False)

    def test() -> Dict[str, Any]:
        rows = []
        for wanted, _seen, unseen in LESSONS:
            for text in unseen:
                t = brain.think(text, "prueba")
                rows.append({"texto": text, "quiere": wanted, "elige": t.strategy})
                brain._thoughts.clear()
        ok = sum(r["elige"] == r["quiere"] for r in rows)
        return {"acierto": round(ok / len(rows), 3), "pruebas": rows}

    steps = [{"ronda": 0, **test()}]
    for r in range(1, rounds + 1):
        for wanted, seen, _unseen in LESSONS:
            for text in seen:
                t = brain.think(text, "chat")
                brain.outcome(text, "respuesta", "chat")
                brain.clock.tick(20)
                brain.think(_owner_says(t.strategy, wanted), "chat")
                brain._thoughts.clear()
                brain.clock.tick(20)
        steps.append({"ronda": r, **test()})
    episodes = [
        {"t": brain.clock() - i, "user": text, "channel": "chat"}
        for i, (_w, seen, _u) in enumerate(LESSONS * 2)
        for text in seen
    ]
    night = brain.sleep(episodes)
    return {
        "rondas": [{"ronda": s["ronda"], "acierto": s["acierto"]} for s in steps],
        "pruebas": steps[-1]["pruebas"],
        "azar": round(1 / len(STRATEGIES), 3),
        "dopamina": {
            "recompensas": brain.stats_["recompensas"],
            "castigos": brain.stats_["castigos"],
            "arrepentimientos": brain.stats_["arrepentimientos"],
        },
        "dormir": night,
        "conceptos": [c["palabra"] for c in brain.stats()["conceptos"]],
        "columna": column_proof(),
    }


class _Clock:
    def __init__(self) -> None:
        self.now = 1_700_000_000.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


__all__ = [
    "REGIONS",
    "STRATEGIES",
    "Affect",
    "FlyBrain",
    "Percept",
    "Thought",
    "column_proof",
    "forget",
    "get_brain",
    "outcome",
    "prove",
    "think",
    "workspace",
]

"""One small interface for every reasoning layer: ask the model, get text.

Each layer (reflection, tree of thoughts, voting, ...) takes an ``LLM`` so it
works the same with Gemini, Ollama, any engine Sergio found, or a scripted
function in tests. ``parse_json`` reads the JSON a model wraps in prose or
code fences.
"""

from __future__ import annotations

import inspect
import json
import re
import time
from typing import Any, Callable, Optional

from openjarvis.core.types import Message, Role


class LLM:
    """A callable model: ``llm(prompt, system=..., temperature=...) -> str``.

    *fn* receives ``(prompt, system, temperature, max_tokens)`` keyword
    arguments it understands; plain ``fn(prompt)`` functions work too.
    """

    def __init__(self, fn: Callable[..., str], name: str = "llm") -> None:
        self._fn = fn
        self.name = name
        self.calls = 0
        self._takes_options = _takes_options(fn)
        self._listeners: list[Callable[[dict], None]] = []

    def listen(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        """Call *callback* after every model call; returns an unsubscribe."""
        self._listeners.append(callback)
        return lambda: (
            self._listeners.remove(callback) if callback in self._listeners else None
        )

    def __call__(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        self.calls += 1
        started = time.monotonic()
        if self._takes_options:
            out = self._fn(
                prompt, system=system, temperature=temperature, max_tokens=max_tokens
            )
        else:
            out = self._fn(prompt)
        text = str(out or "")
        if self._listeners:
            event = {
                "stage": "call",
                "n": self.calls,
                "step": step_label(prompt, system),
                "seconds": round(time.monotonic() - started, 2),
                "preview": text[:600],
            }
            for listener in list(self._listeners):
                try:
                    listener(event)
                except Exception:  # noqa: BLE001 - a viewer must never break thinking
                    pass
        return text

    @classmethod
    def from_engine(cls, engine: Any, model: str) -> "LLM":
        """Wrap an inference engine (``engine.generate(messages, model=...)``)."""

        def ask(
            prompt: str,
            system: Optional[str] = None,
            temperature: float = 0.7,
            max_tokens: int = 2048,
        ) -> str:
            messages = []
            if system:
                messages.append(Message(role=Role.SYSTEM, content=system))
            messages.append(Message(role=Role.USER, content=prompt))
            result = engine.generate(
                messages, model=model, temperature=temperature, max_tokens=max_tokens
            )
            return str((result or {}).get("content") or "")

        return cls(ask, name=f"{getattr(engine, 'engine_id', 'engine')}:{model}")

    @classmethod
    def default(cls) -> "LLM":
        """The engine and model Sergio is configured with (raises when none)."""
        from openjarvis.core.config import load_config
        from openjarvis.engine import get_engine

        config = load_config()
        resolved = get_engine(config)
        if resolved is None:
            raise RuntimeError(
                "No inference engine available (start Ollama or set a Gemini key)."
            )
        _, engine = resolved
        model = config.intelligence.default_model
        if not model:
            models = engine.list_models() or []
            if not models:
                raise RuntimeError("The engine reports no models.")
            model = models[0]
        return cls.from_engine(engine, model)


# What each reasoning layer's prompt is doing, by a phrase only it contains.
STEP_NAMES = (
    ("You are a demanding reviewer", "Critiquing the draft"),
    ("Rewrite the ANSWER to the TASK, fixing", "Improving the draft"),
    ("against its CONSTITUTION", "Checking the principles"),
    ("no longer\nviolates these principles", "Fixing a principle"),
    ("PROPOSED ANSWER:", "Estimating confidence"),
    ("different next steps", "Exploring possible next steps"),
    ("How promising is this partial solution", "Scoring a line of reasoning"),
    ("A careful search found this line of reasoning", "Writing up the best line"),
    ("FINAL ANSWER: <the answer only", "Solving it one more independent way"),
    ("Build the causal model", "Mapping causes and effects"),
    ("Facts computed from the causal graph", "Explaining with the causal facts"),
    ("COUNTERFACTUAL CHANGE:", "Framing the what-if"),
    ("Describe the alternative world", "Describing the alternative world"),
)


def step_label(prompt: str, system: Optional[str] = None) -> str:
    """A short human label for a model call: what the layer is doing, else
    the first sentence it was given."""
    text = f"{system or ''}\n{prompt or ''}"
    for marker, name in STEP_NAMES:
        if marker.lower() in text.lower():
            return name
    for source in (system or "", prompt or ""):
        for line in source.splitlines():
            line = line.strip()
            if line:
                first = re.split(r"(?<=[.!?:])\s", line, maxsplit=1)[0]
                return first[:110] + ("…" if len(first) > 110 else "")
    return "model call"


def _takes_options(fn: Callable[..., Any]) -> bool:
    """Whether *fn* accepts system/temperature/max_tokens keywords."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.kind is p.VAR_KEYWORD or p.name == "system" for p in params)


def as_llm(llm: "LLM | Callable[..., str] | None") -> LLM:
    """Accept an LLM, a plain function, or None (= Sergio's default model)."""
    if llm is None:
        return LLM.default()
    if isinstance(llm, LLM):
        return llm
    return LLM(llm)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def parse_json(text: str) -> Any:
    """The first JSON object or array in *text* (fenced or not), else None."""
    if not text:
        return None
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for chunk in candidates:
        chunk = chunk.strip()
        try:
            return json.loads(chunk)
        except ValueError:
            pass
        for opener, closer in (("{", "}"), ("[", "]")):
            start = chunk.find(opener)
            while start != -1:
                depth = 0
                in_str = False
                escape = False
                for i in range(start, len(chunk)):
                    ch = chunk[i]
                    if in_str:
                        if escape:
                            escape = False
                        elif ch == "\\":
                            escape = True
                        elif ch == '"':
                            in_str = False
                        continue
                    if ch == '"':
                        in_str = True
                    elif ch == opener:
                        depth += 1
                    elif ch == closer:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(chunk[start : i + 1])
                            except ValueError:
                                break
                start = chunk.find(opener, start + 1)
    return None


def clamp(
    value: Any, low: float = 0.0, high: float = 10.0, default: float = 0.0
) -> float:
    """A number from model output, kept inside [low, high]."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
        if not match:
            return default
        number = float(match.group())
    return max(low, min(high, number))


__all__ = ["LLM", "as_llm", "clamp", "parse_json"]

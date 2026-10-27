"""One way for Creator to ask Gemini: model fallbacks, quota pauses, checks.

Every answer can be validated by the caller (``check``): an answer that fails
it counts as a failure of that model and the next one is tried, so a broken
JSON layout or script never reaches the user as if it were fine.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

MODELS = (
    "gemini-3.8-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
)


# Sergio is every model, not only Gemini (owner, 27 Oct 2026: «Sergio no es
# solo Gemini, Sergio es todos los modelos de IA»): with a key of another
# company, its model writes too — first when the owner chose it
# (``SERGIO_VIDEO_MODELO``, any id: «claude-sonnet-5-5», «openrouter/auto»),
# otherwise when Gemini cannot (no key, no quota, busy).
OTHER_MODELS = (
    ("ANTHROPIC_API_KEY", "claude-sonnet-5-5"),
    ("OPENAI_API_KEY", "gpt-5.6-terra"),
    ("DEEPSEEK_API_KEY", "deepseek-v4-pro"),
    ("OPENROUTER_API_KEY", "openrouter/auto"),
)


def other_models() -> list[str]:
    """Models of the other companies this computer has a key for, the
    owner's choice first."""
    out: list[str] = []
    chosen = os.environ.get("SERGIO_VIDEO_MODELO", "").strip()
    if chosen and not chosen.startswith("gemini"):
        out.append(chosen)
    for env, model in OTHER_MODELS:
        if os.environ.get(env, "").strip() and model not in out:
            out.append(model)
    return out


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return text.strip()


def ask_others(
    prompt: str,
    *,
    json_mode: bool = False,
    max_tokens: int = 8192,
    check: Callable[[str], Any] | None = None,
    models: list[str] | None = None,
    engine: Any = None,
) -> str:
    """The same question to the other companies' models, in order."""
    from openjarvis.core.types import Message, Role

    errors: list[str] = []
    todo = models if models is not None else other_models()
    if not todo:
        raise CreatorError("no hay clave de otra empresa de IA")
    if engine is None:
        from openjarvis.engine.cloud import CloudEngine

        engine = CloudEngine()
    text_prompt = prompt + (
        "\n\nAnswer ONLY with valid JSON, no prose." if json_mode else ""
    )
    for model in todo:
        try:
            out = engine.generate(
                [Message(role=Role.USER, content=text_prompt)],
                model=model,
                temperature=0.4,
                max_tokens=min(max_tokens, 32000),
            )
            text = str((out or {}).get("content") or "")
            if json_mode:
                text = _clean_json(text)
            if not text.strip():
                raise ValueError("respuesta vacía")
            if check is not None:
                check(text)
            return text
        except Exception as exc:  # noqa: BLE001 — the next company
            errors.append(f"{model}: {str(exc)[:160]}")
    raise CreatorError("Ningún modelo pudo completarlo: " + " | ".join(errors[-4:]))


class CreatorError(RuntimeError):
    """A Creator step failed in a way the user should read."""


def gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if not key:
        raise CreatorError(
            "Falta la clave de Gemini: añádala en Ajustes o en ~/.openjarvis/sergio.env."
        )
    return key


def ask(
    prompt: str | list[Any],
    *,
    json_mode: bool = False,
    effort: str = "low",
    max_tokens: int = 8192,
    check: Callable[[str], Any] | None = None,
    models: tuple[str, ...] = MODELS,
    client: Any = None,
    hedge_after: float = 15.0,
    timeout: float = 240.0,
) -> str:
    """The answer that passed *check*: Gemini's, or another company's model
    when the owner chose one or Gemini cannot (raises CreatorError
    otherwise). Pictures in *prompt* (a list) go only to Gemini."""
    text_only = isinstance(prompt, str)
    chosen = os.environ.get("SERGIO_VIDEO_MODELO", "").strip()
    has_gemini = bool(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or client
    )
    if (
        text_only
        and other_models()
        and (not has_gemini or (chosen and not chosen.startswith("gemini")))
    ):
        try:
            return ask_others(
                prompt, json_mode=json_mode, max_tokens=max_tokens, check=check
            )
        except CreatorError:
            if not has_gemini:
                raise
    try:
        return _ask_gemini(prompt, json_mode=json_mode, effort=effort, max_tokens=max_tokens,
                           check=check, models=models, client=client, hedge_after=hedge_after,
                           timeout=timeout)  # fmt: skip
    except CreatorError as exc:
        if text_only and other_models():
            try:
                return ask_others(
                    prompt, json_mode=json_mode, max_tokens=max_tokens, check=check
                )
            except CreatorError as other:
                raise CreatorError(f"{exc} · {other}") from other
        raise


def _ask_gemini(
    prompt: str | list[Any],
    *,
    json_mode: bool,
    effort: str,
    max_tokens: int,
    check: Callable[[str], Any] | None,
    models: tuple[str, ...],
    client: Any,
    hedge_after: float,
    timeout: float,
) -> str:
    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs
    from openjarvis.engine.google_client import SwitchingClient, short_wait
    from openjarvis.engine.hedge import HedgeError, first_valid

    client = client or SwitchingClient(gemini_key())
    contents = prompt if isinstance(prompt, list) else [prompt]

    def call(model: str) -> Callable[[], str]:
        def run() -> str:
            config = google_config_kwargs(model, 0.4, max_tokens, effort)
            if json_mode:
                config["response_mime_type"] = "application/json"
            resp = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(**config),
            )
            text = str(resp.text or "")
            if not text.strip():
                raise ValueError("respuesta vacía")
            return text

        return run

    errors: list[str] = []
    for attempt in range(2):
        # Hedged: a model that is slow because Google is busy gets company
        # after hedge_after seconds; the first answer that passes wins.
        try:
            _, text = first_valid(
                [call(m) for m in models],
                names=models,
                check=check,
                hedge_after=hedge_after,
                timeout=timeout,
            )
            return text
        except HedgeError as exc:
            errors.extend(exc.errors)
            if exc.timed_out:
                break
        wait = short_wait(errors) if attempt == 0 else 0.0
        if not wait:
            break
        time.sleep(min(wait, 75.0))  # a short quota pause, then one more round
    raise CreatorError("Gemini no pudo completarlo: " + " | ".join(errors[-4:]))


__all__ = [
    "CreatorError",
    "MODELS",
    "OTHER_MODELS",
    "ask",
    "ask_others",
    "gemini_key",
    "other_models",
]

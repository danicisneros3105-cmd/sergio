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
) -> str:
    """Gemini's answer that passed *check* (raises CreatorError otherwise)."""
    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs
    from openjarvis.engine.google_client import SwitchingClient, short_wait

    client = client or SwitchingClient(gemini_key())
    contents = prompt if isinstance(prompt, list) else [prompt]
    errors: list[str] = []
    for attempt in range(2):
        for model in models:
            try:
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
                if check is not None:
                    check(text)
                return text
            except Exception as exc:  # noqa: BLE001 — try the next model
                errors.append(f"{model}: {str(exc)[:120]}")
        wait = short_wait(errors) if attempt == 0 else 0.0
        if not wait:
            break
        time.sleep(min(wait, 75.0))  # a short quota pause, then one more round
    raise CreatorError("Gemini no pudo completarlo: " + " | ".join(errors[-4:]))


__all__ = ["CreatorError", "MODELS", "ask", "gemini_key"]

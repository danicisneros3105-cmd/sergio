"""Ask a vision model about an image (the webcam): Kimi, then Gemini, then Ollama.

Used by ``camera_look`` so Sergio can answer "¿qué tengo en la mano?", read a
gesture or an expression, or describe what the camera sees.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx

PROMPT = (
    "Eres los ojos de Sergio, un asistente. Mira la foto de la cámara del "
    "usuario y responde en español, breve y concreto, a esta pregunta: {question}\n"
    "Si hay un objeto en la mano, nómbralo. Si hay un gesto (pulgar arriba, "
    "señalar, mano abierta, contar con los dedos) o una expresión (sonrisa, "
    "sorpresa, cansancio), dilo. No inventes lo que no se ve."
)
KIMI_VISION_MODELS = ("kimi-k2.6", "kimi-k2.5", "moonshot-v1-8k-vision-preview")
GEMINI_VISION_MODELS = ("gemini-2.5-flash", "gemini-3-flash-preview")


def _kimi(
    jpeg: bytes, prompt: str, http: httpx.Client, mime: str = "image/jpeg"
) -> str:
    key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY")
    if not key:
        raise RuntimeError("no Kimi key")
    base = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
    image = f"data:{mime};base64," + base64.b64encode(jpeg).decode("ascii")
    wanted = os.environ.get("SERGIO_VISION_MODEL", "")
    models = ([wanted] if wanted.startswith(("kimi", "moonshot")) else []) + list(
        KIMI_VISION_MODELS
    )
    last: Exception | None = None
    for model in models:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": 700,
        }
        if model.startswith("kimi-k2."):
            body["thinking"] = {"type": "disabled"}
        try:
            resp = http.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=body,
                timeout=90,
            )
            resp.raise_for_status()
            return str(resp.json()["choices"][0]["message"]["content"]).strip()
        except Exception as exc:  # noqa: BLE001 — try the next model
            last = exc
    raise RuntimeError(f"Kimi vision failed: {last}")


_GEMINI: Any = None  # remembers which Google service the key works with


def _gemini(jpeg: bytes, prompt: str, mime: str = "image/jpeg") -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("no Gemini key")
    from google.genai import types

    from openjarvis.engine.google_client import SwitchingClient

    global _GEMINI
    if _GEMINI is None or _GEMINI.key != key:
        _GEMINI = SwitchingClient(key)
    client = _GEMINI
    last: Exception | None = None
    for model in GEMINI_VISION_MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=jpeg, mime_type=mime),
                    prompt,
                ],
            )
            return str(resp.text or "").strip()
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"Gemini vision failed: {last}")


def _ollama(jpeg: bytes, prompt: str, http: httpx.Client) -> str:
    model = os.environ.get("SERGIO_VISION_MODEL", "")
    if not model or model.startswith(("kimi", "moonshot", "gemini")):
        raise RuntimeError("no local vision model")
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if "://" not in host:
        host = "http://" + host
    resp = http.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(jpeg).decode("ascii")],
                }
            ],
        },
        timeout=180,
    )
    resp.raise_for_status()
    return str(resp.json()["message"]["content"]).strip()


def ask_image(
    image: bytes,
    prompt: str,
    http: httpx.Client | None = None,
    mime: str = "image/jpeg",
) -> str:
    """Send *prompt* with the image to the first vision model that works."""
    http = http or httpx.Client()
    errors = []
    for name, call in (
        ("Kimi", lambda: _kimi(image, prompt, http, mime)),
        ("Gemini", lambda: _gemini(image, prompt, mime)),
        ("Ollama", lambda: _ollama(image, prompt, http)),
    ):
        try:
            answer = call()
            if answer:
                return answer
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    raise RuntimeError("Ningún modelo con visión respondió. " + " | ".join(errors))


def ask_vision(jpeg: bytes, question: str, http: httpx.Client | None = None) -> str:
    """Answer *question* about a webcam photo."""
    return ask_image(jpeg, PROMPT.format(question=question or "¿Qué ves?"), http)


__all__ = ["ask_image", "ask_vision"]

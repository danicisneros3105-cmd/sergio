"""Ask a vision model about an image (the webcam): Kimi, then Gemini, then Ollama.

Used by ``camera_look`` so Sergio can answer "¿qué tengo en la mano?", read a
gesture or an expression, or describe what the camera sees.
"""

from __future__ import annotations

import base64
import os
from contextlib import nullcontext
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
# Every Gemini Flash has its own free daily quota: when one is spent, the
# next one sees for Sergio.
GEMINI_VISION_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-2.5-flash",
)
# For automatic looks in the background (naming objects in the camera):
# Flash-Lite answers fast and has the largest free daily quota.
GEMINI_LITE_VISION_MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
)


def _frames(images: bytes | list[bytes]) -> list[bytes]:
    return [images] if isinstance(images, bytes) else images


def _image_parts(images: bytes | list[bytes], mime: str) -> list[dict]:
    return [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}",
            },
        }
        for image in _frames(images)
    ]


def _kimi(
    jpeg: bytes | list[bytes],
    prompt: str,
    http: httpx.Client,
    mime: str = "image/jpeg",
    max_tokens: int = 700,
) -> str:
    key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY")
    if not key:
        raise RuntimeError("no Kimi key")
    base = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
    parts = _image_parts(jpeg, mime)
    wanted = os.environ.get("SERGIO_VISION_MODEL", "")
    models = ([wanted] if wanted.startswith(("kimi", "moonshot")) else []) + list(
        KIMI_VISION_MODELS
    )
    last: Exception | None = None
    for model in dict.fromkeys(models):
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        *parts,
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": max_tokens,
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
            answer = str(resp.json()["choices"][0]["message"]["content"] or "").strip()
            if answer:
                return answer
        except Exception as exc:  # noqa: BLE001 — try the next model
            last = exc
    raise RuntimeError(f"Kimi vision failed: {last}")


# Any OpenAI-compatible service with vision (owner, 1 Nov 2026: «todo lo que
# sea solo para Gemini hazlo universal»): with only an OpenRouter or OpenAI
# key, the screen help, the operator and the camera still see.
OPEN_VISION = (
    ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
     ("google/gemini-2.5-flash", "openai/gpt-4o-mini", "anthropic/claude-sonnet-4")),
    ("OPENAI_API_KEY", "https://api.openai.com/v1", ("gpt-4o-mini", "gpt-4o")),
)  # fmt: skip


def _open_vision(
    jpeg: bytes | list[bytes],
    prompt: str,
    http: httpx.Client,
    mime: str = "image/jpeg",
    max_tokens: int = 700,
) -> str:
    parts = _image_parts(jpeg, mime)
    last: Exception | None = None
    tried = False
    wanted = os.environ.get("SERGIO_VISION_MODEL", "").strip()
    prefer_openai = wanted.startswith(("gpt-", "o1", "o3", "o4"))
    providers = reversed(OPEN_VISION) if prefer_openai else OPEN_VISION
    for env, base, models in providers:
        key = os.environ.get(env, "").strip()
        if not key:
            continue
        explicit = (prefer_openai and env == "OPENAI_API_KEY") or (
            "/" in wanted and env == "OPENROUTER_API_KEY"
        )
        for model in dict.fromkeys((wanted, *models) if explicit else models):
            tried = True
            try:
                resp = http.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    *parts,
                                    {"type": "text", "text": prompt},
                                ],
                            }
                        ],
                        "max_tokens": max_tokens,
                    },  # fmt: skip
                    timeout=90,
                )
                resp.raise_for_status()
                answer = str(
                    resp.json()["choices"][0]["message"]["content"] or ""
                ).strip()
                if answer:
                    return answer
            except Exception as exc:  # noqa: BLE001 — the next model
                last = exc
    if not tried:
        raise RuntimeError("no OpenRouter/OpenAI key")
    raise RuntimeError(f"vision failed: {last}")


_GEMINI: Any = None  # remembers which Google service the key works with


def _gemini(
    jpeg: bytes | list[bytes],
    prompt: str,
    mime: str = "image/jpeg",
    models: tuple[str, ...] = GEMINI_VISION_MODELS,
    max_tokens: int = 1024,
) -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("no Gemini key")
    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs
    from openjarvis.engine.google_client import SwitchingClient

    global _GEMINI
    if _GEMINI is None or _GEMINI.key != key:
        _GEMINI = SwitchingClient(key)
    client = _GEMINI
    last: Exception | None = None
    wanted = os.environ.get("SERGIO_VISION_MODEL", "")
    ordered = (wanted, *models) if wanted.startswith("gemini") else models
    for model in dict.fromkeys(ordered):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[
                    *(
                        types.Part.from_bytes(data=image, mime_type=mime)
                        for image in _frames(jpeg)
                    ),
                    prompt,
                ],
                # Seeing should feel instant: think a little, not a lot.
                config=types.GenerateContentConfig(
                    **google_config_kwargs(model, 0.4, max_tokens, "low")
                ),
            )
            answer = str(resp.text or "").strip()
            if answer:
                return answer
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"Gemini vision failed: {last}")


def _ollama(jpeg: bytes | list[bytes], prompt: str, http: httpx.Client) -> str:
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
                    "images": [
                        base64.b64encode(image).decode("ascii")
                        for image in _frames(jpeg)
                    ],
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
    lite: bool = False,
) -> str:
    """Send *prompt* with the image to the first vision model that works.

    *lite*: background looks go to Gemini Flash-Lite first (fast, big quota).
    """
    http = http or httpx.Client()
    errors = []
    models = (
        GEMINI_LITE_VISION_MODELS + GEMINI_VISION_MODELS
        if lite
        else GEMINI_VISION_MODELS
    )
    for name, call in (
        ("Kimi", lambda: _kimi(image, prompt, http, mime)),
        ("Gemini", lambda: _gemini(image, prompt, mime, models)),
        ("OpenRouter/OpenAI", lambda: _open_vision(image, prompt, http, mime)),
        ("Ollama", lambda: _ollama(image, prompt, http)),
    ):
        try:
            answer = call()
            if answer:
                return answer
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    raise RuntimeError("Ningún modelo con visión respondió. " + " | ".join(errors))


def ask_images(
    images: list[bytes],
    prompt: str,
    http: httpx.Client | None = None,
) -> str:
    """Plan with all frames. An explicitly local choice never uploads them."""
    if not images or not all(images):
        raise ValueError("Se necesitan imágenes válidas.")
    model = os.environ.get("SERGIO_VISION_MODEL", "").strip()
    with nullcontext(http) if http is not None else httpx.Client() as client:
        calls = {
            "Kimi": lambda: _kimi(images, prompt, client, max_tokens=8000),
            "Gemini": lambda: _gemini(images, prompt, max_tokens=8000),
            "OpenRouter/OpenAI": lambda: _open_vision(
                images, prompt, client, max_tokens=8000
            ),
            "Ollama": lambda: _ollama(images, prompt, client),
        }
        cloud = ["Kimi", "Gemini", "OpenRouter/OpenAI"]
        if model.startswith("gemini"):
            order = ["Gemini", "Kimi", "OpenRouter/OpenAI"]
        elif model.startswith(("kimi", "moonshot")):
            order = cloud
        elif model.startswith(("gpt-", "o1", "o3", "o4")) or (
            "/" in model and not model.startswith("hf.co/") and ":" not in model
        ):
            order = ["OpenRouter/OpenAI", "Kimi", "Gemini"]
        elif model:
            order = ["Ollama"]
        else:
            order = cloud
        for name in order:
            try:
                answer = calls[name]()
                if answer:
                    return answer
            except Exception:  # noqa: BLE001 — do not expose provider payloads or secrets
                continue
    raise RuntimeError("No respondió ningún modelo de visión: " + ", ".join(order))


def ask_vision(jpeg: bytes, question: str, http: httpx.Client | None = None) -> str:
    """Answer *question* about a webcam photo."""
    return ask_image(jpeg, PROMPT.format(question=question or "¿Qué ves?"), http)


__all__ = ["ask_image", "ask_images", "ask_vision"]

"""One way to ask Gemini for the coach: JSON answers, optional web research,
optional media (a practice video, a screenshot), several models in turn."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

KNOWLEDGE = Path(__file__).parent / "knowledge"
MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
)
DEEP_MODELS = ("gemini-3.1-pro-preview",) + MODELS


@lru_cache(maxsize=None)
def knowledge(*names: str) -> str:
    """The expert notes for these topics (psicologia, salud, idiomas...)."""
    parts = []
    for name in names:
        path = KNOWLEDGE / f"{name}.md"
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


def parse_json(text: str) -> Any:
    """Gemini's JSON, also when it comes inside ``` fences or with prose."""
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = raw.find(opener), raw.rfind(closer)
        if 0 <= start < end:
            try:
                return json.loads(raw[start : end + 1])
            except ValueError:
                continue
    raise ValueError("La respuesta no era JSON")


def _client() -> Any:
    from openjarvis.engine.google_client import SwitchingClient

    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY (sergio nube configurar --gemini …)")
    return SwitchingClient(key)


def ask(
    prompt: str,
    *,
    system: str = "",
    media: list[tuple[bytes, str]] | None = None,
    search: bool = False,
    deep: bool = False,
    check: Callable[[Any], Any] | None = None,
    client: Any = None,
    max_tokens: int = 12000,
) -> Any:
    """Ask for a JSON answer; returns it parsed (``check`` may validate it).

    *search*: ground the answer on Google Search (research); *media*: bytes
    with their mime types (video, image, audio) to look at first.
    """
    from google.genai import types

    from openjarvis.engine.cloud import google_config_kwargs

    client = client or _client()
    contents: list[Any] = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in media or []]
    contents.append(prompt)
    errors = []
    for model in DEEP_MODELS if deep else MODELS:
        kwargs = dict(google_config_kwargs(model, 0.5, max_tokens, "medium" if deep else "low"))
        if system:
            kwargs["system_instruction"] = system
        if search:  # grounding and a JSON mime type can't go together
            kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        else:
            kwargs["response_mime_type"] = "application/json"
        try:
            resp = client.models.generate_content(
                model=model, contents=contents, config=types.GenerateContentConfig(**kwargs)
            )
            data = parse_json(str(resp.text or ""))
            if search:
                data = _with_sources(data, resp)
            return check(data) if check else data
        except Exception as exc:  # noqa: BLE001 — the next model
            errors.append(f"{model}: {str(exc)[:120]}")
    raise RuntimeError("El coach no pudo responder: " + " | ".join(errors[-3:]))


def _with_sources(data: Any, resp: Any) -> Any:
    """Add the web pages Google Search used (title + link) to the answer."""
    if not isinstance(data, dict):
        return data
    found = []
    try:
        for cand in resp.candidates or []:
            meta = getattr(cand, "grounding_metadata", None)
            for chunk in getattr(meta, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                if web is not None and getattr(web, "uri", None):
                    found.append({"titulo": str(getattr(web, "title", "") or ""), "url": str(web.uri)})
    except Exception:  # noqa: BLE001 — sources are a bonus
        pass
    if found and not data.get("fuentes"):
        seen, unique = set(), []
        for item in found:
            if item["url"] not in seen:
                seen.add(item["url"])
                unique.append(item)
        data["fuentes"] = unique[:12]
    return data


__all__ = ["ask", "knowledge", "parse_json"]

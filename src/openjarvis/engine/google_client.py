"""A Google GenAI client that finds the right service for the key by itself.

Google keys work against one of two services:

* the Gemini API (Google AI Studio keys; classic ``AIza…`` and newer ``AQ.…``),
* Vertex AI / Agent Platform "express mode" (``AQ.…`` keys of a Cloud project
  where that API is enabled).

The key alone does not say which one, so this client tries the Gemini API
first, then Vertex AI, and keeps using whichever answered.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Iterator

# Errors that mean "wrong service for this key", not "bad request".
_WRONG_SERVICE = (
    "PERMISSION_DENIED",
    "API_KEY_INVALID",
    "API key not valid",
    "UNAUTHENTICATED",
    "has not been used in project",
    "is disabled",
    "API_KEY_SERVICE_BLOCKED",
    "not supported for this API",
    "express mode",
)


def wrong_service(exc: Exception) -> bool:
    text = str(exc)
    return any(marker in text for marker in _WRONG_SERVICE)


def _default_factory(key: str, vertex: bool) -> Any:
    from google import genai

    return (
        genai.Client(vertexai=True, api_key=key)
        if vertex
        else genai.Client(api_key=key)
    )


# Models whose quota ran out, until when (monotonic). Free keys get a few
# requests a day for some models: asking again only adds seconds of waiting
# before the fallback, on every sentence Sergio says.
_EXHAUSTED: dict[str, float] = {}


class QuotaExhausted(RuntimeError):
    """This model's quota is used up for now (remembered, not asked again)."""


def _retry_seconds(text: str) -> float:
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", text)
    if m:
        h, mins, secs = (float(g) if g else 0.0 for g in m.groups())
        return h * 3600 + mins * 60 + secs
    m = re.search(r"retryDelay'?\"?:\s*'?\"?(\d+)s", text)
    if m:
        return float(m.group(1))
    return 3600.0 if "PerDay" in text else 60.0


def note_quota(model: str, exc: Exception, clock: Callable[[], float] = time.monotonic) -> None:
    text = str(exc)
    if model and ("RESOURCE_EXHAUSTED" in text or "exceeded your current quota" in text):
        _EXHAUSTED[model] = clock() + min(_retry_seconds(text), 6 * 3600)


def check_quota(model: str, clock: Callable[[], float] = time.monotonic) -> None:
    until = _EXHAUSTED.get(model or "", 0.0)
    if until > clock():
        mins = max(1, int((until - clock()) // 60))
        raise QuotaExhausted(
            f"429 RESOURCE_EXHAUSTED: {model} sin cuota por ahora (vuelve en ~{mins} min)"
        )


class _Models:
    def __init__(self, owner: "SwitchingClient") -> None:
        self._owner = owner

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        model = str(kwargs.get("model") or (args[0] if args else ""))
        check_quota(model)
        try:
            return self._owner._call(
                lambda client: client.models.generate_content(*args, **kwargs)
            )
        except Exception as exc:
            note_quota(model, exc)
            raise

    def generate_content_stream(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        def start(client: Any) -> Iterator[Any]:
            stream = iter(client.models.generate_content_stream(*args, **kwargs))
            first = next(stream, None)  # auth errors surface on the first chunk

            def chain() -> Iterator[Any]:
                if first is not None:
                    yield first
                yield from stream

            return chain()

        model = str(kwargs.get("model") or (args[0] if args else ""))
        check_quota(model)
        try:
            return self._owner._call(start)
        except Exception as exc:
            note_quota(model, exc)
            raise


class SwitchingClient:
    """Drop-in for ``genai.Client`` (only ``.models`` is used by Sergio)."""

    def __init__(self, key: str, factory: Callable[[str, bool], Any] | None = None):
        self.key = key
        self._factory = factory or _default_factory
        self._modes = [False, True]  # Gemini API first, then Vertex AI
        self._clients: dict[bool, Any] = {}
        self.models = _Models(self)

    @property
    def vertex(self) -> bool:
        return self._modes[0]

    def _client(self, vertex: bool) -> Any:
        if vertex not in self._clients:
            self._clients[vertex] = self._factory(self.key, vertex)
        return self._clients[vertex]

    def _call(self, fn: Callable[[Any], Any]) -> Any:
        errors: list[str] = []
        for vertex in list(self._modes):
            try:
                result = fn(self._client(vertex))
            except Exception as exc:  # noqa: BLE001
                if not wrong_service(exc):
                    raise
                errors.append(f"{'Vertex AI' if vertex else 'Gemini API'}: {exc}")
                continue
            if self._modes[0] != vertex:  # remember the service that works
                self._modes.remove(vertex)
                self._modes.insert(0, vertex)
            return result
        raise RuntimeError(
            "Google rechazó la clave en sus dos servicios. Crea una clave nueva "
            "en https://aistudio.google.com/apikey . Detalle: " + " | ".join(errors)
        )


__all__ = ["QuotaExhausted", "SwitchingClient", "check_quota", "note_quota", "wrong_service"]

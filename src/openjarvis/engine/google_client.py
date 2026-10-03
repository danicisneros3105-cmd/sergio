"""A Google GenAI client that finds the right service for the key by itself.

Google keys work against one of two services:

* the Gemini API (Google AI Studio keys; classic ``AIza…`` and newer ``AQ.…``),
* Vertex AI / Agent Platform "express mode" (``AQ.…`` keys of a Cloud project
  where that API is enabled).

The key alone does not say which one, so this client tries the Gemini API
first, then Vertex AI, and keeps using whichever answered.
"""

from __future__ import annotations

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


class _Models:
    def __init__(self, owner: "SwitchingClient") -> None:
        self._owner = owner

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        return self._owner._call(
            lambda client: client.models.generate_content(*args, **kwargs)
        )

    def generate_content_stream(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        def start(client: Any) -> Iterator[Any]:
            stream = iter(client.models.generate_content_stream(*args, **kwargs))
            first = next(stream, None)  # auth errors surface on the first chunk

            def chain() -> Iterator[Any]:
                if first is not None:
                    yield first
                yield from stream

            return chain()

        return self._owner._call(start)


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


__all__ = ["SwitchingClient", "wrong_service"]

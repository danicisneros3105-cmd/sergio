"""OpenAI-compatible embeddings: ``POST /v1/embeddings``.

Any OpenAI client can point at Sergio (``base_url=http://localhost:8000/v1``)
and get vectors without a cloud account. Three providers:

* **ollama** — any embedding model pulled in Ollama (``nomic-embed-text``,
  ``mxbai-embed-large``, ``bge-m3``, ``embeddinggemma`` …); local and private.
* **gemini** — ``gemini-embedding-001`` when ``GEMINI_API_KEY`` is set;
  multilingual, best quality. Accepts ``input_type`` (query/document).
* **local** — ``sergio-local``: hashed words and word pairs, no network,
  no download, always available (keyword-level similarity only).

``model: "auto"`` (the default) picks Ollama, then Gemini, then local, and
the response says which one answered. ``dimensions`` shortens vectors
(Matryoshka-style truncation, re-normalised) and ``encoding_format`` may be
``float`` or ``base64`` (packed float32, like OpenAI).
"""

from __future__ import annotations

import base64
import math
import os
import struct
import time
from typing import Any, Callable, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["embeddings"])

MAX_INPUTS = 2048
MAX_CHARS = 32_000
LOCAL_MODELS = ("sergio-local", "local-hash")
GEMINI_MODELS = ("gemini-embedding-001", "text-embedding-004")
OLLAMA_EMBED_HINTS = (
    "embed",
    "bge",
    "minilm",
    "e5",
    "gte",
    "arctic",
    "nomic",
    "mxbai",
    "paraphrase",
)
_TAGS_CACHE: Dict[str, Any] = {"at": 0.0, "models": []}


class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: str = "auto"
    encoding_format: str = "float"
    dimensions: Optional[int] = None
    input_type: Optional[str] = None  # "query" or "document" (Gemini)
    user: Optional[str] = None


# -- providers -----------------------------------------------------------------


def _unit(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _ollama_base() -> str:
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        try:
            from openjarvis.core.config import load_config

            host = load_config().engine.ollama.host or ""
        except Exception:  # noqa: BLE001 - config is optional here
            host = ""
    host = host or "http://localhost:11434"
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


def ollama_embedding_models(timeout: float = 2.0) -> List[str]:
    """Embedding models pulled in Ollama (cached 30 s); [] when Ollama is off."""
    if time.monotonic() - _TAGS_CACHE["at"] < 30:
        return list(_TAGS_CACHE["models"])
    models: List[str] = []
    try:
        import httpx

        resp = httpx.get(f"{_ollama_base()}/api/tags", timeout=timeout, trust_env=False)
        resp.raise_for_status()
        for item in resp.json().get("models", []):
            name = str(item.get("name") or item.get("model") or "")
            if any(hint in name.lower() for hint in OLLAMA_EMBED_HINTS):
                models.append(name)
    except Exception:  # noqa: BLE001 - Ollama off or unreachable
        models = []
    _TAGS_CACHE.update(at=time.monotonic(), models=models)
    return list(models)


def embed_ollama(texts: List[str], model: str) -> List[List[float]]:
    import httpx

    resp = httpx.post(
        f"{_ollama_base()}/api/embed",
        json={"model": model, "input": texts},
        timeout=120,
        trust_env=False,
    )
    if resp.status_code == 404:
        raise LookupError(
            f"Ollama does not have the model {model!r}. Pull it with: ollama pull {model}"
        )
    resp.raise_for_status()
    vectors = resp.json().get("embeddings") or []
    if len(vectors) != len(texts):
        raise RuntimeError("Ollama returned a different number of vectors")
    return [_unit([float(v) for v in vec]) for vec in vectors]


def _gemini_key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def embed_gemini(
    texts: List[str],
    model: str,
    dims: Optional[int],
    input_type: Optional[str],
) -> List[List[float]]:
    from google import genai

    task = (
        "RETRIEVAL_QUERY"
        if (input_type or "").lower() == "query"
        else "RETRIEVAL_DOCUMENT"
    )
    client = genai.Client(api_key=_gemini_key())
    config: Dict[str, Any] = {"task_type": task}
    if dims:
        config["output_dimensionality"] = dims
    resp = client.models.embed_content(model=model, contents=texts, config=config)
    return [_unit(list(e.values)) for e in resp.embeddings]


def embed_local(texts: List[str], dims: Optional[int]) -> List[List[float]]:
    from openjarvis.evolution.memory import DIMS, hash_embed

    return [hash_embed(t, dims or DIMS) for t in texts]


def pick_provider(model: str) -> tuple[str, str]:
    """``(provider, concrete model)`` for a requested model name."""
    wanted = (model or "auto").strip()
    low = wanted.lower()
    if low in LOCAL_MODELS:
        return "local", "sergio-local"
    if low in GEMINI_MODELS or low.startswith("gemini-embedding"):
        if not _gemini_key():
            raise LookupError(
                "Gemini embeddings need GEMINI_API_KEY (sergio nube configurar --gemini TU_CLAVE)"
            )
        return "gemini", wanted
    if low in ("auto", "default", ""):
        local = ollama_embedding_models()
        if local:
            preferred = [m for m in local if m.split(":")[0] == "nomic-embed-text"]
            return "ollama", (preferred or local)[0]
        if _gemini_key():
            return "gemini", GEMINI_MODELS[0]
        return "local", "sergio-local"
    return "ollama", wanted


def embed_texts(
    texts: List[str],
    model: str = "auto",
    dimensions: Optional[int] = None,
    input_type: Optional[str] = None,
) -> tuple[str, List[List[float]]]:
    """Embed *texts*; returns the model that answered and unit vectors."""
    provider, name = pick_provider(model)
    runners: Dict[str, Callable[[], List[List[float]]]] = {
        "local": lambda: embed_local(texts, dimensions),
        "gemini": lambda: embed_gemini(texts, name, dimensions, input_type),
        "ollama": lambda: embed_ollama(texts, name),
    }
    vectors = runners[provider]()
    if dimensions and vectors and len(vectors[0]) > dimensions:
        vectors = [_unit(v[:dimensions]) for v in vectors]
    return name, vectors


# -- route ---------------------------------------------------------------------


def _encode(vec: List[float], fmt: str) -> Union[List[float], str]:
    if fmt == "base64":
        return base64.b64encode(struct.pack(f"<{len(vec)}f", *vec)).decode("ascii")
    return vec


@router.post("/v1/embeddings")
async def create_embeddings(req: EmbeddingRequest) -> Dict[str, Any]:
    import asyncio

    texts = [req.input] if isinstance(req.input, str) else list(req.input)
    if not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
        raise HTTPException(
            400, "input must be a non-empty string or list of non-empty strings"
        )
    if len(texts) > MAX_INPUTS:
        raise HTTPException(400, f"at most {MAX_INPUTS} inputs per request")
    if any(len(t) > MAX_CHARS for t in texts):
        raise HTTPException(400, f"each input must be at most {MAX_CHARS} characters")
    if req.encoding_format not in ("float", "base64"):
        raise HTTPException(400, "encoding_format must be 'float' or 'base64'")
    if req.dimensions is not None and not 8 <= req.dimensions <= 8192:
        raise HTTPException(400, "dimensions must be between 8 and 8192")
    try:
        model, vectors = await asyncio.to_thread(
            embed_texts, texts, req.model, req.dimensions, req.input_type
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(503, f"provider library missing: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - provider down or refused
        raise HTTPException(502, f"embedding provider failed: {exc}") from exc
    tokens = sum(max(1, len(t) // 4) for t in texts)
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": i,
                "embedding": _encode(v, req.encoding_format),
            }
            for i, v in enumerate(vectors)
        ],
        "model": model,
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }


@router.get("/v1/embeddings/models")
async def embedding_models() -> Dict[str, Any]:
    import asyncio

    ollama = await asyncio.to_thread(ollama_embedding_models)
    models = [{"id": "sergio-local", "provider": "local", "available": True}]
    models += [{"id": m, "provider": "ollama", "available": True} for m in ollama]
    models += [
        {"id": m, "provider": "gemini", "available": bool(_gemini_key())}
        for m in GEMINI_MODELS
    ]
    return {"object": "list", "data": models, "auto": pick_provider("auto")[1]}


__all__ = ["embed_texts", "pick_provider", "router"]

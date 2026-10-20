"""Usage and models, for every provider: ``GET /v1/usage?days=1|7|30``.

What Sergio spent (calls, tokens, cost, speed) per model and per provider,
from the telemetry Sergio already records, and every provider with its state:
connected, without a key, or out of quota for now. Not only Gemini: Google,
Anthropic, OpenAI, OpenRouter, Moonshot, MiniMax, AtlasCloud, DeepSeek and
local models (Ollama).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/usage", tags=["usage"])

# key, name shown, API key variable ("" = local, no key), model prefixes
PROVIDERS: List[tuple[str, str, str, tuple[str, ...]]] = [
    ("google", "Google Gemini", "GEMINI_API_KEY", ("gemini", "gemma")),
    ("anthropic", "Anthropic Claude", "ANTHROPIC_API_KEY", ("claude",)),
    (
        "openai",
        "OpenAI",
        "OPENAI_API_KEY",
        ("gpt-", "chatgpt-", "o1", "o3", "o4", "codex/"),
    ),
    ("openrouter", "OpenRouter", "OPENROUTER_API_KEY", ("openrouter/",)),
    ("moonshot", "Moonshot Kimi", "MOONSHOT_API_KEY", ("kimi", "moonshot")),
    ("minimax", "MiniMax", "MINIMAX_API_KEY", ("minimax",)),
    ("atlascloud", "AtlasCloud", "ATLASCLOUD_API_KEY", ("atlascloud/",)),
    ("deepseek", "DeepSeek", "DEEPSEEK_API_KEY", ("deepseek",)),
    ("local", "En este equipo (Ollama)", "", ()),
]


def provider_of(model: str) -> str:
    base = (model or "").lower().split("@", 1)[0]
    for key, _name, _env, prefixes in PROVIDERS:
        if prefixes and base.startswith(prefixes):
            return key
    return "local"


def _keys() -> Dict[str, bool]:
    try:
        from openjarvis.server.nodes_pro_routes import key_status

        found = dict(key_status())
    except Exception:  # noqa: BLE001 - fall back to the environment
        found = {}
    for _k, _n, env, _p in PROVIDERS:
        if env and env not in found:
            found[env] = bool(os.environ.get(env))
    if not found.get("GEMINI_API_KEY") and os.environ.get("GOOGLE_API_KEY"):
        found["GEMINI_API_KEY"] = True
    return found


def _out_of_quota() -> Dict[str, int]:
    """Model -> minutes until it can be asked again (Gemini remembers 429s)."""
    try:
        from openjarvis.engine import google_client
    except Exception:  # noqa: BLE001
        return {}
    now = time.monotonic()
    return {
        m: max(1, int((until - now) // 60))
        for m, until in google_client._EXHAUSTED.items()
        if until > now
    }


def _per_model(request: Request, since: float) -> List[Dict[str, Any]]:
    from openjarvis.server.api_routes import _telemetry_db_path

    path = _telemetry_db_path(request)
    if not path.exists():
        return []
    from openjarvis.telemetry.aggregator import TelemetryAggregator

    agg = TelemetryAggregator(path)
    try:
        rows = agg.per_model_stats(since=since)
    finally:
        agg.close()
    return [
        {
            "model": r.model_id,
            "provider": provider_of(r.model_id),
            "calls": r.call_count,
            "tokens": r.total_tokens,
            "cost": round(r.total_cost, 4),
            "avg_seconds": round(r.avg_latency, 2),
        }
        for r in sorted(rows, key=lambda r: -r.call_count)
        if r.model_id
    ]


def _available(request: Request) -> List[str]:
    engine = getattr(request.app.state, "engine", None)
    try:
        return sorted({str(m) for m in (engine.list_models() if engine else [])})
    except Exception:  # noqa: BLE001 - an engine that is down lists nothing
        return []


def _default_model(request: Request) -> str:
    config = getattr(request.app.state, "config", None)
    try:
        return str(config.intelligence.default_model or "")
    except AttributeError:
        return str(getattr(request.app.state, "model", "") or "")


@router.get("")
async def usage(request: Request, days: int = Query(7, ge=1, le=90)) -> Dict[str, Any]:
    since = time.time() - days * 86400
    try:
        models = _per_model(request, since)
    except Exception:  # noqa: BLE001 - no telemetry yet: say so with zeros
        models = []
    keys, tired = _keys(), _out_of_quota()
    available = _available(request)
    providers = []
    for key, name, env, _p in PROVIDERS:
        used = [m for m in models if m["provider"] == key]
        mine = [m for m in available if provider_of(m) == key]
        if key == "local":
            state = "conectado" if mine else "apagado"
        elif not keys.get(env):
            state = "sin clave"
        elif any(provider_of(m) == key for m in tired):
            state = "sin cuota"
        else:
            state = "conectado"
        providers.append(
            {
                "key": key,
                "name": name,
                "state": state,
                "models": mine,
                "calls": sum(m["calls"] for m in used),
                "cost": round(sum(m["cost"] for m in used), 4),
            }
        )
    return {
        "days": days,
        "default_model": _default_model(request),
        "totals": {
            "calls": sum(m["calls"] for m in models),
            "tokens": sum(m["tokens"] for m in models),
            "cost": round(sum(m["cost"] for m in models), 4),
        },
        "models": models,
        "providers": providers,
        "out_of_quota": [{"model": m, "minutes": n} for m, n in sorted(tired.items())],
    }


def _ollama_host(request: Request) -> str:
    config = getattr(request.app.state, "config", None)
    engine_cfg = getattr(config, "engine", None)
    host = getattr(engine_cfg, "ollama_host", None) or getattr(
        getattr(engine_cfg, "ollama", None), "host", None
    )
    return str(
        host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    ).rstrip("/")


@router.get("/local-models")
async def local_models(request: Request) -> Dict[str, Any]:
    """The models in Ollama on this computer. The page cannot ask Ollama
    itself: its security policy only lets it talk to Sergio's server."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            data = (await client.get(_ollama_host(request) + "/api/tags")).json()
    except Exception:  # noqa: BLE001 - Ollama closed: no local models
        return {"models": [], "running": False}
    models = [
        {"name": m.get("name", ""), "size": int(m.get("size") or 0)}
        for m in data.get("models") or []
    ]
    return {"models": models, "running": True}


class Preload(BaseModel):
    model: str = Field(..., min_length=1, max_length=200)


@router.post("/preload")
async def preload(body: Preload, request: Request) -> Dict[str, Any]:
    """Load a local model into memory (an empty prompt, kept 5 minutes)."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                _ollama_host(request) + "/api/generate",
                json={"model": body.model, "prompt": "", "keep_alive": "5m"},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "El modelo tardó más de 2 minutos en cargar.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Ollama no está abierto en este equipo.") from exc
    if resp.status_code != 200:
        raise HTTPException(502, f"Ollama no pudo cargar {body.model}.")
    return {"ok": True}


__all__ = ["PROVIDERS", "provider_of", "router"]

"""ToolOrchestra worker pools: the default and paper pools, the expert
mapping for the RL orchestrator, and validation of a cell's
``worker_pool`` override. Split out of ``toolorchestra.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openjarvis.agents.hybrid._prices import (
    PRICES,
)


def _expert_for(
    slot: str,
    local_model: Optional[str],
    local_endpoint: Optional[str],
    cloud_model: str,
    cloud_endpoint: str = "anthropic",
) -> Dict[str, Any]:
    """Map an upstream model slot (`answer-1`, `search-3`, …) to a worker spec.

    Routing policy:
      - `*-1` (frontier tier)  -> cloud (`cloud_model`), wtype keyed off
                                  `cloud_endpoint` ("anthropic"/"openai"/"gemini")
      - `*-2` (mid tier)       -> cloud `gpt-5-mini` (matches the paper's
                                  cost tier for mid OpenAI calls)
      - `*-3` (local tier)     -> local vLLM (`local_model`)
      - `answer-math-*`        -> same tiers as the numeric suffix
      - `search-*`             -> provider-native web search when the cloud
                                  endpoint supports it; otherwise Anthropic
    """
    if slot.startswith("search"):
        ep = (cloud_endpoint or "anthropic").lower()
        if ep == "openai":
            return {
                "name": f"search:{slot}",
                "type": "openai-web-search",
                "model": cloud_model,
            }
        if ep == "gemini":
            return {
                "name": f"search:{slot}",
                "type": "gemini-web-search",
                "model": cloud_model,
            }
        return {
            "name": f"search:{slot}",
            "type": "anthropic-web-search",
            "model": _DEFAULT_WEB_SEARCH_MODEL,
        }
    if slot.endswith("-1") or slot.endswith("-math-1"):
        ep = (cloud_endpoint or "anthropic").lower()
        if ep not in ("anthropic", "openai", "gemini"):
            ep = "anthropic"
        return {
            "name": f"frontier:{slot}",
            "type": ep,
            "model": cloud_model,
        }
    if slot.endswith("-2") or slot.endswith("-math-2"):
        return {
            "name": f"mid:{slot}",
            "type": "openai",
            "model": "gpt-5-mini",
        }
    # `*-3` / `*-4` collapse to local vLLM (paper uses Qwen3-32B etc.;
    # we substitute whatever local model the cell wired up).
    if local_model and local_endpoint:
        return {
            "name": f"local:{slot}",
            "type": "vllm",
            "model": local_model,
            "base_url": local_endpoint,
        }
    # Fallback if no local — gpt-5-mini.
    return {
        "name": f"mid-fallback:{slot}",
        "type": "openai",
        "model": "gpt-5-mini",
    }


_PAPER_CODER_OPENROUTER = "qwen/qwen-2.5-coder-32b-instruct"


_PAPER_GENERALIST_TIER3_OPENROUTER = "meta-llama/llama-3.3-70b-instruct"


def _paper_expert_for(
    slot: str,
    local_model: Optional[str],
    local_endpoint: Optional[str],
    cloud_model: str,
    cloud_endpoint: str = "openai",
) -> Dict[str, Any]:
    """Paper-match counterpart of ``_expert_for``.

    Differs from ``_expert_for``:
      - Search slots go to ``tavily-search`` (not Anthropic web_search).
      - Tier-3 generalist answer (``answer-3``) routes to Llama-3.3-70B via
        OpenRouter rather than collapsing onto the local vLLM.
      - Math slots route to the OpenRouter code specialist (Qwen-2.5-Coder-32B)
        as a substitute for the unavailable Qwen-2.5-Math-{72B,7B}.
      - ``reasoner-1`` / ``answer-1`` route to GPT-5 by default (paper).
    """
    if slot.startswith("search"):
        return {
            "name": f"tavily:{slot}",
            "type": "tavily-search",
            "model": "tavily",
        }
    if slot in ("answer-math-1", "answer-math-2"):
        return {
            "name": f"math-coder:{slot}",
            "type": "openrouter",
            "model": _PAPER_CODER_OPENROUTER,
        }
    if slot == "answer-3":
        return {
            "name": f"generalist-llama:{slot}",
            "type": "openrouter",
            "model": _PAPER_GENERALIST_TIER3_OPENROUTER,
        }
    if slot.endswith("-1"):
        # Tier-1 frontier reasoner / answer — paper uses GPT-5.
        return {
            "name": f"frontier:{slot}",
            "type": "openai",
            "model": "gpt-5",
        }
    if slot.endswith("-2"):
        return {
            "name": f"mid:{slot}",
            "type": "openai",
            "model": "gpt-5-mini",
        }
    # `*-3` / `*-4` collapse onto the local vLLM (the orchestrator endpoint
    # also serves the local Qwen for the rare local-tier slot).
    if local_model and local_endpoint:
        return {
            "name": f"local:{slot}",
            "type": "vllm",
            "model": local_model,
            "base_url": local_endpoint,
        }
    return {
        "name": f"mid-fallback:{slot}",
        "type": "openai",
        "model": "gpt-5-mini",
    }


def _paper_pool(
    local_model: Optional[str],
    local_endpoint: Optional[str],
) -> List[Dict[str, Any]]:
    """Paper-match worker pool (registered for traces / inspection).

    NOTE: in RL mode the orchestrator dispatches via tool/slot rather than
    worker_id, so this list is purely informational — `_paper_expert_for`
    is the actual routing function. We still return a list here so the
    paradigm's trace metadata has something concrete to log.
    """
    pool: List[Dict[str, Any]] = []
    if local_model and local_endpoint:
        pool.append(
            {
                "id": len(pool),
                "name": "local-qwen",
                "type": "vllm",
                "model": local_model,
                "base_url": local_endpoint,
                "description": "Local Qwen vLLM (paper uses Qwen3-32B).",
            }
        )
    pool.append(
        {
            "id": len(pool),
            "name": "tavily-search",
            "type": "tavily-search",
            "model": "tavily",
            "description": "Tavily web search.",
        }
    )
    pool.append(
        {
            "id": len(pool),
            "name": "modal-python",
            "type": "modal-python",
            "model": "modal-python",
            "description": "Modal Sandbox for one-shot Python exec.",
        }
    )
    pool.append(
        {
            "id": len(pool),
            "name": "code-specialist",
            "type": "openrouter",
            "model": _PAPER_CODER_OPENROUTER,
            "description": "Qwen-2.5-Coder-32B via OpenRouter (paper).",
        }
    )
    pool.append(
        {
            "id": len(pool),
            "name": "generalist-llama",
            "type": "openrouter",
            "model": _PAPER_GENERALIST_TIER3_OPENROUTER,
            "description": "Llama-3.3-70B-Instruct via OpenRouter (paper tier-3).",
        }
    )
    pool.append(
        {
            "id": len(pool),
            "name": "generalist-gpt5",
            "type": "openai",
            "model": "gpt-5",
            "description": "GPT-5 frontier generalist.",
        }
    )
    pool.append(
        {
            "id": len(pool),
            "name": "generalist-gpt5-mini",
            "type": "openai",
            "model": "gpt-5-mini",
            "description": "GPT-5-mini mid generalist.",
        }
    )
    return pool


def _default_pool(
    local_model: Optional[str],
    local_endpoint: Optional[str],
    cloud_model: str = "claude-opus-4-7",
    cloud_endpoint: str = "anthropic",
) -> List[Dict[str, Any]]:
    """Default heterogeneous worker pool.

    The frontier worker's ``type`` + ``model`` track the cell's resolved
    ``(cloud_model, cloud_endpoint)`` pair so non-Anthropic cells (gpt-5,
    gemini-2.5-pro, …) route their frontier slot to the right SDK.
    """
    ep = (cloud_endpoint or "anthropic").lower()
    if ep not in ("anthropic", "openai", "gemini"):
        ep = "anthropic"
    pool: List[Dict[str, Any]] = []
    if local_model and local_endpoint:
        pool.append(
            {
                "id": len(pool),
                "name": "local-qwen",
                "type": "vllm",
                "model": local_model,
                "base_url": local_endpoint,
                "description": (
                    "Open-weights Qwen3.5 served locally. Cheap and fast. Good at "
                    "concise extraction, formatting, arithmetic on given data."
                ),
            }
        )
    if ep == "openai":
        search_type = "openai-web-search"
        search_model = cloud_model
        search_desc = "OpenAI hosted web search on the configured frontier model."
    elif ep == "gemini":
        search_type = "gemini-web-search"
        search_model = cloud_model
        search_desc = "Gemini Google Search grounding on the configured frontier model."
    else:
        search_type = "anthropic-web-search"
        search_model = _DEFAULT_WEB_SEARCH_MODEL
        search_desc = "Anthropic server-side web_search."
    pool.append(
        {
            "id": len(pool),
            "name": "web-search",
            "type": search_type,
            "model": search_model,
            "description": (
                f"{search_desc} Use for facts that need a lookup "
                "(recent events, rare names/dates, niche sources). Returns a digest."
            ),
        }
    )
    pool.append(
        {
            "id": len(pool),
            "name": f"frontier-{ep}",
            "type": ep,
            "model": cloud_model,
            "description": (
                "Frontier reasoning model. Use for hard multi-step reasoning, "
                "code review, or a final synthesis pass. Expensive — use sparingly."
            ),
        }
    )
    pool.append(
        {
            "id": len(pool),
            "name": "frontier-openai-mini",
            "type": "openai",
            "model": "gpt-5-mini",
            "description": (
                "Mid-tier OpenAI model. Solid general knowledge and reasoning at a "
                "fraction of frontier cost."
            ),
        }
    )
    return pool


# Worker types toolorchestra's `_call_worker` actually dispatches.
#
# Paper-match additions (2026-05-19) — opt in via `method_cfg.pool = "paper"`:
#   `tavily-search`  — Tavily API search (the paper's web tool).
#   `openrouter`     — OpenAI-compatible client at openrouter.ai/api/v1.
#                      Used for the code/math specialists and Llama-3.3-70B /
#                      Qwen3-32B generalists.
#   `modal-python`   — One-shot Python exec in a fresh Modal Sandbox (the
#                      paper's "Python sandbox" inside `enhance_reasoning`).
_TOOLORCH_VALID_TYPES = (
    "vllm",
    "openai",
    "anthropic",
    "anthropic-web-search",
    "openai-web-search",
    "gemini",
    "gemini-web-search",
    "tavily-search",
    "openrouter",
    "modal-python",
)


_TOOLORCH_SEARCH_TYPES = (
    "anthropic-web-search",
    "openai-web-search",
    "gemini-web-search",
    "tavily-search",
)


# Default model used when an `anthropic-web-search` entry omits `model`.
_DEFAULT_WEB_SEARCH_MODEL = "claude-haiku-4-5"


def _resolve_worker_pool(
    cfg: Dict[str, Any],
    local_model: Optional[str],
    local_endpoint: Optional[str],
    cloud_model: str,
    cloud_endpoint: str = "anthropic",
) -> List[Dict[str, Any]]:
    """Return the worker pool for this run.

    Strict replace, not merge: if ``cfg["worker_pool"]`` is set, the
    default pool is ignored entirely. Falls back to ``_default_pool`` when
    the override is absent.

    Each user-supplied entry must be a dict with keys ``id``, ``name``,
    ``type``, and (for non-search types) ``model``. Search worker types are
    ``anthropic-web-search``, ``openai-web-search``, ``gemini-web-search``,
    and ``tavily-search``. ``anthropic-web-search`` entries may omit
    ``model`` — it defaults to ``claude-haiku-4-5``. OpenAI and Gemini
    search workers default to the configured cloud model. Tavily does not
    require a model.

    Substitution: ``model = "$local"`` (or ``"<local>"``) resolves to
    ``local_model``; ``model = "$cloud"`` / ``"<cloud>"`` to ``cloud_model``.

    On any validation failure, raises ``ValueError`` with the message
    ``"Invalid worker_pool entry [<id>]: <reason>"``. Fails fast at agent
    init rather than mid-task.
    """
    override = cfg.get("worker_pool")
    if override is None:
        return _default_pool(local_model, local_endpoint, cloud_model, cloud_endpoint)
    if not isinstance(override, list) or not override:
        raise ValueError(
            "Invalid worker_pool entry [-]: worker_pool must be a non-empty list"
        )

    resolved: List[Dict[str, Any]] = []
    seen_ids: set = set()
    has_non_search = False
    for raw in override:
        wid_repr = raw.get("id", "?") if isinstance(raw, dict) else "?"
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid worker_pool entry [{wid_repr}]: entry must be a dict"
            )
        entry = dict(raw)
        wid = entry.get("id")
        if not isinstance(wid, int):
            raise ValueError(
                f"Invalid worker_pool entry [{wid_repr}]: 'id' must be an int"
            )
        if wid in seen_ids:
            raise ValueError(f"Invalid worker_pool entry [{wid}]: duplicate id")
        seen_ids.add(wid)
        if not entry.get("name") or not isinstance(entry["name"], str):
            raise ValueError(
                f"Invalid worker_pool entry [{wid}]: 'name' must be a non-empty string"
            )
        wtype = entry.get("type") or entry.get("endpoint")
        if not isinstance(wtype, str) or wtype.lower() not in _TOOLORCH_VALID_TYPES:
            raise ValueError(
                f"Invalid worker_pool entry [{wid}]: 'type' must be one of "
                f"{_TOOLORCH_VALID_TYPES} (got {wtype!r})"
            )
        wtype = wtype.lower()
        entry["type"] = wtype
        # Substitute $local / $cloud placeholders (before any model check).
        model = entry.get("model")
        if isinstance(model, str) and model in ("$local", "<local>"):
            if not local_model:
                raise ValueError(
                    f"Invalid worker_pool entry [{wid}]: model='{model}' "
                    "requires a local_model to be configured for this cell"
                )
            model = local_model
            entry["model"] = model
        elif isinstance(model, str) and model in ("$cloud", "<cloud>"):
            model = cloud_model
            entry["model"] = model
        if wtype in _TOOLORCH_SEARCH_TYPES:
            if model in (None, ""):
                if wtype == "anthropic-web-search":
                    model = _DEFAULT_WEB_SEARCH_MODEL
                elif wtype in ("openai-web-search", "gemini-web-search"):
                    model = cloud_model
                else:
                    model = wtype
                entry["model"] = model
            elif not isinstance(model, str):
                raise ValueError(
                    f"Invalid worker_pool entry [{wid}]: 'model' must be a string when set"
                )
            if (
                wtype in ("openai-web-search", "gemini-web-search")
                and model not in PRICES
            ):
                raise ValueError(
                    f"Invalid worker_pool entry [{wid}]: model {model!r} "
                    f"is not in PRICES (known: {sorted(PRICES)})"
                )
            # Search workers don't satisfy the "needs a solver" requirement.
        else:
            if not isinstance(model, str) or not model:
                raise ValueError(
                    f"Invalid worker_pool entry [{wid}]: 'model' must be a non-empty string"
                )
            if wtype == "vllm":
                if not entry.get("base_url"):
                    if not local_endpoint:
                        raise ValueError(
                            f"Invalid worker_pool entry [{wid}]: vllm worker needs "
                            "'base_url' (or a configured local_endpoint to fall back to)"
                        )
                    entry["base_url"] = local_endpoint
                entry.setdefault("api_key", "EMPTY")
            else:
                if model not in PRICES:
                    raise ValueError(
                        f"Invalid worker_pool entry [{wid}]: model {model!r} "
                        f"is not in PRICES (known: {sorted(PRICES)})"
                    )
            has_non_search = True
        entry.setdefault(
            "description",
            f"User-supplied {wtype} worker ({model}).",
        )
        resolved.append(entry)

    if not has_non_search:
        raise ValueError(
            "Invalid worker_pool entry [-]: worker_pool must contain at least "
            "one non-search worker (vllm / openai / anthropic / gemini)"
        )
    return resolved

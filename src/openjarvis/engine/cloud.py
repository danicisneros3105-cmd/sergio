"""Cloud inference engine.

OpenAI, Anthropic, Google, MiniMax, DeepSeek, Kimi (Moonshot) and Atlas Cloud API
backends.
"""

from __future__ import annotations

import json  # noqa: F401 — used by the cloud_*.py provider mixins
import logging
import os
import re
import time
import uuid  # noqa: F401 — used by the cloud_*.py provider mixins
from collections.abc import AsyncIterator, Sequence
from typing import Any, Dict, List

# Used through the provider mixins (cloud_*.py), which look them up here;
# tests patch httpx on this module.
import httpx  # noqa: F401 — used by the mixins; tests patch it here

from openjarvis.core.registry import EngineRegistry
from openjarvis.core.types import Message
from openjarvis.engine._base import (
    EngineConnectionError,
    InferenceEngine,
    messages_to_dicts,
)
from openjarvis.engine._stubs import StreamChunk

logger = logging.getLogger(__name__)

# Pricing per million tokens (input, output)
PRICING: Dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5": (10.00, 30.00),
    "gpt-5.4": (15.00, 60.00),
    "gpt-5-mini": (0.25, 2.00),
    "o3-mini": (1.10, 4.40),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
    "claude-haiku-3-5-20241022": (0.80, 4.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3-pro": (2.00, 12.00),
    "gemini-3-flash": (0.50, 3.00),
    "gemini-3.1-pro-preview": (2.50, 15.00),
    "gemini-3.1-flash-lite-preview": (0.30, 2.50),
    "gemini-3-flash-preview": (0.50, 3.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "MiniMax-M3": (0.30, 1.20),
    "MiniMax-M2.7": (0.30, 1.20),
    "MiniMax-M2.7-highspeed": (0.60, 2.40),
    "MiniMax-M2.5": (0.30, 1.20),
    "MiniMax-M2.5-highspeed": (0.60, 2.40),
    "deepseek-v4-flash": (0.27, 1.10),
    "deepseek-v4-pro": (0.55, 2.19),
    # Atlas Cloud — an aggregator, so keys carry the "atlascloud/" routing
    # prefix (same convention as OpenRouter below). Rates are USD per 1M
    # tokens, read from the gateway's own catalog: GET
    # https://api.atlascloud.ai/v1/models returns pricing.prompt /
    # pricing.completion in USD *per token*; multiply by 1e6.
    "atlascloud/openai/gpt-4.1-mini": (0.40, 1.60),
    "atlascloud/openai/gpt-5.4-mini": (0.75, 4.50),
    "atlascloud/deepseek-ai/deepseek-v3.2": (0.26, 0.38),
    "atlascloud/Qwen/Qwen3-235B-A22B-Instruct-2507": (0.20, 0.88),
    "atlascloud/qwen/qwen3.5-35b-a3b": (0.225, 1.80),
    "atlascloud/zai-org/GLM-4.6": (0.60, 2.20),
    "atlascloud/moonshotai/kimi-k2.5": (0.49, 2.50),
    "atlascloud/minimaxai/minimax-m2.5": (0.295, 1.20),
}

_MINIMAX_M3_LONG_CONTEXT_THRESHOLD = 512_000
_MINIMAX_M3_LONG_CONTEXT_PRICING = (0.60, 2.40)

# Well-known model IDs per provider
_OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",
    "gpt-5.4",
    "gpt-5-mini",
    "o3-mini",
]
_ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-3-5-20241022",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-haiku-4-5-20251001",
]
_GOOGLE_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3-pro",
    "gemini-3-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
]
_MINIMAX_MODELS = [
    "MiniMax-M3",
    "MiniMax-M2.7",
    "MiniMax-M2.7-highspeed",
    "MiniMax-M2.5",
    "MiniMax-M2.5-highspeed",
]
_DEEPSEEK_MODELS = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
]
# Kimi (Moonshot). The live list comes from the API; this is the fallback.
_KIMI_MODELS = [
    "kimi-k2.6",
    "kimi-k2.5",
    "kimi-k2-turbo",
    "kimi-k2-thinking",
]
KIMI_DEFAULT_BASE_URL = "https://api.moonshot.ai/v1"

# OpenRouter models — prefixed with "openrouter/" so they can be identified
_OPENROUTER_POPULAR = [
    "openrouter/auto",
    "openrouter/openai/gpt-4o",
    "openrouter/anthropic/claude-sonnet-4",
    "openrouter/google/gemini-2.5-pro",
    "openrouter/meta-llama/llama-3.3-70b-instruct",
    "openrouter/mistralai/mistral-large",
    "openrouter/deepseek/deepseek-r1",
    "openrouter/qwen/qwen3-235b-a22b",
]

# Atlas Cloud models — prefixed with "atlascloud/" so they can be identified.
# Atlas Cloud is an OpenAI-compatible aggregator whose own model IDs are
# already "vendor/model", so the prefix is what keeps
# "atlascloud/anthropic/claude-*" from being routed to the Anthropic SDK.
# The gateway serves many more than these — GET /v1/models lists what is
# currently routable, and any ID from there works as "atlascloud/<id>".
_ATLASCLOUD_POPULAR = [
    "atlascloud/openai/gpt-4.1-mini",
    "atlascloud/openai/gpt-5.4-mini",
    "atlascloud/deepseek-ai/deepseek-v3.2",
    "atlascloud/Qwen/Qwen3-235B-A22B-Instruct-2507",
    "atlascloud/qwen/qwen3.5-35b-a3b",
    "atlascloud/zai-org/GLM-4.6",
    "atlascloud/moonshotai/kimi-k2.5",
    "atlascloud/minimaxai/minimax-m2.5",
]

# Codex models — prefixed with "codex/" for ChatGPT Plus/Pro subscribers.
# Uses the Responses API at chatgpt.com, not the standard OpenAI API.
_CODEX_MODELS = [
    "codex/gpt-4o",
    "codex/gpt-4o-mini",
    "codex/o3-mini",
    "codex/gpt-5-mini",
    "codex/gpt-5-mini-2025-08-07",
]


def _is_minimax_model(model: str) -> bool:
    return model.lower().startswith("minimax")


def _is_deepseek_model(model: str) -> bool:
    return model.lower().startswith("deepseek")


def _is_kimi_model(model: str) -> bool:
    return model.lower().startswith(("kimi", "moonshot"))


def _env_key(*names: str) -> str:
    """API key from the environment, cleaned of copy-paste damage."""
    import unicodedata

    for name in names:
        raw = os.environ.get(name, "")
        if raw:
            key = unicodedata.normalize("NFKC", raw)
            key = "".join(c for c in key if c.isprintable() and not c.isspace())
            key = key.strip("'\"`")
            if key.isascii():
                return key
            logger.warning("%s contains non-ASCII characters; ignoring it", name)
    return ""


def _kimi_create(client: Any, create_kwargs: Dict[str, Any]) -> Any:
    """Kimi chat call: instant mode (no long thinking) when the model has it.

    K2.5/K2.6 think by default, which is slow for voice; ``thinking: disabled``
    turns that off. Models without the switch reject it, so retry without.
    """
    model = str(create_kwargs.get("model", "")).lower()
    if model.startswith("kimi-k2.") and "thinking" not in model:
        try:
            return _chat_completion_with_temperature_retry(
                client,
                {**create_kwargs, "extra_body": {"thinking": {"type": "disabled"}}},
            )
        except Exception as exc:  # noqa: BLE001
            if "thinking" not in str(exc).lower():
                raise
    return _chat_completion_with_temperature_retry(client, create_kwargs)


_KIMI_PASSTHROUGH = ("tools", "tool_choice", "top_p", "stop", "response_format")


def _is_openrouter_model(model: str) -> bool:
    return model.startswith("openrouter/")


def _is_atlascloud_model(model: str) -> bool:
    return model.startswith("atlascloud/")


def _is_codex_model(model: str) -> bool:
    return model.startswith("codex/")


def _is_anthropic_model(model: str) -> bool:
    # Aggregator-prefixed IDs are excluded: "atlascloud/anthropic/claude-*"
    # contains "claude" but must go to the aggregator, not the Anthropic SDK.
    return (
        "claude" in model.lower()
        and not _is_openrouter_model(model)
        and not _is_atlascloud_model(model)
    )


def _is_google_model(model: str) -> bool:
    return (
        "gemini" in model.lower()
        and not _is_openrouter_model(model)
        and not _is_atlascloud_model(model)
    )


EFFORTS = ("minimal", "low", "medium", "high")


def split_effort(model: str) -> tuple[str, str]:
    """``gemini-3.8-flash@high`` -> (``gemini-3.8-flash``, ``high``).

    Sergio asks for an effort (thinking) level per request this way, so the
    OpenAI-compatible API does not need an extra field.
    """
    name, sep, effort = model.rpartition("@")
    if sep and effort.lower() in EFFORTS:
        return name, effort.lower()
    return model, ""


def _gemini_generation(model: str) -> float:
    found = re.match(r"gemini-(\d+(?:\.\d+)?)", model)
    return float(found.group(1)) if found else 0.0


# Google's documented placeholder for function calls whose real thought
# signature is unknown (written by another model, or lost).
SKIP_SIGNATURE = b"skip_thought_signature_validator"


def google_config_kwargs(
    model: str, temperature: float, max_tokens: int, effort: str = ""
) -> Dict[str, Any]:
    """GenerateContentConfig arguments for a Gemini model.

    Gemini 3+ replaced temperature with ``thinking_level`` (low/medium/high);
    thinking tokens share the output budget, so give it room.
    """
    if _gemini_generation(model) < 3:
        return {"temperature": temperature, "max_output_tokens": max_tokens}
    kwargs: Dict[str, Any] = {"max_output_tokens": max(max_tokens, 8192)}
    level = effort or os.environ.get("SERGIO_EFFORT", "").strip().lower()
    if level in EFFORTS:
        if level == "minimal" and not any(
            m in model for m in ("flash-lite", "3.5-flash", "3-flash")
        ):
            level = "low"  # Pro and 3.8 Flash have no minimal level
        try:
            from google.genai import types as genai_types

            kwargs["thinking_config"] = genai_types.ThinkingConfig(
                thinking_level=level.upper()
            )
        except Exception:  # noqa: BLE001 — older SDK: default thinking
            pass
    return kwargs


# Positive prefix predicate for genuine OpenAI models. Kept in sync with
# ``server/cloud_router.py:_OPENAI_PREFIXES`` so local-vs-cloud classification
# agrees across the codebase. Used by ``_client_for_model``/``can_serve`` so the
# cloud engine never claims it can serve an unrecognized (e.g. local Ollama)
# model name just because an OpenAI key happens to be present (see #335).
_OPENAI_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")


def _is_openai_model(model: str) -> bool:
    """True only for genuine OpenAI models (gpt-*, chatgpt-*, o1/o3/o4 series).

    Defined positively so that an unrecognized model name (a local Ollama model
    like ``qwen3.5:0.8b``, or a typo) is NOT treated as an OpenAI model. This is
    the routing surface ``can_serve`` relies on; ``generate``/``stream`` keep
    their OpenAI fall-through so an explicitly-requested unknown cloud model
    still errors loudly at call time.

    Caveat: a user may repoint the OpenAI client at an OpenAI-compatible server
    (vLLM/LM Studio) via ``OPENAI_BASE_URL`` and legitimately serve non-gpt
    names. That path is undocumented/untested in this engine; if it is added,
    this predicate (or ``_client_for_model``) should treat a configured custom
    base_url as "serves anything".
    """
    m = model.lower()
    if m in (name.lower() for name in _OPENAI_MODELS):
        return True
    return m.startswith(_OPENAI_PREFIXES)


def _is_openai_reasoning_model(model: str) -> bool:
    """Check if model is an OpenAI reasoning model that restricts temperature."""
    m = model.lower()
    # o1/o3 series and gpt-5-mini (all variants) are reasoning models
    if m.startswith(("o1", "o3")):
        return True
    return m == "gpt-5-mini" or m.startswith("gpt-5-mini-")


def _is_unsupported_temperature_error(exc: Exception) -> bool:
    """True if an OpenAI 400 says the model rejects a non-default temperature.

    Some models (e.g. gpt-5) only accept the default temperature and return
    ``code: unsupported_value`` for ``param: temperature`` (see #426, #1019). We
    can't enumerate every such model up front, so detect the error and retry
    without temperature — mirroring the tools-400 retry in the local engines.
    """
    message = str(exc).lower()
    if "temperature" not in message:
        return False
    return (
        "unsupported_value" in message
        or "unsupported value" in message
        or "only the default" in message
        or "does not support" in message
        or "unsupported parameter" in message
        or "is not supported" in message
    )


def _chat_completion_with_temperature_retry(
    client: Any,
    create_kwargs: Dict[str, Any],
) -> Any:
    """Invoke client.chat.completions.create, retrying without temperature on 400."""
    try:
        return client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        if "temperature" in create_kwargs and _is_unsupported_temperature_error(exc):
            create_kwargs.pop("temperature", None)
            return client.chat.completions.create(**create_kwargs)
        raise


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost based on the hardcoded pricing table."""
    # Try exact match first, then prefix match
    prices = PRICING.get(model)
    if prices is None:
        for key, val in PRICING.items():
            if model.startswith(key):
                prices = val
                break
    if prices is None:
        return 0.0
    if (
        model.startswith("MiniMax-M3")
        and prompt_tokens > _MINIMAX_M3_LONG_CONTEXT_THRESHOLD
    ):
        prices = _MINIMAX_M3_LONG_CONTEXT_PRICING
    input_cost = (prompt_tokens / 1_000_000) * prices[0]
    output_cost = (completion_tokens / 1_000_000) * prices[1]
    return input_cost + output_cost


def _first_choice_or_raise(resp: Any, *, provider: str, model: str) -> Any:
    """Return the first completion choice or surface the provider error."""
    choices = getattr(resp, "choices", None)
    if choices:
        return choices[0]

    error = getattr(resp, "error", None)
    if isinstance(error, dict):
        detail = str(error.get("message") or error)
    elif error is not None:
        detail = str(getattr(error, "message", None) or error)
    else:
        detail = ""

    message = f"{provider} returned no choices for model {model!r}"
    raise EngineConnectionError(
        message + (f": {detail}" if detail else " and no error message")
    )


def _serialize_anthropic_block(block: Any) -> Dict[str, Any]:
    """Turn an Anthropic content block into a JSON-safe dict for tracing.

    Handles every block type Anthropic returns today (text, tool_use,
    server_tool_use, web_search_tool_result, tool_result, thinking). Nested
    content (e.g. ``web_search_tool_result.content`` is itself a list of
    citation/result blocks) recurses so the trace has the full payload, not
    a truncated summary.
    """
    out: Dict[str, Any] = {
        "type": getattr(block, "type", None) or type(block).__name__,
    }
    for attr in (
        "id",
        "name",
        "input",
        "text",
        "thinking",
        "signature",
        "tool_use_id",
        "content",
    ):
        if not hasattr(block, attr):
            continue
        val = getattr(block, attr)
        if attr == "content" and isinstance(val, list):
            out[attr] = [_serialize_anthropic_block(b) for b in val]
        elif hasattr(val, "model_dump"):
            try:
                out[attr] = val.model_dump()
            except Exception:
                out[attr] = str(val)
        else:
            out[attr] = val
    return out


def _annotate_anthropic_cache(messages: list[dict]) -> list[dict]:
    """Add cache_control to system message for Anthropic prompt caching."""
    result = []
    for msg in messages:
        if msg.get("role") == "system":
            content = msg["content"]
            if isinstance(content, str):
                content = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            elif isinstance(content, list):
                content = [
                    {**block, "cache_control": {"type": "ephemeral"}}
                    for block in content
                ]
            result.append({**msg, "content": content})
        else:
            result.append(msg)
    return result


def _convert_tools_to_anthropic(
    openai_tools: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert OpenAI function-calling tools to Anthropic tool format."""
    result = []
    for tool in openai_tools:
        func = tool.get("function", {})
        result.append(
            {
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            }
        )
    return result


def _convert_tools_to_google(
    openai_tools: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert OpenAI function-calling tools to Google function declarations."""
    declarations = []
    for tool in openai_tools:
        func = tool.get("function", {})
        declaration: Dict[str, Any] = {
            "name": func.get("name", ""),
            "description": func.get("description", ""),
        }
        params = google_schema(func.get("parameters") or {})
        if params.get("properties"):
            declaration["parameters"] = params
        declarations.append(declaration)
    return declarations


# JSON-Schema keys the Gemini API accepts in function parameters; others
# (additionalProperties, $schema, oneOf, const, ...) make it reject the call.
_GOOGLE_SCHEMA_KEYS = {
    "type",
    "format",
    "description",
    "nullable",
    "enum",
    "properties",
    "required",
    "items",
    "anyOf",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "pattern",
    "title",
}


# Free keys get a daily quota per model: siblings to try when one runs out.
FLASH_FAMILY = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-flash-latest",
    "gemini-2.5-flash",
)
PRO_FAMILY = ("gemini-3.1-pro-preview", "gemini-pro-latest", "gemini-2.5-pro")
LITE_FAMILY = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
)
QUOTA_COOLDOWN = 3600.0
_QUOTA_EXHAUSTED: Dict[str, float] = {}


def quota_fallbacks(model: str) -> List[str]:
    """Other Gemini models to use when *model* has no quota left."""
    name = model.lower()
    if not name.startswith("gemini"):
        return []
    if "lite" in name:
        family = [*LITE_FAMILY, *FLASH_FAMILY]
    elif "pro" in name:
        family = [*PRO_FAMILY, *FLASH_FAMILY]
    else:
        family = [*FLASH_FAMILY, *LITE_FAMILY]
    return [m for m in family if m != name]


def _exhausted(model: str) -> bool:
    return _QUOTA_EXHAUSTED.get(model, 0.0) > time.monotonic()


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or "exceeded your current quota" in text


BUSY_COOLDOWN = 120.0  # an overloaded model gets a short rest only


def _is_busy_error(exc: Exception) -> bool:
    """Google is overloaded right now (503 / high demand): try a sibling."""
    text = str(exc)
    return any(
        marker in text
        for marker in (
            "503",
            "UNAVAILABLE",
            "high demand",
            "overloaded",
            "500 INTERNAL",
        )
    )


def google_schema(schema: Any) -> Dict[str, Any]:
    """A JSON Schema reduced to what Gemini function declarations accept."""
    if not isinstance(schema, dict):
        return {"type": "string"}
    out: Dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _GOOGLE_SCHEMA_KEYS:
            continue
        if key == "type" and isinstance(value, list):  # ["string", "null"]
            kinds = [v for v in value if v != "null"]
            out["type"] = kinds[0] if kinds else "string"
            if "null" in value:
                out["nullable"] = True
        elif key == "properties" and isinstance(value, dict):
            out["properties"] = {k: google_schema(v) for k, v in value.items()}
        elif key == "items":
            out["items"] = google_schema(value)
        elif key == "anyOf" and isinstance(value, list):
            out["anyOf"] = [google_schema(v) for v in value]
        elif key == "enum" and isinstance(value, list):
            out["enum"] = [str(v) for v in value]  # Gemini enums are strings
        else:
            out[key] = value
    if "oneOf" in schema and "anyOf" not in out:
        out["anyOf"] = [google_schema(v) for v in schema["oneOf"]]
    if out.get("type") == "array" and "items" not in out:
        out["items"] = {"type": "string"}
    if "required" in out and isinstance(out.get("properties"), dict):
        out["required"] = [r for r in out["required"] if r in out["properties"]]
    if "type" not in out and "anyOf" not in out:
        out["type"] = "object" if "properties" in out else "string"
    return out


# Provider groups live in their own modules; they look helpers up here.
from openjarvis.engine.cloud_anthropic import AnthropicMixin  # noqa: E402
from openjarvis.engine.cloud_compat import CompatProvidersMixin  # noqa: E402
from openjarvis.engine.cloud_google import GoogleMixin  # noqa: E402
from openjarvis.engine.cloud_openai import OpenAIMixin  # noqa: E402


@EngineRegistry.register("cloud")
class CloudEngine(
    AnthropicMixin, GoogleMixin, OpenAIMixin, CompatProvidersMixin, InferenceEngine
):
    """Cloud inference via OpenAI, Anthropic, Google, MiniMax, DeepSeek, and
    Atlas Cloud SDKs."""

    engine_id = "cloud"
    is_cloud = True

    def __init__(self) -> None:
        self._openai_client: Any = None
        self._anthropic_client: Any = None
        self._google_client: Any = None
        self._openrouter_client: Any = None
        self._atlascloud_client: Any = None
        self._minimax_client: Any = None
        self._deepseek_client: Any = None
        self._kimi_client: Any = None
        self._kimi_live_models: List[str] | None = None
        self._codex_client: Any = None
        # Gemini thought_signatures: tool_call_id -> signature bytes
        self._thought_sigs: Dict[str, bytes] = {}
        self._init_clients()

    def _init_clients(self) -> None:
        if os.environ.get("OPENAI_API_KEY"):
            try:
                import openai

                self._openai_client = openai.OpenAI()
            except ImportError:
                pass
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic

                self._anthropic_client = anthropic.Anthropic()
            except ImportError:
                pass
        gemini_key = _env_key("GEMINI_API_KEY", "GOOGLE_API_KEY")
        if gemini_key:
            try:
                from google import genai  # noqa: F401 — fail early if missing

                from openjarvis.engine.google_client import SwitchingClient

                # Gemini API or Vertex AI: the client finds which one the
                # key belongs to (AQ. keys can be either).
                self._google_client = SwitchingClient(gemini_key)
            except ImportError:
                pass
        openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        if openrouter_key:
            try:
                import openai

                self._openrouter_client = openai.OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_key,
                )
            except ImportError:
                pass
        atlascloud_key = os.environ.get("ATLASCLOUD_API_KEY")
        if atlascloud_key:
            try:
                import openai

                self._atlascloud_client = openai.OpenAI(
                    base_url="https://api.atlascloud.ai/v1",
                    api_key=atlascloud_key,
                )
            except ImportError:
                pass
        minimax_key = os.environ.get("MINIMAX_API_KEY")
        if minimax_key:
            try:
                import openai

                self._minimax_client = openai.OpenAI(
                    base_url="https://api.minimax.io/v1",
                    api_key=minimax_key,
                )
            except ImportError:
                pass
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
        if deepseek_key:
            try:
                import openai

                self._deepseek_client = openai.OpenAI(
                    base_url="https://api.deepseek.com/v1",
                    api_key=deepseek_key,
                )
            except ImportError:
                pass
        kimi_key = _env_key("MOONSHOT_API_KEY", "KIMI_API_KEY")
        if kimi_key:
            try:
                import openai

                self._kimi_client = openai.OpenAI(
                    base_url=os.environ.get("MOONSHOT_BASE_URL", KIMI_DEFAULT_BASE_URL),
                    api_key=kimi_key,
                )
            except ImportError:
                pass
        # Codex — uses the OpenAI Responses API.
        # Supports both standard API keys (api.openai.com) and ChatGPT
        # OAuth tokens (chatgpt.com) via OPENAI_CODEX_BASE_URL override.
        codex_token = os.environ.get("OPENAI_CODEX_API_KEY")
        if codex_token:
            codex_url = os.environ.get(
                "OPENAI_CODEX_BASE_URL",
                "https://api.openai.com/v1",
            ).rstrip("/")
            if not codex_url.endswith("/responses"):
                codex_url += "/responses"
            self._codex_client = {
                "token": codex_token,
                "url": codex_url,
            }

    def generate(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        kw = dict(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        if _is_codex_model(model):
            return self._generate_codex(messages, **kw)
        if _is_openrouter_model(model):
            return self._generate_openrouter(messages, **kw)
        if _is_atlascloud_model(model):
            return self._generate_atlascloud(messages, **kw)
        if _is_minimax_model(model):
            return self._generate_minimax(messages, **kw)
        if _is_kimi_model(model):
            return self._generate_kimi(messages, **kw)
        if _is_deepseek_model(model):
            return self._generate_deepseek(messages, **kw)
        if _is_anthropic_model(model):
            return self._generate_anthropic(messages, **kw)
        if _is_google_model(model):
            return self._generate_google(messages, **kw)
        return self._generate_openai(messages, **kw)

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        kw = dict(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        if _is_codex_model(model):
            async for token in self._stream_codex(messages, **kw):
                yield token
        elif _is_openrouter_model(model):
            async for token in self._stream_openrouter(messages, **kw):
                yield token
        elif _is_atlascloud_model(model):
            async for token in self._stream_atlascloud(messages, **kw):
                yield token
        elif _is_minimax_model(model):
            async for token in self._stream_minimax(messages, **kw):
                yield token
        elif _is_kimi_model(model):
            async for token in self._stream_kimi(messages, **kw):
                yield token
        elif _is_deepseek_model(model):
            async for token in self._stream_deepseek(messages, **kw):
                yield token
        elif _is_anthropic_model(model):
            async for token in self._stream_anthropic(messages, **kw):
                yield token
        elif _is_google_model(model):
            async for token in self._stream_google(messages, **kw):
                yield token
        else:
            async for token in self._stream_openai(messages, **kw):
                yield token

    # -- stream_full: rich streaming with tool_calls support ----------------

    async def _stream_full_openai(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Yield StreamChunks from an OpenAI-compatible streaming response.

        Works for OpenAI, OpenRouter, Atlas Cloud, MiniMax, DeepSeek, and Codex.
        """
        if _is_codex_model(model):
            # Codex uses Responses API — fall back to base stream_full wrapper
            async for chunk in super().stream_full(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                yield chunk
            return
        if _is_openrouter_model(model):
            client = self._openrouter_client
            if client is None:
                raise EngineConnectionError("OpenRouter client not available")
            actual_model = model.removeprefix("openrouter/")
            create_kwargs: Dict[str, Any] = {
                "model": actual_model,
                "messages": messages_to_dicts(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
                **kwargs,
            }
        elif _is_atlascloud_model(model):
            client = self._atlascloud_client
            if client is None:
                raise EngineConnectionError("Atlas Cloud client not available")
            create_kwargs = {
                "model": model.removeprefix("atlascloud/"),
                "messages": messages_to_dicts(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
                **kwargs,
            }
        elif _is_minimax_model(model):
            client = self._minimax_client
            if client is None:
                raise EngineConnectionError("MiniMax client not available")
            temperature = max(temperature, 0.01)
            temperature = min(temperature, 1.0)
            create_kwargs = {
                "model": model,
                "messages": messages_to_dicts(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
                **kwargs,
            }
        elif _is_kimi_model(model):
            client = self._kimi_client
            if client is None:
                raise EngineConnectionError("Kimi client not available")
            create_kwargs = {
                "model": model,
                "messages": messages_to_dicts(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
                **kwargs,
            }
        elif _is_deepseek_model(model):
            client = self._deepseek_client
            if client is None:
                raise EngineConnectionError("DeepSeek client not available")
            create_kwargs = {
                "model": model,
                "messages": messages_to_dicts(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
                **kwargs,
            }
        else:
            client = self._openai_client
            if client is None:
                raise EngineConnectionError("OpenAI client not available")
            create_kwargs = {
                "model": model,
                "messages": messages_to_dicts(messages),
                "max_completion_tokens": max_tokens,
                "stream": True,
                **kwargs,
            }
            if not _is_openai_reasoning_model(model):
                create_kwargs["temperature"] = temperature
        resp = _chat_completion_with_temperature_retry(client, create_kwargs)
        for chunk in resp:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue
            delta = choice.delta
            content = delta.content if delta else None
            tool_calls = None
            if delta and delta.tool_calls:
                tool_calls = [
                    {
                        "index": tc.index,
                        "id": tc.id or "",
                        "function": {
                            "name": (tc.function.name or "") if tc.function else "",
                            "arguments": (
                                (tc.function.arguments or "") if tc.function else ""
                            ),
                        },
                    }
                    for tc in delta.tool_calls
                ]
            finish = choice.finish_reason
            if content or tool_calls or finish:
                yield StreamChunk(
                    content=content,
                    tool_calls=tool_calls,
                    finish_reason=finish,
                )

    async def stream_full(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Yield StreamChunks with content, tool_calls, and finish_reason."""
        kw = dict(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        if _is_anthropic_model(model):
            async for chunk in self._stream_full_anthropic(messages, **kw):
                yield chunk
        elif _is_google_model(model):
            async for chunk in self._stream_full_google(messages, **kw):
                yield chunk
        else:
            async for chunk in self._stream_full_openai(messages, **kw):
                yield chunk

    def list_models(self) -> List[str]:
        models: List[str] = []
        if self._openai_client is not None:
            models.extend(_OPENAI_MODELS)
        if self._anthropic_client is not None:
            models.extend(_ANTHROPIC_MODELS)
        if self._google_client is not None:
            models.extend(_GOOGLE_MODELS)
        if self._openrouter_client is not None:
            models.extend(_OPENROUTER_POPULAR)
        if self._atlascloud_client is not None:
            models.extend(_ATLASCLOUD_POPULAR)
        if self._minimax_client is not None:
            models.extend(_MINIMAX_MODELS)
        if self._deepseek_client is not None:
            models.extend(_DEEPSEEK_MODELS)
        if self._kimi_client is not None:
            models.extend(self._kimi_models())
        if self._codex_client is not None:
            models.extend(_CODEX_MODELS)
        return models

    def _client_for_model(self, model: str) -> Any:
        """Return the provider client ``generate``/``stream`` will dispatch to
        for *model*, or ``None`` for a model this engine cannot route.

        Mirrors the routing in ``generate``/``stream``, but is intentionally
        *stricter* on the OpenAI fall-through: only genuine OpenAI models map to
        the OpenAI client. Unrecognized names (e.g. a local Ollama model like
        ``qwen3.5:0.8b``) return ``None`` so ``can_serve`` declines them and the
        cloud engine is not mis-selected as a fallback when the local engine is
        transiently down and any (even dummy) ``OPENAI_API_KEY`` is set (#335).
        ``generate``/``stream`` keep their OpenAI fall-through, so an
        explicitly-requested unknown cloud model still fails loudly at call time.
        """
        if _is_codex_model(model):
            return self._codex_client
        if _is_openrouter_model(model):
            return self._openrouter_client
        if _is_atlascloud_model(model):
            return self._atlascloud_client
        if _is_minimax_model(model):
            return self._minimax_client
        if _is_kimi_model(model):
            return self._kimi_client
        if _is_deepseek_model(model):
            return self._deepseek_client
        if _is_anthropic_model(model):
            return self._anthropic_client
        if _is_google_model(model):
            return self._google_client
        if _is_openai_model(model):
            return self._openai_client
        return None

    def can_serve(self, model: str) -> bool:
        """Return ``True`` only if the provider client for *model* exists.

        ``health()`` is ``True`` whenever *any* provider client is configured,
        but a request for, say, a ``gpt-*`` model still needs the OpenAI
        client specifically. Without this check the cloud engine gets picked
        as a fallback (when the local engine is down) for a model it can't
        serve, then dies at call time with "<provider> client not available"
        instead of the user getting a helpful "start your local engine"
        message (see #532).
        """
        return self._client_for_model(model) is not None

    def health(self) -> bool:
        return (
            self._openai_client is not None
            or self._anthropic_client is not None
            or self._google_client is not None
            or self._openrouter_client is not None
            or self._atlascloud_client is not None
            or self._minimax_client is not None
            or self._deepseek_client is not None
            or self._kimi_client is not None
            or self._codex_client is not None
        )

    def close(self) -> None:
        if self._openai_client is not None:
            if hasattr(self._openai_client, "close"):
                self._openai_client.close()
            self._openai_client = None
        if self._anthropic_client is not None:
            if hasattr(self._anthropic_client, "close"):
                self._anthropic_client.close()
            self._anthropic_client = None
        if self._google_client is not None:
            self._google_client = None
        if self._openrouter_client is not None:
            if hasattr(self._openrouter_client, "close"):
                self._openrouter_client.close()
            self._openrouter_client = None
        if self._atlascloud_client is not None:
            if hasattr(self._atlascloud_client, "close"):
                self._atlascloud_client.close()
            self._atlascloud_client = None
        if self._minimax_client is not None:
            if hasattr(self._minimax_client, "close"):
                self._minimax_client.close()
            self._minimax_client = None
        # The DeepSeek client was never released here, so its httpx pool
        # outlived close() (every other provider client is dropped).
        if self._deepseek_client is not None:
            if hasattr(self._deepseek_client, "close"):
                self._deepseek_client.close()
            self._deepseek_client = None
        if self._kimi_client is not None:
            if hasattr(self._kimi_client, "close"):
                self._kimi_client.close()
            self._kimi_client = None
        if self._codex_client is not None:
            self._codex_client = None


__all__ = ["CloudEngine", "PRICING", "_annotate_anthropic_cache", "estimate_cost"]

"""OpenAI-compatible cloud providers for :class:`~openjarvis.engine.cloud.CloudEngine`:
OpenRouter, AtlasCloud, MiniMax, Kimi (Moonshot) and DeepSeek.

Split out of ``cloud.py`` to keep it readable. Module-level helpers are
looked up on ``openjarvis.engine.cloud`` at call time, so behaviour (and
anything patched there) is unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Dict, List

import openjarvis.engine.cloud as _cloud
from openjarvis.core.types import Message


class CompatProvidersMixin:
    def _generate_openrouter(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self._openrouter_client is None:
            raise _cloud.EngineConnectionError(
                "OpenRouter client not available — set OPENROUTER_API_KEY"
            )
        # Strip the "openrouter/" prefix to get the actual model ID
        actual_model = model.removeprefix("openrouter/")
        kwargs.pop("response_format", None)
        create_kwargs: Dict[str, Any] = {
            "model": actual_model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        # Forward tools / tool_choice (OpenRouter is OpenAI-compatible).
        tools = kwargs.pop("tools", None)
        if tools:
            create_kwargs["tools"] = tools
        tool_choice = kwargs.pop("tool_choice", None)
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice
        t0 = _cloud.time.monotonic()
        resp = _cloud._chat_completion_with_temperature_retry(
            self._openrouter_client, create_kwargs
        )
        elapsed = _cloud.time.monotonic() - t0
        choice = _cloud._first_choice_or_raise(
            resp, provider="OpenRouter", model=actual_model
        )
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        result: Dict[str, Any] = {
            "content": choice.message.content or "",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": (usage.total_tokens if usage else 0),
            },
            "model": resp.model,
            "finish_reason": choice.finish_reason or "stop",
            "ttft": elapsed,
        }
        if getattr(choice.message, "tool_calls", None):
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]
        return result

    def _generate_atlascloud(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self._atlascloud_client is None:
            raise _cloud.EngineConnectionError(
                "Atlas Cloud client not available — set ATLASCLOUD_API_KEY"
            )
        # Strip the "atlascloud/" prefix to get the gateway's own model ID.
        actual_model = model.removeprefix("atlascloud/")
        create_kwargs: Dict[str, Any] = {
            "model": actual_model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        # Atlas Cloud is OpenAI-compatible: response_format, tools and
        # tool_choice all pass straight through.
        response_format = kwargs.pop("response_format", None)
        if response_format is not None:
            create_kwargs["response_format"] = response_format
        tools = kwargs.pop("tools", None)
        if tools:
            create_kwargs["tools"] = tools
        tool_choice = kwargs.pop("tool_choice", None)
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice
        t0 = _cloud.time.monotonic()
        resp = _cloud._chat_completion_with_temperature_retry(
            self._atlascloud_client, create_kwargs
        )
        elapsed = _cloud.time.monotonic() - t0
        choice = _cloud._first_choice_or_raise(
            resp, provider="Atlas Cloud", model=actual_model
        )
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        result: Dict[str, Any] = {
            "content": choice.message.content or "",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": (usage.total_tokens if usage else 0),
            },
            "model": resp.model,
            "finish_reason": choice.finish_reason or "stop",
            # Cost is keyed on the prefixed ID so PRICING stays unambiguous
            # between "atlascloud/minimaxai/minimax-m2.5" and MiniMax direct.
            "cost_usd": _cloud.estimate_cost(model, prompt_tokens, completion_tokens),
            "ttft": elapsed,
        }
        if getattr(choice.message, "tool_calls", None):
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]
        return result

    def _generate_minimax(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self._minimax_client is None:
            raise _cloud.EngineConnectionError(
                "MiniMax client not available — set MINIMAX_API_KEY"
            )
        # MiniMax requires temperature in (0.0, 1.0]; clamp zero
        temperature = max(temperature, 0.01)
        temperature = min(temperature, 1.0)
        kwargs.pop("response_format", None)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        t0 = _cloud.time.monotonic()
        resp = _cloud._chat_completion_with_temperature_retry(
            self._minimax_client, create_kwargs
        )
        elapsed = _cloud.time.monotonic() - t0
        choice = _cloud._first_choice_or_raise(resp, provider="MiniMax", model=model)
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        result: Dict[str, Any] = {
            "content": choice.message.content or "",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": (usage.total_tokens if usage else 0),
            },
            "model": resp.model,
            "finish_reason": choice.finish_reason or "stop",
            "cost_usd": _cloud.estimate_cost(model, prompt_tokens, completion_tokens),
            "ttft": elapsed,
        }
        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in choice.message.tool_calls
            ]
        return result

    def _generate_kimi(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self._kimi_client is None:
            raise _cloud.EngineConnectionError(
                "Kimi client not available — set MOONSHOT_API_KEY"
            )
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            **{
                k: kwargs[k]
                for k in _cloud._KIMI_PASSTHROUGH
                if kwargs.get(k) is not None
            },
        }
        t0 = _cloud.time.monotonic()
        resp = _cloud._kimi_create(self._kimi_client, create_kwargs)
        elapsed = _cloud.time.monotonic() - t0
        choice = _cloud._first_choice_or_raise(resp, provider="Kimi", model=model)
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        result: Dict[str, Any] = {
            "content": choice.message.content or "",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": (usage.total_tokens if usage else 0),
            },
            "model": resp.model,
            "finish_reason": choice.finish_reason or "stop",
            "cost_usd": _cloud.estimate_cost(model, prompt_tokens, completion_tokens),
            "ttft": elapsed,
        }
        if getattr(choice.message, "tool_calls", None):
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in choice.message.tool_calls
            ]
        return result

    async def _stream_kimi(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._kimi_client is None:
            raise _cloud.EngineConnectionError("Kimi client not available")
        resp = _cloud._kimi_create(
            self._kimi_client,
            {
                "model": model,
                "messages": _cloud.messages_to_dicts(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            },
        )
        for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    def _generate_deepseek(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self._deepseek_client is None:
            raise _cloud.EngineConnectionError(
                "DeepSeek client not available — set DEEPSEEK_API_KEY"
            )
        kwargs.pop("response_format", None)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        t0 = _cloud.time.monotonic()
        resp = _cloud._chat_completion_with_temperature_retry(
            self._deepseek_client, create_kwargs
        )
        elapsed = _cloud.time.monotonic() - t0
        choice = _cloud._first_choice_or_raise(resp, provider="DeepSeek", model=model)
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        result: Dict[str, Any] = {
            "content": choice.message.content or "",
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": (usage.total_tokens if usage else 0),
            },
            "model": resp.model,
            "finish_reason": choice.finish_reason or "stop",
            "cost_usd": _cloud.estimate_cost(model, prompt_tokens, completion_tokens),
            "ttft": elapsed,
        }
        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in choice.message.tool_calls
            ]
        return result

    async def _stream_openrouter(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._openrouter_client is None:
            raise _cloud.EngineConnectionError("OpenRouter client not available")
        actual_model = model.removeprefix("openrouter/")
        create_kwargs: Dict[str, Any] = {
            "model": actual_model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        # Forward tools / tool_choice (OpenRouter is OpenAI-compatible).
        tools = kwargs.pop("tools", None)
        if tools:
            create_kwargs["tools"] = tools
        tool_choice = kwargs.pop("tool_choice", None)
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice
        resp = _cloud._chat_completion_with_temperature_retry(
            self._openrouter_client, create_kwargs
        )
        for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def _stream_atlascloud(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._atlascloud_client is None:
            raise _cloud.EngineConnectionError("Atlas Cloud client not available")
        actual_model = model.removeprefix("atlascloud/")
        create_kwargs: Dict[str, Any] = {
            "model": actual_model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        # Forward tools / tool_choice (Atlas Cloud is OpenAI-compatible).
        tools = kwargs.pop("tools", None)
        if tools:
            create_kwargs["tools"] = tools
        tool_choice = kwargs.pop("tool_choice", None)
        if tool_choice is not None:
            create_kwargs["tool_choice"] = tool_choice
        resp = _cloud._chat_completion_with_temperature_retry(
            self._atlascloud_client, create_kwargs
        )
        for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def _stream_minimax(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._minimax_client is None:
            raise _cloud.EngineConnectionError("MiniMax client not available")
        temperature = max(temperature, 0.01)
        temperature = min(temperature, 1.0)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        resp = _cloud._chat_completion_with_temperature_retry(
            self._minimax_client, create_kwargs
        )
        for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def _stream_deepseek(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._deepseek_client is None:
            raise _cloud.EngineConnectionError("DeepSeek client not available")
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        resp = _cloud._chat_completion_with_temperature_retry(
            self._deepseek_client, create_kwargs
        )
        for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    def _kimi_models(self) -> List[str]:
        """Kimi's live model list (cached), falling back to the known ids."""
        if self._kimi_live_models is None:
            try:
                listed = [m.id for m in self._kimi_client.models.list().data]
                self._kimi_live_models = [m for m in listed if _cloud._is_kimi_model(m)]
            except Exception:  # noqa: BLE001 — offline, bad key, old SDK
                self._kimi_live_models = []
        return self._kimi_live_models or list(_cloud._KIMI_MODELS)


__all__ = ["CompatProvidersMixin"]

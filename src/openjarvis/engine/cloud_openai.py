"""OpenAI calls for :class:`~openjarvis.engine.cloud.CloudEngine`: Chat
Completions (generate, stream) and the Codex
Responses endpoint.

Split out of ``cloud.py``; module-level helpers (and ``httpx``) are looked
up on ``openjarvis.engine.cloud`` at call time, so behaviour and anything
patched there are unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Dict, List

import openjarvis.engine.cloud as _cloud
from openjarvis.core.types import Message


class OpenAIMixin:
    @staticmethod
    def _codex_build_input(
        messages: Sequence[Message],
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Convert Message list to Codex Responses API format.

        Returns (system_instructions, input_messages).
        """
        instructions = ""
        input_msgs: List[Dict[str, Any]] = []
        for m in messages:
            if m.role.value == "system":
                instructions = m.content
            elif m.role.value in ("user", "assistant"):
                input_msgs.append(
                    {
                        "role": m.role.value,
                        "content": [{"type": "input_text", "text": m.content}],
                    }
                )
        return instructions, input_msgs

    def _generate_codex(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate via Codex Responses API (ChatGPT Plus/Pro)."""
        if self._codex_client is None:
            raise _cloud.EngineConnectionError(
                "Codex client not available — set OPENAI_CODEX_API_KEY"
            )
        actual_model = model.removeprefix("codex/")
        instructions, input_msgs = self._codex_build_input(messages)

        body: Dict[str, Any] = {
            "model": actual_model,
            "input": input_msgs,
            "store": False,
            "stream": False,
        }
        if instructions:
            body["instructions"] = instructions

        headers = {
            "Authorization": f"Bearer {self._codex_client['token']}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "responses=experimental",
        }

        t0 = _cloud.time.monotonic()
        resp = _cloud.httpx.post(
            self._codex_client["url"],
            json=body,
            headers=headers,
            timeout=120.0,
        )
        elapsed = _cloud.time.monotonic() - t0
        resp.raise_for_status()
        data = resp.json()

        # Extract text from Responses API output.
        # The output array contains items of type "reasoning" and "message";
        # we want the "message" item's content blocks.
        content = data.get("output_text", "")
        if not content:
            for item in data.get("output", []):
                if item.get("type") not in ("message", None):
                    continue
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        content = block.get("text", "")
                        break
                if content:
                    break

        usage_data = data.get("usage", {})
        prompt_tokens = usage_data.get("input_tokens", 0)
        completion_tokens = usage_data.get("output_tokens", 0)

        return {
            "content": content,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "model": actual_model,
            "finish_reason": "stop",
            "cost_usd": 0.0,
            "ttft": elapsed,
        }

    async def _stream_codex(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream via Codex Responses API (SSE)."""
        if self._codex_client is None:
            raise _cloud.EngineConnectionError("Codex client not available")
        actual_model = model.removeprefix("codex/")
        instructions, input_msgs = self._codex_build_input(messages)

        body: Dict[str, Any] = {
            "model": actual_model,
            "input": input_msgs,
            "store": False,
            "stream": True,
        }
        if instructions:
            body["instructions"] = instructions

        headers = {
            "Authorization": f"Bearer {self._codex_client['token']}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "OpenAI-Beta": "responses=experimental",
        }

        async with _cloud.httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                self._codex_client["url"],
                json=body,
                headers=headers,
                timeout=120.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        event = _cloud.json.loads(payload)
                    except (_cloud.json.JSONDecodeError, ValueError):
                        continue
                    etype = event.get("type", "")
                    if etype == "response.output_text.delta":
                        delta = event.get("delta", "")
                        if delta:
                            yield delta

    def _generate_openai(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self._openai_client is None:
            raise _cloud.EngineConnectionError(
                "OpenAI client not available — set "
                "OPENAI_API_KEY and install "
                "openjarvis[inference-cloud]"
            )
        # Extract response_format before spreading kwargs into create_kwargs
        response_format = kwargs.pop("response_format", None)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_completion_tokens": max_tokens,
            **kwargs,
        }
        if not _cloud._is_openai_reasoning_model(model):
            create_kwargs["temperature"] = temperature

        # Apply structured output / JSON mode
        if response_format is not None:
            from openjarvis.engine._stubs import ResponseFormat

            if isinstance(response_format, ResponseFormat):
                if response_format.type == "json_schema" and response_format.schema:
                    create_kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "response",
                            "schema": response_format.schema,
                        },
                    }
                else:
                    create_kwargs["response_format"] = {"type": "json_object"}
            else:
                # Raw dict pass-through for backward compatibility
                create_kwargs["response_format"] = response_format

        t0 = _cloud.time.monotonic()
        resp = _cloud._chat_completion_with_temperature_retry(
            self._openai_client, create_kwargs
        )
        elapsed = _cloud.time.monotonic() - t0
        choice = _cloud._first_choice_or_raise(resp, provider="OpenAI", model=model)
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        result = {
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

        # Extract tool_calls if present
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

    async def _stream_openai(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._openai_client is None:
            raise _cloud.EngineConnectionError("OpenAI client not available")
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": _cloud.messages_to_dicts(messages),
            "max_completion_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        if not _cloud._is_openai_reasoning_model(model):
            create_kwargs["temperature"] = temperature
        resp = _cloud._chat_completion_with_temperature_retry(
            self._openai_client, create_kwargs
        )
        for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


__all__ = ["OpenAIMixin"]

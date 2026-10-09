"""Google Gemini calls for :class:`~openjarvis.engine.cloud.CloudEngine`:
generate with quota fallback across model families, stream and full
stream with tool calls and thought signatures.

Split out of ``cloud.py``; module-level helpers (and ``genai_types``) are
looked up on ``openjarvis.engine.cloud`` at call time, so behaviour and
anything patched there are unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Dict, List

import openjarvis.engine.cloud as _cloud
from openjarvis.core.types import Message
from openjarvis.engine._stubs import StreamChunk


class GoogleMixin:
    def _generate_google(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self._google_client is None:
            raise _cloud.EngineConnectionError(
                "Google client not available — set "
                "GEMINI_API_KEY or GOOGLE_API_KEY and install "
                "openjarvis[inference-google]"
            )
        # Build contents from messages, converting tool roles for Gemini
        system_text = ""
        contents: List[Dict[str, Any]] = []
        for m in messages:
            if m.role.value == "system":
                system_text = m.content
            elif m.role.value == "tool":
                # Gemini expects function responses as role="user" with
                # function_response parts
                fn_resp_part = {
                    "function_response": {
                        "name": m.name or "unknown",
                        "response": {"result": m.content},
                    }
                }
                # Merge consecutive tool results into a single user message
                if (
                    contents
                    and contents[-1]["role"] == "user"
                    and contents[-1]["parts"]
                    and "function_response" in contents[-1]["parts"][-1]
                ):
                    contents[-1]["parts"].append(fn_resp_part)
                else:
                    contents.append({"role": "user", "parts": [fn_resp_part]})
            elif m.role.value == "assistant" and m.tool_calls:
                # Convert assistant tool_calls to function_call parts
                parts: List[Dict[str, Any]] = []
                if m.content:
                    parts.append({"text": m.content})
                for tc in m.tool_calls:
                    args = tc.arguments
                    if isinstance(args, str):
                        try:
                            args = _cloud.json.loads(args)
                        except (_cloud.json.JSONDecodeError, TypeError):
                            args = {"input": args}
                    fc_part: Dict[str, Any] = {
                        "function_call": {
                            "name": tc.name,
                            "args": args if isinstance(args, dict) else {},
                        }
                    }
                    # Replay thought_signature for Gemini reasoning models
                    # (a call without one -- another model wrote it, or it
                    # was lost -- gets Google's documented placeholder,
                    # otherwise Gemini 3 refuses the whole request)
                    sig = self._thought_sigs.get(tc.id)
                    fc_part["thought_signature"] = (
                        sig if sig is not None else _cloud.SKIP_SIGNATURE
                    )
                    parts.append(fc_part)
                contents.append({"role": "model", "parts": parts})
            elif m.role.value == "assistant":
                contents.append({"role": "model", "parts": [{"text": m.content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": m.content}]})

        from google.genai import types as genai_types

        model, effort = _cloud.split_effort(model)
        config = genai_types.GenerateContentConfig(
            **_cloud.google_config_kwargs(model, temperature, max_tokens, effort)
        )
        if system_text:
            config.system_instruction = system_text

        # Convert and pass tools in Google format
        raw_tools = kwargs.pop("tools", None)
        if raw_tools:
            declarations = _cloud._convert_tools_to_google(raw_tools)
            config.tools = [{"function_declarations": declarations}]

        # Apply structured output / JSON mode for Google
        response_format = kwargs.pop("response_format", None)
        if response_format is not None:
            from openjarvis.engine._stubs import ResponseFormat

            if isinstance(response_format, ResponseFormat):
                config.response_mime_type = "application/json"
                if response_format.schema:
                    config.response_schema = response_format.schema

        t0 = _cloud.time.monotonic()
        resp, model = self._google_with_fallback(
            model, contents, config, effort, temperature, max_tokens
        )
        elapsed = _cloud.time.monotonic() - t0

        # Extract text and function_call parts from response
        text_parts: list[str] = []
        tool_calls: list[Dict[str, Any]] = []
        candidates = getattr(resp, "candidates", None)
        if candidates:
            parts = getattr(candidates[0].content, "parts", [])
            for part in parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    fc_args = dict(fc.args) if hasattr(fc.args, "items") else {}
                    tc_dict: Dict[str, Any] = {
                        "id": f"google_{fc.name}",
                        "name": fc.name,
                        "arguments": _cloud.json.dumps(fc_args),
                    }
                    # Preserve thought_signature for Gemini reasoning models
                    # (kept on the side: bytes in the result broke JSON
                    # replies and traces with "bytes is not JSON serializable")
                    sig = getattr(part, "thought_signature", None)
                    if sig is not None:
                        self._thought_sigs[tc_dict["id"]] = sig
                    tool_calls.append(tc_dict)
                elif hasattr(part, "text") and part.text:
                    text_parts.append(part.text)

        # Guard against resp.text ValueError when only function_call parts
        if text_parts:
            content = "\n".join(text_parts)
        else:
            try:
                content = resp.text or ""
            except (ValueError, AttributeError):
                content = ""

        um = resp.usage_metadata
        prompt_tokens = getattr(um, "prompt_token_count", 0) if um else 0
        completion_tokens = getattr(um, "candidates_token_count", 0) if um else 0

        result: Dict[str, Any] = {
            "content": content,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "model": model,
            "finish_reason": "stop",
            "cost_usd": _cloud.estimate_cost(model, prompt_tokens, completion_tokens),
            "ttft": elapsed,
        }

        if tool_calls:
            result["tool_calls"] = tool_calls

        return result

    def _google_with_fallback(
        self,
        model: str,
        contents: List[Dict[str, Any]],
        config: Any,
        effort: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[Any, str]:
        """generate_content, moving to a sibling model when one is out of quota.

        Free Gemini keys have a small daily quota *per model*; when the chosen
        one runs out (429 RESOURCE_EXHAUSTED) Sergio keeps working with the
        next Gemini of the same family instead of going silent.
        """
        candidates = [model, *_cloud.quota_fallbacks(model)]
        fresh = [c for c in candidates if not _cloud._exhausted(c)] or candidates
        last: Exception | None = None
        for candidate in fresh:
            if candidate != model:
                from google.genai import types as genai_types

                config = genai_types.GenerateContentConfig(
                    **_cloud.google_config_kwargs(
                        candidate, temperature, max_tokens, effort
                    ),
                    system_instruction=config.system_instruction,
                    tools=config.tools,
                    response_mime_type=config.response_mime_type,
                    response_schema=config.response_schema,
                )
                # Thought signatures belong to the model that wrote them; the
                # new model gets the placeholder on its function calls.
                contents = [
                    {
                        **c,
                        "parts": [
                            {k: v for k, v in part.items() if k != "thought_signature"}
                            | (
                                {"thought_signature": _cloud.SKIP_SIGNATURE}
                                if "function_call" in part
                                else {}
                            )
                            for part in c["parts"]
                        ],
                    }
                    for c in contents
                ]
            try:
                resp = self._google_client.models.generate_content(
                    model=candidate, contents=contents, config=config
                )
            except Exception as exc:  # noqa: BLE001
                if _cloud._is_quota_error(exc):
                    cooldown = _cloud.QUOTA_COOLDOWN
                elif _cloud._is_busy_error(exc):
                    cooldown = _cloud.BUSY_COOLDOWN
                else:
                    raise
                _cloud._QUOTA_EXHAUSTED[candidate] = _cloud.time.monotonic() + cooldown
                last = exc
                # Expected with free-tier quotas: the next model answers instead.
                _cloud.logger.info(
                    "Gemini %s unavailable (%s); trying the next",
                    candidate,
                    str(exc)[:80],
                )
                continue
            return resp, candidate
        raise last if last is not None else RuntimeError("no Gemini model")

    async def _stream_google(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._google_client is None:
            raise _cloud.EngineConnectionError("Google client not available")
        system_text = ""
        contents: List[Dict[str, Any]] = []
        for m in messages:
            if m.role.value == "system":
                system_text = m.content
            elif m.role.value == "assistant":
                contents.append({"role": "model", "parts": [{"text": m.content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": m.content}]})

        from google.genai import types as genai_types

        model, effort = _cloud.split_effort(model)
        config = genai_types.GenerateContentConfig(
            **_cloud.google_config_kwargs(model, temperature, max_tokens, effort)
        )
        if system_text:
            config.system_instruction = system_text

        for chunk in self._google_client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        ):
            if chunk.text:
                yield chunk.text

    async def _stream_full_google(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream Google text and function-call parts as full chunks."""
        if self._google_client is None:
            raise _cloud.EngineConnectionError("Google client not available")

        system_text = ""
        contents: List[Dict[str, Any]] = []
        for message in messages:
            if message.role.value == "system":
                system_text = message.content
            elif message.role.value == "tool":
                function_response = {
                    "function_response": {
                        "name": message.name or "unknown",
                        "response": {"result": message.content},
                    }
                }
                if (
                    contents
                    and contents[-1]["role"] == "user"
                    and contents[-1]["parts"]
                    and "function_response" in contents[-1]["parts"][-1]
                ):
                    contents[-1]["parts"].append(function_response)
                else:
                    contents.append({"role": "user", "parts": [function_response]})
            elif message.role.value == "assistant" and message.tool_calls:
                parts: List[Dict[str, Any]] = []
                if message.content:
                    parts.append({"text": message.content})
                for tool_call in message.tool_calls:
                    args = tool_call.arguments
                    if isinstance(args, str):
                        try:
                            args = _cloud.json.loads(args)
                        except (_cloud.json.JSONDecodeError, TypeError):
                            args = {"input": args}
                    function_call_part: Dict[str, Any] = {
                        "function_call": {
                            "name": tool_call.name,
                            "args": args if isinstance(args, dict) else {},
                        }
                    }
                    signature = self._thought_sigs.get(tool_call.id)
                    function_call_part["thought_signature"] = (
                        signature if signature is not None else _cloud.SKIP_SIGNATURE
                    )
                    parts.append(function_call_part)
                contents.append({"role": "model", "parts": parts})
            elif message.role.value == "assistant":
                contents.append({"role": "model", "parts": [{"text": message.content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": message.content}]})

        from google.genai import types as genai_types

        model, effort = _cloud.split_effort(model)
        config = genai_types.GenerateContentConfig(
            **_cloud.google_config_kwargs(model, temperature, max_tokens, effort)
        )
        if system_text:
            config.system_instruction = system_text

        tools = kwargs.pop("tools", None)
        if tools:
            config.tools = [
                {"function_declarations": _cloud._convert_tools_to_google(tools)}
            ]

        tool_call_count = 0
        stream_id = _cloud.uuid.uuid4().hex
        final_usage: Dict[str, Any] | None = None
        for chunk in self._google_client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        ):
            usage_metadata = getattr(chunk, "usage_metadata", None)
            if usage_metadata is not None:
                prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0) or 0
                completion_tokens = (
                    getattr(usage_metadata, "candidates_token_count", 0) or 0
                )
                final_usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                }

            candidates = getattr(chunk, "candidates", None)
            parts = []
            if candidates:
                parts = getattr(candidates[0].content, "parts", []) or []

            if parts:
                text_found = False
                calls: List[Dict[str, Any]] = []
                for part in parts:
                    text = getattr(part, "text", None)
                    if text:
                        text_found = True
                        yield _cloud.StreamChunk(content=text)

                    function_call = getattr(part, "function_call", None)
                    if function_call:
                        name = getattr(function_call, "name", "")
                        raw_args = getattr(function_call, "args", {})
                        args = dict(raw_args) if hasattr(raw_args, "items") else {}
                        # Gemini emits complete function-call parts, so each part is
                        # a distinct invocation. The same function may legitimately
                        # be called more than once in a parallel response.
                        tool_index = tool_call_count
                        # The engine is shared across server requests, and saved
                        # thought signatures are keyed by tool-call ID. Include a
                        # per-stream nonce so concurrent conversations cannot
                        # overwrite each other's signatures.
                        tool_id = f"google_{stream_id}_{tool_index}"
                        tool_call_count += 1
                        tool_call = {
                            "index": tool_index,
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": _cloud.json.dumps(args),
                            },
                        }
                        calls.append(tool_call)
                        signature = getattr(part, "thought_signature", None)
                        if signature is not None:  # kept on the side (not JSON)
                            self._thought_sigs[tool_id] = signature
                if calls:
                    yield _cloud.StreamChunk(tool_calls=calls)
                if text_found:
                    continue

            try:
                text = chunk.text
            except (AttributeError, ValueError):
                text = None
            if text:
                yield _cloud.StreamChunk(content=text)

        yield _cloud.StreamChunk(
            finish_reason="tool_calls" if tool_call_count else "stop",
            usage=final_usage,
        )


__all__ = ["GoogleMixin"]

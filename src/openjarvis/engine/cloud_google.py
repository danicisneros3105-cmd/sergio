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
from openjarvis.engine.model_health import health


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
        fresh = self._google_stream_candidates(model)
        primary_contents, primary_config = contents, config

        def request_for(candidate: str) -> tuple[List[Dict[str, Any]], Any]:
            if candidate == model:
                return primary_contents, primary_config
            from google.genai import types as genai_types

            cfg = genai_types.GenerateContentConfig(
                **_cloud.google_config_kwargs(
                    candidate, temperature, max_tokens, effort
                ),
                system_instruction=primary_config.system_instruction,
                tools=primary_config.tools,
                response_mime_type=primary_config.response_mime_type,
                response_schema=primary_config.response_schema,
            )
            # Thought signatures belong to the model that wrote them; the
            # new model gets the placeholder on its function calls.
            cts = [
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
                for c in primary_contents
            ]
            return cts, cfg

        class _Fatal:
            def __init__(self, exc: Exception) -> None:
                self.exc = exc

        def attempt(index: int, candidate: str) -> Any:
            def run() -> Any:
                cts, cfg = request_for(candidate)
                t0 = _cloud.time.monotonic()
                try:
                    resp = self._google_client.models.generate_content(
                        model=candidate, contents=cts, config=cfg
                    )
                    health().ok(candidate, _cloud.time.monotonic() - t0)
                    return resp
                except Exception as exc:  # noqa: BLE001
                    if _cloud._is_quota_error(exc) or _cloud._is_model_not_found_error(
                        exc
                    ):
                        cooldown = _cloud.QUOTA_COOLDOWN
                    elif _cloud._is_busy_error(exc):
                        cooldown = _cloud.BUSY_COOLDOWN
                        health().failed(candidate, _cloud.time.monotonic() - t0)
                    elif index == 0:
                        return _Fatal(exc)  # a bad request: no sibling fixes it
                    else:
                        raise
                    _cloud._QUOTA_EXHAUSTED[candidate] = (
                        _cloud.time.monotonic() + cooldown
                    )
                    # Expected with free-tier quotas or preview model tiers: the next model answers.
                    _cloud.logger.info(
                        "Gemini %s unavailable (%s); trying the next",
                        candidate,
                        str(exc)[:80],
                    )
                    raise

            return run

        # Hedged: when Google is busy a model may take minutes; after
        # HEDGE_AFTER s the next sibling starts too and the first answer wins.
        from openjarvis.engine.hedge import HedgeError, first_valid

        started = _cloud.time.monotonic()
        try:
            index, resp = first_valid(
                [attempt(i, c) for i, c in enumerate(fresh)],
                names=fresh,
                hedge_after=health().hedge_after(fresh[0], _cloud.HEDGE_AFTER),
                timeout=_cloud.HEDGE_TIMEOUT,
            )
        except HedgeError as exc:
            raise RuntimeError(
                "Gemini no respondió: " + " | ".join(exc.errors[-3:])
            ) from exc
        if isinstance(resp, _Fatal):
            raise resp.exc
        waited = _cloud.time.monotonic() - started
        for slower in fresh[:index]:  # overtaken while still thinking: slow
            if not health().resting(slower):
                health().failed(slower, waited)
        return resp, fresh[index]

    def _google_stream_candidates(self, model: str) -> List[str]:
        """The chosen model and its siblings: out-of-quota ones left out,
        the ones answering fast lately first (``model_health``)."""
        candidates = [model, *_cloud.quota_fallbacks(model)]
        fresh = [c for c in candidates if not _cloud._exhausted(c)] or candidates
        return health().order(fresh)

    def _hedged_google_stream(
        self, candidates: List[str], request: Any
    ) -> AsyncIterator[tuple[str, Any]]:
        """Stream from the first candidate that starts answering.

        Every SDK stream runs on its own thread (it blocks), so a slow model
        never freezes the server; when the current one has said nothing after
        ``STREAM_HEDGE_AFTER`` s (less for a model that is usually quick) the
        next sibling starts as well and the first to speak wins.
        """
        from openjarvis.engine.hedge import HedgeError, first_stream

        def start(candidate: str) -> Any:
            return lambda: self._google_client.models.generate_content_stream(
                model=candidate, **request(candidate)
            )

        def on_error(index: int, exc: BaseException, seconds: float) -> None:
            candidate = candidates[index]
            if _cloud._is_quota_error(exc) or _cloud._is_model_not_found_error(exc):
                _cloud._QUOTA_EXHAUSTED[candidate] = (
                    _cloud.time.monotonic() + _cloud.QUOTA_COOLDOWN
                )
            elif _cloud._is_busy_error(exc):
                _cloud._QUOTA_EXHAUSTED[candidate] = (
                    _cloud.time.monotonic() + _cloud.BUSY_COOLDOWN
                )
                health().failed(candidate, seconds)
            _cloud.logger.info(
                "Gemini stream %s unavailable (%s); trying the next",
                candidate,
                str(exc)[:80],
            )

        def retryable(index: int, exc: BaseException) -> bool:
            if index > 0:
                return True
            return (
                _cloud._is_quota_error(exc)
                or _cloud._is_model_not_found_error(exc)
                or _cloud._is_busy_error(exc)
            )

        async def run() -> AsyncIterator[tuple[str, Any]]:
            try:
                async for index, chunk in first_stream(
                    [start(c) for c in candidates],
                    names=candidates,
                    hedge_after=lambda i: health().hedge_after(
                        candidates[i], _cloud.STREAM_HEDGE_AFTER
                    ),
                    first_timeout=_cloud.HEDGE_TIMEOUT,
                    retryable=retryable,
                    on_first=lambda i, sec: health().ok(candidates[i], sec),
                    on_error=on_error,
                    on_slow=lambda i, sec: health().failed(candidates[i], sec),
                ):
                    yield candidates[index], chunk
            except HedgeError as exc:
                raise RuntimeError(
                    "Gemini no respondió: " + " | ".join(exc.errors[-3:])
                ) from exc

        return run()

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

        def request(candidate: str) -> Dict[str, Any]:
            config = genai_types.GenerateContentConfig(
                **_cloud.google_config_kwargs(
                    candidate, temperature, max_tokens, effort
                )
            )
            if system_text:
                config.system_instruction = system_text
            return {"contents": contents, "config": config}

        async for _candidate, chunk in self._hedged_google_stream(
            self._google_stream_candidates(model), request
        ):
            try:
                text = chunk.text
            except (AttributeError, ValueError):
                text = None
            if text:
                yield text

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
        tools = kwargs.pop("tools", None)
        tool_decls = (
            [{"function_declarations": _cloud._convert_tools_to_google(tools)}]
            if tools
            else None
        )

        def request(candidate: str) -> Dict[str, Any]:
            config = genai_types.GenerateContentConfig(
                **_cloud.google_config_kwargs(
                    candidate, temperature, max_tokens, effort
                )
            )
            if system_text:
                config.system_instruction = system_text
            if tool_decls:
                config.tools = tool_decls
            if candidate == model:
                return {"contents": contents, "config": config}
            # Thought signatures belong to the model that wrote them.
            cts = [
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
            return {"contents": cts, "config": config}

        tool_call_count = 0
        stream_id = _cloud.uuid.uuid4().hex
        final_usage: Dict[str, Any] | None = None
        async for _candidate, chunk in self._hedged_google_stream(
            self._google_stream_candidates(model), request
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
                        tool_index = tool_call_count
                        tool_id = f"google_{stream_id}_{tool_index}"
                        tool_call_count += 1
                        calls.append(
                            {
                                "index": tool_index,
                                "id": tool_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": _cloud.json.dumps(args),
                                },
                            }
                        )
                        signature = getattr(part, "thought_signature", None)
                        if signature is not None:
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

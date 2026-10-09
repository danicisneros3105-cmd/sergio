"""Raw SDK calls shared by the hybrid local/cloud agents: Anthropic, OpenAI,
OpenRouter, Gemini and vLLM, plus their server-side tool loops (web
search). Each records into the active per-task trace.

Split out of ``_base.py``; module-level helpers are looked up on that
module at call time, so behaviour (and anything patched there) is
unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import openjarvis.agents.hybrid._base as _hb


class SDKCallsMixin:
    @staticmethod
    def _call_anthropic(
        model: str,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tools: Optional[list] = None,
        tool_choice: Optional[dict] = None,
        output_config: Optional[dict] = None,
        timeout: float = 600.0,
        max_retries: int = 12,
        trace_role: str = "cloud",
    ) -> Tuple[str, int, int, int]:
        """Single Anthropic call. Returns (text, p_tok, c_tok, n_web_searches).

        Strips ``temperature`` for Opus 4.7+ (rejected by the API). Captures
        the call into the active per-task trace if one is open. Bumped
        default max_retries to 12 (~2 min of backoff) so cells survive
        sustained Anthropic 529 "Overloaded" windows when many cells share
        Opus quota.
        """
        import anthropic

        client = anthropic.Anthropic(timeout=timeout, max_retries=max_retries)
        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            kwargs["system"] = system
        if _hb.supports_temperature(model):
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if output_config:
            kwargs["output_config"] = output_config
        t0 = _hb.time.time()
        msg = client.messages.create(**kwargs)
        _hb._bump_cloud_calls()
        latency = _hb.time.time() - t0
        text = "".join(b.text for b in msg.content if hasattr(b, "text"))
        srv = getattr(msg.usage, "server_tool_use", None)
        n_searches = getattr(srv, "web_search_requests", 0) if srv else 0
        content_blocks = [_hb._serialize_block(b) for b in msg.content]
        tool_use_blocks = [
            b
            for b in content_blocks
            if b.get("type")
            in (
                "tool_use",
                "server_tool_use",
            )
        ]
        tool_result_blocks = [
            b
            for b in content_blocks
            if b.get("type")
            in (
                "web_search_tool_result",
                "tool_result",
            )
        ]
        _hb._record_event(
            {
                "kind": "anthropic",
                "role": trace_role,
                "model": model,
                "system": system,
                "user": user,
                "response": text,
                "content_blocks": content_blocks,
                "tool_calls": tool_use_blocks,
                "tool_results": tool_result_blocks,
                "tokens_in": msg.usage.input_tokens,
                "tokens_out": msg.usage.output_tokens,
                "n_web_searches": n_searches,
                "tools_declared": tools,
                "tool_choice": tool_choice,
                "output_config": output_config,
                "stop_reason": getattr(msg, "stop_reason", None),
                "latency_s": latency,
                "ts": _hb.time.time(),
            }
        )
        return text, msg.usage.input_tokens, msg.usage.output_tokens, n_searches

    @staticmethod
    def _call_openai(
        model: str,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[Any] = None,
        timeout: float = 600.0,
        trace_role: str = "cloud",
    ) -> Tuple[str, int, int]:
        """Single OpenAI call. Returns (text, p_tok, c_tok). Trace-captured;
        also records any tool_calls the model emits."""
        from openai import OpenAI

        client = OpenAI(timeout=timeout)
        messages: list = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        kwargs: Dict[str, Any] = {"model": model, "messages": messages}
        if _hb.is_gpt5_family(model):
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = temperature
        if response_format is not None:
            kwargs["response_format"] = response_format
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        t0 = _hb.time.time()
        resp = client.chat.completions.create(**kwargs)
        _hb._bump_cloud_calls()
        latency = _hb.time.time() - t0
        choice = resp.choices[0]
        message = choice.message
        text = message.content or ""
        tool_calls = _hb._serialize_openai_tool_calls(
            getattr(message, "tool_calls", None)
        )
        reasoning = getattr(message, "reasoning_content", None) or getattr(
            message, "reasoning", None
        )
        u = resp.usage
        p = getattr(u, "prompt_tokens", 0) if u else 0
        c = getattr(u, "completion_tokens", 0) if u else 0
        _hb._record_event(
            {
                "kind": "openai",
                "role": trace_role,
                "model": model,
                "system": system,
                "user": user,
                "response": text,
                "tool_calls": tool_calls,
                "reasoning_content": reasoning,
                "tokens_in": p,
                "tokens_out": c,
                "response_format": response_format,
                "tools_declared": tools,
                "tool_choice": tool_choice,
                "finish_reason": getattr(choice, "finish_reason", None),
                "latency_s": latency,
                "ts": _hb.time.time(),
            }
        )
        return text, p, c

    @staticmethod
    def _call_openrouter(
        model: str,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout: float = 600.0,
        trace_role: str = "cloud",
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, int, int]:
        """Single OpenRouter call. Returns (text, p_tok, c_tok).

        OpenRouter is OpenAI-API-compatible; we use the OpenAI SDK with a
        custom ``base_url`` and ``OPENROUTER_API_KEY``. ``model`` is the
        OpenRouter slug ``"<provider>/<model>"`` (e.g.
        ``"deepseek/deepseek-r1"``). For convenience the caller may also
        pass the OpenJarvis-engine-style ``"openrouter/<provider>/<model>"``
        prefix (see ``src/openjarvis/engine/cloud.py``) — we strip it here.

        Note: unlike ``_call_openai``, we do NOT apply the GPT-5 family
        ``max_completion_tokens`` rewrite or temperature stripping —
        OpenRouter models have varied parameter support. We pass through
        whatever the caller supplies; if a specific model errors on
        ``temperature``, that's the cell's problem to handle.

        ``extra_body`` is forwarded to the OpenAI SDK as the ``extra_body``
        kwarg so callers can pass OpenRouter-specific fields (e.g.
        ``{"reasoning": {"effort": "medium"}}`` to enable thinking on Qwen3,
        or ``{"provider": {...}}`` to pin routing). The SDK serializes
        ``extra_body`` into the JSON request body alongside the standard
        fields.

        Every call goes through the process-wide
        ``_OpenRouterLimiter`` (concurrency semaphore + sliding-window RPM
        deque) so a wide ThreadPoolExecutor can't blow past account caps.

        Trace events use ``"kind": "openrouter"`` so the dashboard can
        distinguish them from native OpenAI calls.
        """
        from openai import OpenAI

        if model.startswith("openrouter/"):
            model = model[len("openrouter/") :]
        api_key = _hb.os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set; cannot call OpenRouter.")
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=timeout,
        )
        messages: list = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        limiter = _hb._openrouter_limiter()
        limiter.wait_for_rpm_slot()
        limiter.acquire_concurrency()
        try:
            t0 = _hb.time.time()
            resp = client.chat.completions.create(**kwargs)
        finally:
            limiter.release_concurrency()
            limiter.record_call()
        _hb._bump_cloud_calls()
        latency = _hb.time.time() - t0
        choice = resp.choices[0]
        message = choice.message
        text = message.content or ""
        tool_calls = _hb._serialize_openai_tool_calls(
            getattr(message, "tool_calls", None)
        )
        reasoning = getattr(message, "reasoning_content", None) or getattr(
            message, "reasoning", None
        )
        u = resp.usage
        p = getattr(u, "prompt_tokens", 0) if u else 0
        c = getattr(u, "completion_tokens", 0) if u else 0
        _hb._record_event(
            {
                "kind": "openrouter",
                "role": trace_role,
                "model": model,
                "system": system,
                "user": user,
                "response": text,
                "tool_calls": tool_calls,
                "reasoning_content": reasoning,
                "tokens_in": p,
                "tokens_out": c,
                "finish_reason": getattr(choice, "finish_reason", None),
                "latency_s": latency,
                "ts": _hb.time.time(),
            }
        )
        return text, p, c

    @staticmethod
    def _call_gemini(
        model: str,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout: float = 600.0,
        trace_role: str = "cloud",
    ) -> Tuple[str, int, int]:
        """Single Gemini Developer-API call. Returns (text, p_tok, c_tok).

        Tool-call parity with Anthropic is intentionally NOT implemented —
        skillorchestra / baseline-cloud only need text generation, and the
        google-genai tool-config plumbing diverges enough from the
        Anthropic/OpenAI shape that wiring it would double the surface
        area of this file. If a future paradigm needs Gemini tool use,
        extend this helper rather than hand-rolling it in the agent.

        Captures the call into the active per-task trace via the
        ``"gemini"`` kind so the dashboard's trace renderer picks it up.
        """
        from google import genai
        from google.genai import types

        client = genai.Client(
            http_options=types.HttpOptions(timeout=int(timeout * 1000))
        )
        cfg = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system:
            cfg.system_instruction = system
        t0 = _hb.time.time()
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=cfg,
        )
        _hb._bump_cloud_calls()
        latency = _hb.time.time() - t0
        # `resp.text` is the convenience accessor that concatenates every
        # text part in the first candidate. Empty if the model emitted
        # only non-text parts (which we don't request).
        text = (resp.text or "") if hasattr(resp, "text") else ""
        um = getattr(resp, "usage_metadata", None)
        p = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
        c = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
        finish_reason = None
        try:
            finish_reason = str(resp.candidates[0].finish_reason)
        except Exception:
            pass
        _hb._record_event(
            {
                "kind": "gemini",
                "role": trace_role,
                "model": model,
                "system": system,
                "user": user,
                "response": text,
                "tokens_in": p,
                "tokens_out": c,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "finish_reason": finish_reason,
                "latency_s": latency,
                "ts": _hb.time.time(),
            }
        )
        return text, p, c

    @staticmethod
    def _call_vllm(
        model: str,
        endpoint: str,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        enable_thinking: bool = False,
        tools: Optional[list] = None,
        tool_choice: Optional[Any] = None,
        timeout: float = 600.0,
        trace_role: str = "local",
    ) -> Tuple[str, int, int]:
        """Local vLLM (OpenAI-compatible) call. Returns (text, p_tok, c_tok).
        Captures the full response into the trace — including any tool_calls
        the local model emits (vLLM exposes them in
        ``resp.choices[0].message.tool_calls`` when ``--enable-auto-tool-choice``
        is on)."""
        from openai import OpenAI

        client = OpenAI(base_url=endpoint, api_key="EMPTY", timeout=timeout)
        messages: list = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        kwargs: Dict[str, Any] = dict(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": enable_thinking}},
        )
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        t0 = _hb.time.time()
        resp = client.chat.completions.create(**kwargs)
        _hb._bump_local_calls()
        latency = _hb.time.time() - t0
        choice = resp.choices[0]
        message = choice.message
        text = message.content or ""
        tool_calls = _hb._serialize_openai_tool_calls(
            getattr(message, "tool_calls", None)
        )
        reasoning = getattr(message, "reasoning_content", None) or getattr(
            message, "reasoning", None
        )
        u = resp.usage
        p = getattr(u, "prompt_tokens", 0) if u else 0
        c = getattr(u, "completion_tokens", 0) if u else 0
        _hb._record_event(
            {
                "kind": "vllm",
                "role": trace_role,
                "model": model,
                "endpoint": endpoint,
                "system": system,
                "user": user,
                "response": text,
                "tool_calls": tool_calls,
                "reasoning_content": reasoning,
                "tokens_in": p,
                "tokens_out": c,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "enable_thinking": enable_thinking,
                "tools_declared": tools,
                "tool_choice": tool_choice,
                "finish_reason": getattr(choice, "finish_reason", None),
                "latency_s": latency,
                "ts": _hb.time.time(),
            }
        )
        return text, p, c

    @staticmethod
    def _call_anthropic_agent(
        model: str,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tools: Optional[list] = None,
        max_turns: int = 8,
        timeout: float = 600.0,
        max_retries: int = 5,
        trace_role: str = "cloud",
    ) -> Tuple[str, int, int, int, int]:
        """Multi-turn Anthropic loop with optional tools.

        Returns ``(final_text, prompt_tokens_sum, completion_tokens_sum,
        n_web_searches_sum, turns)``. The loop appends the assistant
        response (preserving server-tool blocks so Anthropic's continuation
        is valid) and re-prompts until the model stops with ``end_turn``
        or we hit ``max_turns``. Server-side tools (web_search) execute
        inside a single message and don't require a tool_result echo —
        the model just continues thinking with the search results
        already in its context. Client-side tools aren't executed here;
        if the model emits a client-side ``tool_use`` block we stop
        (paradigms that want client tools should call ``_call_anthropic``
        directly and handle their own dispatch).
        """
        import anthropic

        client = anthropic.Anthropic(timeout=timeout, max_retries=max_retries)
        # Build the conversation. We grow ``messages`` across turns so the
        # model sees its own prior assistant content (text + server tool
        # use + web_search_tool_result). For server tools Anthropic is
        # happy as long as we feed the raw assistant content back; no
        # synthetic user tool_result block is needed.
        messages: List[Dict[str, Any]] = [{"role": "user", "content": user}]
        p_total = 0
        c_total = 0
        n_searches_total = 0
        last_text = ""
        turns = 0
        for turn in range(max(1, max_turns)):
            turns = turn + 1
            kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if system:
                kwargs["system"] = system
            if _hb.supports_temperature(model):
                kwargs["temperature"] = temperature
            if tools:
                kwargs["tools"] = tools
            t0 = _hb.time.time()
            msg = client.messages.create(**kwargs)
            _hb._bump_cloud_calls()
            latency = _hb.time.time() - t0
            text = "".join(b.text for b in msg.content if hasattr(b, "text"))
            srv = getattr(msg.usage, "server_tool_use", None)
            n_searches = getattr(srv, "web_search_requests", 0) if srv else 0
            content_blocks = [_hb._serialize_block(b) for b in msg.content]
            tool_use_blocks = [
                b
                for b in content_blocks
                if b.get("type") in ("tool_use", "server_tool_use")
            ]
            tool_result_blocks = [
                b
                for b in content_blocks
                if b.get("type") in ("web_search_tool_result", "tool_result")
            ]
            stop_reason = getattr(msg, "stop_reason", None)
            _hb._record_event(
                {
                    "kind": "anthropic",
                    "role": trace_role,
                    "model": model,
                    "system": system if turn == 0 else None,
                    "user": user if turn == 0 else None,
                    "turn": turn,
                    "response": text,
                    "content_blocks": content_blocks,
                    "tool_calls": tool_use_blocks,
                    "tool_results": tool_result_blocks,
                    "tokens_in": msg.usage.input_tokens,
                    "tokens_out": msg.usage.output_tokens,
                    "n_web_searches": n_searches,
                    "tools_declared": tools,
                    "stop_reason": stop_reason,
                    "latency_s": latency,
                    "ts": _hb.time.time(),
                }
            )
            p_total += msg.usage.input_tokens
            c_total += msg.usage.output_tokens
            n_searches_total += n_searches
            if text:
                last_text = text
            # If the model wants a client-side tool we don't dispatch
            # here — break and let the caller (or future loop variant)
            # handle it. Only ``server_tool_use`` blocks (web_search)
            # are auto-continued by Anthropic itself.
            client_tool_use = any(b.get("type") == "tool_use" for b in content_blocks)
            if client_tool_use:
                break
            if stop_reason == "end_turn" or stop_reason is None:
                break
            # Otherwise: ``stop_reason`` like "max_tokens" or "tool_use"
            # (server side) — Anthropic returned mid-thought. Append the
            # assistant turn and ask it to continue.
            messages.append({"role": "assistant", "content": msg.content})
            messages.append(
                {
                    "role": "user",
                    "content": "Continue.",
                }
            )
        return last_text, p_total, c_total, n_searches_total, turns

    @staticmethod
    def _call_openai_agent(
        model: str,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tools: Optional[list] = None,
        max_turns: int = 8,
        timeout: float = 600.0,
        trace_role: str = "cloud",
    ) -> Tuple[str, int, int, int, int]:
        """OpenAI hosted-web-search call via the Responses API.

        Returns ``(final_text, prompt_tokens_sum, completion_tokens_sum,
        n_web_searches_sum, turns)`` — the same 5-tuple shape as
        ``_call_anthropic_agent`` so callers can dispatch uniformly.

        OpenAI's hosted web search is exposed only through the **Responses
        API** (``client.responses.create``), not chat completions. The tool
        is declared as ``{"type": "web_search"}``; older SDK/model combos
        only accept the legacy ``"web_search_preview"`` name, so we retry
        once with that on a tool-type rejection. The Responses API runs the
        search server-side and returns the post-search answer in one call,
        so ``turns`` is 1 — the ``max_turns`` arg is accepted only for
        signature parity with ``_call_anthropic_agent``.

        ``n_web_searches`` counts ``web_search_call`` items in the response
        output. Token usage is summed from ``response.usage``
        (``input_tokens`` / ``output_tokens``).
        """
        from openai import OpenAI

        del max_turns  # Responses API resolves search server-side in one call.
        client = OpenAI(timeout=timeout)

        search_tool_names = ["web_search", "web_search_preview"]
        kwargs_base: Dict[str, Any] = {
            "model": model,
            "input": user,
            "max_output_tokens": max_tokens,
        }
        if system:
            kwargs_base["instructions"] = system
        # GPT-5 family ignores `temperature` on the Responses API (reasoning
        # models reject it); only pass it for non-gpt-5 models.
        if not _hb.is_gpt5_family(model):
            kwargs_base["temperature"] = temperature

        resp = None
        last_exc: Optional[BaseException] = None
        used_tool_name = search_tool_names[0]
        t0 = _hb.time.time()
        for tool_name in search_tool_names:
            try:
                resp = client.responses.create(
                    **kwargs_base,
                    tools=[{"type": tool_name}],
                )
                used_tool_name = tool_name
                break
            except Exception as exc:  # noqa: BLE001
                # Only fall through to the legacy name on what looks like a
                # tool-type rejection; re-raise anything else immediately.
                last_exc = exc
                msg = str(exc).lower()
                if "web_search" in msg or "tool" in msg or "unsupported" in msg:
                    continue
                raise
        if resp is None:
            raise (
                last_exc
                if last_exc is not None
                else RuntimeError(
                    "openai responses.create failed for all web_search tool names"
                )
            )
        _hb._bump_cloud_calls()
        latency = _hb.time.time() - t0

        # Extract output text. Prefer the SDK convenience accessor; fall back
        # to walking the output items for `output_text` content parts.
        text = ""
        try:
            text = resp.output_text or ""
        except Exception:  # noqa: BLE001
            text = ""
        output_items = list(getattr(resp, "output", None) or [])
        if not text:
            chunks: List[str] = []
            for item in output_items:
                if getattr(item, "type", None) != "message":
                    continue
                for part in getattr(item, "content", None) or []:
                    if getattr(part, "type", None) in ("output_text", "text"):
                        chunks.append(getattr(part, "text", "") or "")
            text = "".join(chunks)

        n_searches = sum(
            1
            for item in output_items
            if getattr(item, "type", None)
            in (
                "web_search_call",
                "web_search_tool_call",
            )
        )
        u = getattr(resp, "usage", None)
        p = int(getattr(u, "input_tokens", 0) or 0) if u else 0
        c = int(getattr(u, "output_tokens", 0) or 0) if u else 0
        _hb._record_event(
            {
                "kind": "openai_agent",
                "role": trace_role,
                "model": model,
                "system": system,
                "user": user,
                "response": text,
                "output_items": _hb._jsonable(output_items),
                "tokens_in": p,
                "tokens_out": c,
                "n_web_searches": n_searches,
                "tools_declared": [{"type": used_tool_name}],
                "stop_reason": getattr(resp, "status", None),
                "latency_s": latency,
                "ts": _hb.time.time(),
            }
        )
        return text, p, c, n_searches, 1

    @staticmethod
    def _call_gemini_agent(
        model: str,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tools: Optional[list] = None,
        max_turns: int = 8,
        timeout: float = 600.0,
        trace_role: str = "cloud",
    ) -> Tuple[str, int, int, int, int]:
        """Gemini call grounded with Google Search.

        Returns ``(final_text, prompt_tokens_sum, completion_tokens_sum,
        n_web_searches_sum, turns)`` — same shape as ``_call_anthropic_agent``.

        Grounding is wired by adding ``Tool(google_search=GoogleSearch())``
        to the ``GenerateContentConfig``. Gemini resolves the grounding
        server-side inside a single ``generate_content`` call, so
        ``turns`` is always 1 and ``max_turns`` / ``tools`` are accepted
        only for signature parity with ``_call_anthropic_agent``.

        ``n_web_searches`` is derived from ``candidates[0].grounding_metadata``
        — we count the ``web_search_queries`` Gemini reports, falling back to
        0 when no grounding metadata is present (the model answered without
        searching).
        """
        from google import genai
        from google.genai import types

        del tools, max_turns  # grounding is config-level + single-call.
        client = genai.Client(
            http_options=types.HttpOptions(timeout=int(timeout * 1000))
        )
        cfg = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )
        if system:
            cfg.system_instruction = system
        t0 = _hb.time.time()
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=cfg,
        )
        _hb._bump_cloud_calls()
        latency = _hb.time.time() - t0
        text = (resp.text or "") if hasattr(resp, "text") else ""
        um = getattr(resp, "usage_metadata", None)
        p = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
        c = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0

        # Derive search count from grounding metadata when present.
        n_searches = 0
        web_search_queries: List[str] = []
        finish_reason = None
        try:
            cand0 = resp.candidates[0]
            finish_reason = str(getattr(cand0, "finish_reason", None))
            gm = getattr(cand0, "grounding_metadata", None)
            if gm is not None:
                queries = getattr(gm, "web_search_queries", None) or []
                web_search_queries = [str(q) for q in queries]
                n_searches = len(web_search_queries)
        except Exception:  # noqa: BLE001
            pass
        _hb._record_event(
            {
                "kind": "gemini_agent",
                "role": trace_role,
                "model": model,
                "system": system,
                "user": user,
                "response": text,
                "tokens_in": p,
                "tokens_out": c,
                "n_web_searches": n_searches,
                "web_search_queries": web_search_queries,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "finish_reason": finish_reason,
                "latency_s": latency,
                "ts": _hb.time.time(),
            }
        )
        return text, p, c, n_searches, 1


__all__ = ["SDKCallsMixin"]

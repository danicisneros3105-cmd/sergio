"""Route handlers for the OpenAI-compatible API server."""

from __future__ import annotations

import asyncio
import logging
import threading
import weakref
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, HTTPException, Request

# routes_admin looks get_config_dir, is_embed_only_model, ModelListResponse
# and ModelObject up on this module.
from openjarvis.core.paths import get_config_dir  # noqa: F401
from openjarvis.core.types import Message, Role, ToolCall
from openjarvis.server.model_capabilities import is_embed_only_model  # noqa: F401
from openjarvis.server.models import (  # noqa: F401
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    ComplexityInfo,
    ModelListResponse,
    ModelObject,
    UsageInfo,
)

router = APIRouter()


def _to_messages(chat_messages) -> list[Message]:
    """Convert Pydantic ChatMessage objects to core Message objects."""
    messages = []
    for m in chat_messages:
        role = Role(m.role) if m.role in {r.value for r in Role} else Role.USER
        messages.append(
            Message(
                role=role,
                content=m.content or "",
                name=m.name,
                tool_calls=[
                    ToolCall(
                        id=tool_call.get("id", ""),
                        name=tool_call.get("function", {}).get("name", ""),
                        arguments=tool_call.get("function", {}).get("arguments", "{}"),
                    )
                    for tool_call in (m.tool_calls or [])
                ]
                or None,
                tool_call_id=m.tool_call_id,
            )
        )
    return messages


def _ensure_identity_prompt(messages: list[Message], app_config) -> list[Message]:
    """Return one leading system message, adding identity when needed.

    The desktop UI's chat backend posts only user/assistant turns to
    ``/v1/chat/completions`` (see ``frontend/.../Chat/InputArea.tsx``), so
    nothing grounds the model's identity. Without a system prompt the model
    answers from its training identity (e.g. "I'm Claude", "I am Qwen"),
    which is what #540 reported. The CLI paths inject this via
    ``SystemPromptBuilder`` / ``BaseAgent``; the engine-direct server paths
    did not. This mirrors the agent fallback in ``agents/_stubs.py``.

    If any caller-supplied message already carries a system role, the caller
    has supplied their own grounding and we do not add the server identity.
    All system messages are still folded into one leading entry because some
    chat templates reject multiple or mid-history system roles. Internally
    tagged memory context does not count as caller grounding.

    Resolution of the identity text: the config comes from ``app.state`` when
    wired, otherwise ``load_config()``; the prompt itself is assembled by
    ``SystemPromptBuilder`` from ``agent.default_system_prompt`` plus the
    persona files (SOUL.md/MEMORY.md/USER.md), matching
    ``_build_managed_system_prompt`` in ``agent_manager_routes.py``. Config
    resolution is wrapped so a broken/missing config degrades to "no
    injection" rather than crashing the endpoint, but the failure is logged
    (per REVIEW.md — never silently swallow).
    """

    def _is_caller_system_prompt(m: Message) -> bool:
        return m.role == Role.SYSTEM and not m.metadata.get("memory_context")

    system_messages = [message for message in messages if message.role == Role.SYSTEM]
    caller_supplied_system = any(
        _is_caller_system_prompt(message) for message in system_messages
    )
    identity_already_applied = any(
        message.metadata.get("openjarvis_identity_prompt")
        for message in system_messages
    )

    prompt = ""
    if not caller_supplied_system and not identity_already_applied:
        try:
            cfg = app_config
            if cfg is None:
                from openjarvis.core.config import load_config

                cfg = load_config()

            from openjarvis.prompt.builder import SystemPromptBuilder

            builder = SystemPromptBuilder(
                agent_template=cfg.agent.default_system_prompt or "",
                memory_files_config=getattr(cfg, "memory_files", None),
                system_prompt_config=getattr(cfg, "system_prompt", None),
            )
            prompt = builder.build()
        except Exception:
            logging.getLogger("openjarvis.server").debug(
                "Identity system prompt resolution failed; "
                "serving request without identity grounding",
                exc_info=True,
            )

    if prompt:
        # The prompt library rides along with the identity (agent paths add it
        # in BaseAgent, so it is only built here for engine-direct requests).
        last_user = next(
            (m.text for m in reversed(messages) if m.role == Role.USER and m.text), ""
        )
        try:
            from openjarvis.connectome.brain import mind_context

            guidance = mind_context(last_user)
        except Exception:  # noqa: BLE001
            guidance = ""
        if guidance:
            prompt = f"{prompt}\n\n{guidance}"
        try:  # never invent progress on a video (video_essay/job.truth)
            from openjarvis.nodes.worker import _with_truth

            prompt = _with_truth(last_user, prompt)
        except Exception:  # noqa: BLE001
            pass

    system_parts = []
    if prompt:
        system_parts.append(prompt)
    system_parts.extend(message.text for message in system_messages if message.text)
    non_system_messages = [
        message for message in messages if message.role != Role.SYSTEM
    ]

    if not system_parts:
        return non_system_messages

    if system_messages:
        first_system = system_messages[0]
        metadata = dict(first_system.metadata)
        if prompt:
            # Preserve the first system message's metadata while tagging the
            # server-built identity so BaseAgent does not build it a second
            # time if this normalized conversation later reaches agent code.
            metadata["openjarvis_identity_prompt"] = True
        combined_system = replace(
            first_system,
            content="\n\n".join(system_parts),
            metadata=metadata,
        )
    else:
        combined_system = Message(
            role=Role.SYSTEM,
            content=prompt,
            metadata={"openjarvis_identity_prompt": True},
        )

    return [combined_system, *non_system_messages]


def _apply_terry(request_body: ChatCompletionRequest, query: str, model: str) -> bool:
    """Terry's brief rides with the request as an instruction (the owner's own
    words stay as they are). Returns whether a brief was added."""
    from openjarvis.agents import terry
    from openjarvis.server.models import ChatMessage

    try:
        brief, _analysis = terry.prepare(
            query, terry.history_text(request_body.messages), model
        )
    except Exception:  # noqa: BLE001 — Terry is a bonus: the request goes as it came
        return False
    terry.prepared(query)
    msgs = list(request_body.messages)
    if msgs and msgs[0].role == "system":
        msgs[0] = ChatMessage(
            role="system", content=f"{msgs[0].content or ''}\n\n{brief}"
        )
    else:
        msgs.insert(0, ChatMessage(role="system", content=brief))
    request_body.messages = msgs
    return True


def _last_user_text(request_body: ChatCompletionRequest) -> str:
    for m in reversed(request_body.messages):
        if m.role == "user" and m.content:
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


@router.post("/v1/chat/completions")
async def chat_completions(request_body: ChatCompletionRequest, request: Request):
    """Handle chat completion requests; medium and complicated ones are first
    understood by Terry (agents/terry.py), with «Preguntándole a Terry…» and
    playful status lines streamed while he works."""
    from openjarvis.agents import terry
    from openjarvis.connectome import decision as cortex

    query = _last_user_text(request_body)
    if query:
        await asyncio.to_thread(terry.judge_previous, query)
    quick = any(
        m.role == "system" and str(m.content or "").startswith("[Quick Chat]")
        for m in request_body.messages
    )  # Quick Chat: speed first, no Terry
    # The brain decides first (connectome/decision.py): how much to think, and
    # whether Terry writes the brief. Without the brain, Terry's own rule.
    thought = (
        await asyncio.to_thread(cortex.think, query, "chat")
        if query and not request_body.tools
        else None
    )
    wants_terry = (
        thought.terry if thought is not None else bool(query) and terry.wanted(query)
    )
    if request_body.tools or quick or not query or not wants_terry:
        return await _chat_completions(request_body, request)
    if not request_body.stream:
        await asyncio.to_thread(_apply_terry, request_body, query, request_body.model)
        return await _chat_completions(request_body, request)

    lang = terry.language(query)

    async def body():
        import json as _json

        lines = terry.statuses(lang)
        yield f"event: status\ndata: {_json.dumps({'phase': lines[0]})}\n\n"
        task = asyncio.ensure_future(
            asyncio.to_thread(_apply_terry, request_body, query, request_body.model)
        )
        i = 1
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.8)
            except asyncio.TimeoutError:
                yield f"event: status\ndata: {_json.dumps({'phase': lines[i % len(lines)]})}\n\n"
                i += 1
        yield f"event: status\ndata: {_json.dumps({'phase': lines[i % len(lines)]})}\n\n"
        inner = await _chat_completions(request_body, request)
        iterator = getattr(inner, "body_iterator", None)
        if iterator is None:
            raw = getattr(inner, "body", b"")
            yield raw.decode() if isinstance(raw, bytes) else str(raw)
            return
        async for chunk in iterator:
            yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _inject_memory(
    request_body: ChatCompletionRequest,
    config: Any,
    memory_backend: Any,
    memory_service: Any,
    use_server_agent: bool,
) -> None:
    """Fold the memories that fit the request into its messages."""
    if (
        config is not None
        and config.agent.context_from_memory
        and request_body.messages
    ):
        try:
            from openjarvis.tools.storage.context import ContextConfig, inject_context

            facts = memory_service.list_facts() if memory_service is not None else []

            # Extract query from the last user message
            query_text = ""
            for m in reversed(request_body.messages):
                if m.role == "user" and m.content:
                    query_text = m.content
                    break

            if query_text:
                messages = _to_messages(request_body.messages)
                # Direct engine paths need the server identity folded into
                # memory here so adapters receive one leading system message.
                # Agent paths build that same identity in BaseAgent; injecting
                # it at both layers duplicates the prompt around memory.
                if not use_server_agent:
                    messages = _ensure_identity_prompt(messages, config)
                ctx_cfg = ContextConfig(
                    top_k=config.memory.context_top_k,
                    min_score=config.memory.context_min_score,
                    max_context_tokens=config.memory.context_max_tokens,
                )
                enriched = inject_context(
                    query_text,
                    messages,
                    memory_backend,
                    config=ctx_cfg,
                    facts=facts,
                )
                # Rebuild after identity/context merging so downstream engine
                # adapters always receive exactly one system message.
                from openjarvis.server.models import ChatMessage

                new_msgs = []
                for msg in enriched:
                    new_msgs.append(
                        ChatMessage(
                            role=msg.role.value,
                            content=msg.content,
                            name=msg.name,
                            tool_calls=[
                                {
                                    "id": tool_call.id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_call.name,
                                        "arguments": tool_call.arguments,
                                    },
                                }
                                for tool_call in (msg.tool_calls or [])
                            ]
                            or None,
                            tool_call_id=getattr(msg, "tool_call_id", None),
                        )
                    )
                request_body.messages = new_msgs
        except Exception:
            logging.getLogger("openjarvis.server").debug(
                "Memory context injection failed",
                exc_info=True,
            )


async def _chat_completions(request_body: ChatCompletionRequest, request: Request):
    """Handle chat completion requests (streaming and non-streaming)."""
    from openjarvis.quota import guard, model_weight

    guard("mensajes", model_weight(request_body.model))  # a big model counts more
    from openjarvis.accounts.provision import CUSTOMER_KEY, customer_model

    if CUSTOMER_KEY.get():  # a customer: through their own key at OpenRouter
        request_body.model = customer_model(request_body.model)
    engine = request.app.state.engine
    agent = getattr(request.app.state, "agent", None)
    model = request_body.model
    use_server_agent = (
        agent is not None
        and not request_body.tools
        and (not request_body.stream or bool(getattr(agent, "_tools", None)))
    )

    # Inject memory context into messages before dispatching (in a worker
    # thread: a memory search must never hold up the other requests, like a
    # voice turn arriving at the same time).
    config = getattr(request.app.state, "config", None)
    memory_backend = getattr(request.app.state, "memory_backend", None)
    await asyncio.to_thread(
        _inject_memory,
        request_body,
        config,
        memory_backend,
        getattr(request.app.state, "memory_service", None),
        use_server_agent,
    )

    # How much to think: the brain's basal ganglia choose (connectome/decision.py)
    # from what they learned; the inherited complexity score is only the
    # fallback when the brain is switched off.
    complexity_info = None
    query_text_for_complexity = ""
    for m in reversed(request_body.messages):
        if m.role == "user" and m.content:
            query_text_for_complexity = m.content
            break
    thought = None
    if query_text_for_complexity and not request_body.tools:
        from openjarvis.connectome import decision as cortex

        thought = await asyncio.to_thread(
            cortex.think, str(query_text_for_complexity), "chat"
        )
    if thought is not None:
        try:
            from openjarvis.learning.routing.complexity import adjust_tokens_for_model

            suggested = adjust_tokens_for_model(thought.max_tokens, model)
        except Exception:  # noqa: BLE001
            suggested = thought.max_tokens
        complexity_info = ComplexityInfo(
            score=thought.score, tier=thought.tier, suggested_max_tokens=suggested
        )
        if suggested > request_body.max_tokens:
            request_body.max_tokens = suggested
        model = _effort_for(model, thought.tier)
    elif query_text_for_complexity:
        try:
            from openjarvis.learning.routing.complexity import (
                adjust_tokens_for_model,
                score_complexity,
            )

            cr = score_complexity(query_text_for_complexity)
            suggested = adjust_tokens_for_model(
                cr.suggested_max_tokens,
                model,
            )
            complexity_info = ComplexityInfo(
                score=cr.score,
                tier=cr.tier,
                suggested_max_tokens=suggested,
            )
            # Bump max_tokens when complexity suggests more than what
            # the client requested — never reduce below the request value.
            if suggested > request_body.max_tokens:
                request_body.max_tokens = suggested
            model = _effort_for(model, cr.tier)
        except Exception:
            logging.getLogger("openjarvis.server").debug(
                "Complexity analysis failed",
                exc_info=True,
            )

    if request_body.stream:
        # When the client passes `tools`, stream the model's raw
        # OpenAI-compat function-calling decision directly from the engine
        # (bypassing the agent) — the streaming mirror of the non-streaming
        # #454 fix. Routing client-supplied tools through a server-side agent
        # would execute the agent's different tool set and drop the raw tool
        # call the caller expects (#414).
        #
        # Without client-supplied tools, keep streaming requests on the
        # configured server agent so its server-side tool loop is available
        # to the desktop UI and other stream:true clients (#735). Fall back to
        # direct token streaming when no tool-bearing agent is configured.
        if request_body.tools:
            return await _handle_stream_tools(
                engine,
                model,
                request_body,
                complexity_info,
                app_config=config,
                bus=getattr(request.app.state, "bus", None),
                memory_service=getattr(request.app.state, "memory_service", None),
            )
        if use_server_agent:
            return await _handle_agent_stream(
                agent,
                model,
                request_body,
                complexity_info,
                trace_store=getattr(request.app.state, "trace_store", None),
                bus=getattr(request.app.state, "bus", None),
                memory_service=getattr(request.app.state, "memory_service", None),
            )
        return await _handle_stream(
            engine,
            model,
            request_body,
            complexity_info,
            trace_store=getattr(request.app.state, "trace_store", None),
            app_config=config,
            bus=getattr(request.app.state, "bus", None),
            memory_service=getattr(request.app.state, "memory_service", None),
        )

    # Non-streaming: use agent if available, otherwise direct engine call.
    #
    # EXCEPTION: when the client explicitly passed `tools`, they're asking
    # for raw OpenAI-compat function-calling — return the model's
    # tool_call decision verbatim. Routing through `_handle_agent` would
    # call `agent.run(input_text)`, which IGNORES `request_body.tools`,
    # runs the agent's own internal tool loop with its own (different)
    # tool spec, and returns only `result.content` — so the model's
    # tool_calls vanish and the user sees a generic acknowledgement
    # (e.g. "Understood. If you have another request...") that the
    # agent's re-prompted LLM produced. See #414.
    #
    # If a future caller needs agent orchestration WITH client-supplied
    # tools (e.g. injecting MCP tools through this endpoint and wanting
    # the agent to execute them), add an explicit opt-in header rather
    # than removing this guard — silent re-routing is what produced #414.
    # ``_handle_agent`` (sync ``agent.run()``) and ``_handle_direct`` (sync
    # ``engine.generate()``) both make blocking upstream calls; run them in a
    # worker thread so a slow/wedged non-streaming request can't stall the
    # event loop and every other concurrent request with it.
    if use_server_agent:
        response = await asyncio.to_thread(
            _handle_agent,
            agent,
            model,
            request_body,
            complexity_info,
            trace_store=getattr(request.app.state, "trace_store", None),
            bus=getattr(request.app.state, "bus", None),
        )
    else:
        bus = getattr(request.app.state, "bus", None)
        response = await asyncio.to_thread(
            _handle_direct,
            engine,
            model,
            request_body,
            bus=bus,
            complexity_info=complexity_info,
            app_config=config,
        )

    # Hand the completed exchange to the background memory service.
    _remember_exchange(
        getattr(request.app.state, "memory_service", None),
        query_text_for_complexity,
        response,
        bus=getattr(request.app.state, "bus", None),
        source="server.chat",
    )
    return response


def _response_content(response) -> str:
    """Extract assistant text from an OpenAI-compatible response object."""
    content = ""
    choices = getattr(response, "choices", None)
    if choices:
        content = getattr(choices[0].message, "content", "") or ""
    return content


def _record_completed_exchange(
    memory_service,
    user_text: str,
    assistant_text: str,
    *,
    bus=None,
    source: str = "server.chat",
) -> None:
    """Publish or submit a completed exchange without blocking a reply."""
    if not user_text:
        return
    try:
        if bus is not None:
            from openjarvis.memory import publish_completed_exchange

            publish_completed_exchange(
                bus,
                user_text,
                assistant_text,
                source=source,
            )
        else:
            from openjarvis.connectome.brain import remember_exchange

            remember_exchange(user_text, assistant_text)
            if memory_service is not None:
                memory_service.submit(user_text, assistant_text)
    except Exception:  # noqa: BLE001 — memory is best-effort, never fail a reply
        logging.getLogger("openjarvis.server").debug(
            "Memory submit failed",
            exc_info=True,
        )


def _remember_exchange(
    memory_service,
    user_text: str,
    response,
    *,
    bus=None,
    source: str = "server.chat",
) -> None:
    """Record a completed non-streaming exchange."""
    _record_completed_exchange(
        memory_service,
        user_text,
        _response_content(response),
        bus=bus,
        source=source,
    )


def _effort_for(model: str, tier: str) -> str:
    """Pick the thinking level of a Gemini 3+ model from the question.

    Left to its default, Gemini 3.8 Flash thinks hard on "hola" (about 6 s
    instead of 2 s). Easy questions get ``low``; only hard ones think more.
    An explicit ``model@effort`` or ``SERGIO_EFFORT`` always wins.
    """
    import os
    import re

    if "@" in model or os.environ.get("SERGIO_EFFORT", "").strip():
        return model
    found = re.match(r"gemini-(\d+(?:\.\d+)?)", model)
    if not found or float(found.group(1)) < 3:
        return model
    effort = {"complex": "medium", "very_complex": "high"}.get(tier, "low")
    return f"{model}@{effort}"


def _engine_key_for_model(engine: Any, model: str) -> str | None:
    """Resolve the engine that advertised *model* through wrapper layers."""
    from openjarvis.engine.multi import MultiEngine
    from openjarvis.security.guardrails import GuardrailsEngine
    from openjarvis.telemetry.instrumented_engine import InstrumentedEngine

    current = engine
    while current is not None:
        if isinstance(current, MultiEngine):
            return current.engine_key_for(model)
        if isinstance(current, InstrumentedEngine):
            current = current._inner
            continue
        if isinstance(current, GuardrailsEngine):
            current = current._engine
            continue
        engine_id = getattr(current, "engine_id", None)
        return engine_id if isinstance(engine_id, str) else None
    return None


def _uses_direct_cloud_router(engine: Any, model: str) -> bool:
    """Whether *model* should bypass the configured engine for direct cloud."""
    from openjarvis.server.cloud_router import is_cloud_model

    return is_cloud_model(model) and _engine_key_for_model(engine, model) != "litellm"


def _handle_direct(
    engine,
    model: str,
    req: ChatCompletionRequest,
    bus=None,
    complexity_info=None,
    app_config=None,
) -> ChatCompletionResponse:
    """Direct engine call without agent."""
    messages = _to_messages(req.messages)
    messages = _ensure_identity_prompt(messages, app_config)
    kwargs: dict[str, Any] = {}
    if req.tools:
        kwargs["tools"] = req.tools
    if bus:
        from openjarvis.telemetry.instrumented_engine import InstrumentedEngine
        from openjarvis.telemetry.wrapper import instrumented_generate

        # `app.state.engine` may already be an InstrumentedEngine (the
        # common case when telemetry is wired in). If we then wrap it
        # with `instrumented_generate`, BOTH layers fire a
        # TELEMETRY_RECORD per call:
        #
        #   - InstrumentedEngine.generate() publishes a FULL record
        #     (energy_joules, GPU stats, token_counting_version, ...).
        #   - instrumented_generate() publishes a BARE record (timing +
        #     tokens only; no energy meter, no version stamp).
        #
        # The doubled count was the dominant driver of the bimodal
        # Wh/token distribution on the public leaderboard.
        #
        # The fix below is NOT "unwrap and call instrumented_generate":
        # that would have replaced "doubled records" with "every
        # request emits only a bare record with no energy / no version",
        # which the leaderboard's `current_methodology_only=True` filter
        # would then drop entirely. Instead, when the engine is already
        # an InstrumentedEngine, skip the wrapper and call `generate`
        # directly — InstrumentedEngine publishes the full per-record
        # event itself with energy + version intact. Only fall back to
        # the lightweight wrapper for engines that aren't already
        # instrumented.
        if isinstance(engine, InstrumentedEngine):
            result = engine.generate(
                messages,
                model=model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                **kwargs,
            )
        else:
            result = instrumented_generate(
                engine,
                messages,
                model=model,
                bus=bus,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                **kwargs,
            )
    else:
        result = engine.generate(
            messages,
            model=model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            **kwargs,
        )
    content = result.get("content", "")
    usage = result.get("usage", {})

    choice_msg = ChoiceMessage(role="assistant", content=content)
    # Include tool calls if present
    tool_calls = result.get("tool_calls")
    if tool_calls:
        choice_msg.tool_calls = [
            {
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": tc.get("arguments", "{}"),
                },
            }
            for tc in tool_calls
        ]

    return ChatCompletionResponse(
        model=model,
        choices=[
            Choice(
                message=choice_msg,
                finish_reason=result.get("finish_reason", "stop"),
            )
        ],
        usage=UsageInfo(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        ),
        complexity=complexity_info,
    )


# _handle_agent runs on a worker thread (via asyncio.to_thread) for both
# the streaming and non-streaming routes, so concurrent requests against
# the same shared agent execute on real OS threads and can genuinely
# interleave. A lock per agent *instance* serializes the
# override-run-restore critical section below so one request's temporary
# `model` override can never be read as another's "original" value (#759).
# Key by object identity rather than by the agent itself: custom agents may be
# unhashable or may not support weak references.  The values are weak so this
# registry retains neither the agent nor an idle lock.  A caller keeps the lock
# alive from lookup through the full override/run/restore critical section.
_agent_model_locks: "weakref.WeakValueDictionary[int, threading.Lock]" = (
    weakref.WeakValueDictionary()
)
_agent_model_locks_guard = threading.Lock()


def _get_agent_model_lock(agent: Any) -> threading.Lock:
    """Return the lock serializing model overrides for *agent*, creating it
    on first use. One lock per agent instance, not global, so unrelated
    agents don't serialize against each other."""
    agent_id = id(agent)
    with _agent_model_locks_guard:
        lock = _agent_model_locks.get(agent_id)
        if lock is None:
            lock = threading.Lock()
            _agent_model_locks[agent_id] = lock
        return lock


def _request_agent(agent: Any, model: str) -> Any:
    """A per-request copy of *agent* using *model*, or None if it cannot be copied."""
    import copy

    try:
        own = copy.copy(agent)
        if model:
            own._model = model
    except Exception:  # noqa: BLE001 — fall back to the serialized override
        return None
    guard = getattr(agent, "_loop_guard", None)
    if guard is not None:
        try:
            from openjarvis.agents.loop_guard import LoopGuard

            own._loop_guard = LoopGuard(guard._config, bus=getattr(guard, "_bus", None))
        except Exception:  # noqa: BLE001 — keep the shared guard
            pass
    return own


def _handle_agent(
    agent,
    model: str,
    req: ChatCompletionRequest,
    complexity_info=None,
    *,
    trace_store=None,
    bus=None,
    sink=None,
) -> ChatCompletionResponse:
    """Run through agent; with *sink*, its text goes there as it is written.

    When *trace_store* is set, the agent run is wrapped in a
    ``TraceCollector`` (mirroring ``system/orchestrator.py``) so every
    completion records a ``Trace`` to ``traces.db``. Previously this endpoint
    called ``agent.run()`` raw, so the server never produced traces:
    ``traces.db`` stayed empty and spec_search's cold-start gate
    (``check_readiness``, min 20 traces) could never open.
    """
    from openjarvis.agents._stubs import AgentContext

    # Build context from prior messages
    ctx = AgentContext()
    if len(req.messages) > 1:
        prior = _to_messages(req.messages[:-1])
        for m in prior:
            ctx.conversation.add(m)

    # Last message is the input
    input_text = req.messages[-1].content if req.messages else ""

    def run(target) -> Any:
        if sink is not None:
            from openjarvis.agents._stubs import stream_tokens

            with stream_tokens(sink, target):
                return _run(target)
        return _run(target)

    def _run(target) -> Any:
        if trace_store is not None:
            from openjarvis.traces.collector import TraceCollector

            collector = TraceCollector(target, store=trace_store, bus=bus)
            return collector.run(input_text, context=ctx)
        return target.run(input_text, context=ctx)

    # Each request runs on its own shallow copy of the agent with its model
    # (#759) and a fresh loop guard. It used to hold one lock for the whole
    # run, so a voice turn waited for a chat turn (and a Node) to finish
    # (owner, 26 Oct 2026: «lag en mensajes y voz»), and the loop guard's
    # counts never reset between requests.
    own = _request_agent(agent, model)
    if own is not None:
        result = run(own)
    else:  # an agent that cannot be copied: the old serialized override
        with _get_agent_model_lock(agent):
            original_model = agent._model
            if model:
                agent._model = model
            try:
                result = run(agent)
            finally:
                agent._model = original_model

    usage = UsageInfo(
        prompt_tokens=result.metadata.get("prompt_tokens", 0),
        completion_tokens=result.metadata.get("completion_tokens", 0),
        total_tokens=result.metadata.get("total_tokens", 0),
    )

    # Include audio metadata if the agent produced audio (e.g. morning digest)
    audio_meta = None
    audio_path = result.metadata.get("audio_path", "")
    if audio_path:
        from pathlib import Path

        from openjarvis.server.models import AudioMeta

        if Path(audio_path).exists():
            audio_meta = AudioMeta(url="/api/digest/audio")

    return ChatCompletionResponse(
        model=model,
        choices=[
            Choice(
                message=ChoiceMessage(
                    role="assistant",
                    content=result.content,
                    audio=audio_meta,
                ),
                finish_reason="stop",
            )
        ],
        usage=usage,
        complexity=complexity_info,
    )


@router.get("/health")
async def health(request: Request):
    """Health check endpoint."""
    engine = request.app.state.engine
    healthy = engine.health()
    if not healthy:
        raise HTTPException(status_code=503, detail="Engine unhealthy")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Channel endpoints
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Security scan endpoint
# ---------------------------------------------------------------------------


__all__ = ["router"]


# Moved to their own module; they look their helpers up here.
from openjarvis.server.routes_stream import _handle_agent_stream as _handle_agent_stream  # noqa: E402,I001
from openjarvis.server.routes_stream import _handle_stream as _handle_stream  # noqa: E402,I001
from openjarvis.server.routes_stream import _handle_stream_tools as _handle_stream_tools  # noqa: E402,I001

# Only the moved code uses these; it looks them up on this module.
import uuid as uuid  # noqa: E402,I001
from fastapi.responses import StreamingResponse as StreamingResponse  # noqa: E402,I001
from openjarvis.server.models import ChatCompletionChunk as ChatCompletionChunk  # noqa: E402,I001
from openjarvis.server.models import DeltaMessage as DeltaMessage  # noqa: E402,I001
from openjarvis.server.models import StreamChoice as StreamChoice  # noqa: E402,I001

# Endpoints moved to their own module; importing it registers them on
# ``router`` (it looks every helper up on this module).
from openjarvis.server import routes_admin as _routes_admin  # noqa: E402,I001

list_models = _routes_admin.list_models
pull_model = _routes_admin.pull_model
delete_model = _routes_admin.delete_model
reload_cloud_engine = _routes_admin.reload_cloud_engine
savings = _routes_admin.savings
reset_telemetry = _routes_admin.reset_telemetry
server_info = _routes_admin.server_info
list_channels = _routes_admin.list_channels
channel_send = _routes_admin.channel_send
channel_status = _routes_admin.channel_status
security_scan = _routes_admin.security_scan

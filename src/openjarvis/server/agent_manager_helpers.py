"""Helpers behind the managed-agent routes: the shared memory backend and MCP
clients, the lightweight system used to run an agent, the tool catalogue,
system prompts, history replay and SSE chunks.

Split out of ``agent_manager_routes.py``; its names are looked up on that
module at call time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Tuple

import openjarvis.server.agent_manager_routes as _amr


def _resolve_memory_backend(config: Any) -> Any:
    """Instantiate the configured memory backend, or None if unavailable.

    Memory storage is a tool dependency, independent of whether retrieved
    context is injected into prompts.  ``context_from_memory`` controls only
    that prompt enrichment; explicitly configured ``memory_*`` tools still
    need a backend when it is false.
    """
    if config is None:
        return None
    try:
        import openjarvis.tools.storage  # noqa: F401
        from openjarvis.core.registry import MemoryRegistry

        key = config.memory.default_backend
        if MemoryRegistry.contains(key):
            return MemoryRegistry.create(key, db_path=config.memory.db_path)
    except Exception:
        _amr.logger.debug(
            "Lightweight system: memory backend init failed", exc_info=True
        )
    return None


def _memory_backend_lock(app_state: Any) -> threading.Lock:
    """Return the per-runtime lock, creating it safely for lightweight tests."""

    lock = getattr(app_state, "_memory_backend_lock", None)
    if lock is not None:
        return lock
    with _amr._MEMORY_BACKEND_LOCK_SETUP:
        lock = getattr(app_state, "_memory_backend_lock", None)
        if lock is None:
            lock = _amr.threading.Lock()
            app_state._memory_backend_lock = lock
    return lock


def _get_or_create_memory_backend(app_state: Any, config: Any = None) -> Any:
    """Return one runtime-owned memory backend, even under concurrent ticks."""

    if app_state is None:
        return None
    backend = getattr(app_state, "memory_backend", None)
    if backend is not None:
        return backend

    lock = _amr._memory_backend_lock(app_state)
    with lock:
        backend = getattr(app_state, "memory_backend", None)
        if backend is not None:
            return backend
        if getattr(app_state, "_managed_runtime_stopping", False):
            return None
        backend = _amr._resolve_memory_backend(
            config if config is not None else getattr(app_state, "config", None)
        )
        if backend is not None:
            app_state.memory_backend = backend
            app_state._owns_memory_backend = True
        return backend


def _mcp_state_lock(app_state: Any, attr: str) -> threading.Lock:
    """Return a named per-runtime MCP lock, creating it atomically."""

    lock = getattr(app_state, attr, None)
    if lock is not None:
        return lock
    with _amr._MCP_LOCK_SETUP:
        lock = getattr(app_state, attr, None)
        if lock is None:
            lock = _amr.threading.Lock()
            setattr(app_state, attr, lock)
    return lock


def _register_mcp_client(app_state: Any, client: Any) -> bool:
    """Publish a client before blocking I/O so shutdown can interrupt it."""

    lock = _amr._mcp_state_lock(app_state, "_mcp_clients_lock")
    with lock:
        if getattr(app_state, "_managed_runtime_stopping", False):
            return False
        clients = getattr(app_state, "_mcp_clients", None)
        if not isinstance(clients, list):
            clients = list(clients or [])
            app_state._mcp_clients = clients
        clients.append(client)
        return True


def _unregister_mcp_client(app_state: Any, client: Any) -> None:
    """Remove a client that failed discovery or exposed no usable tools."""

    lock = _amr._mcp_state_lock(app_state, "_mcp_clients_lock")
    with lock:
        clients = getattr(app_state, "_mcp_clients", None)
        if isinstance(clients, list):
            try:
                clients.remove(client)
            except ValueError:
                pass


def _make_lightweight_system(
    engine: Any,
    model: str,
    config: Any = None,
    runtime: Any = None,
) -> _amr._LightweightSystem:
    """Build a minimal system with a fresh inference engine.

    The server's ``app.state.engine`` is heavily wrapped
    (MultiEngine -> InstrumentedEngine -> GuardrailsEngine) and can
    return empty content from background threads. Create a fresh
    engine directly (no health checks or model discovery that
    could interfere with in-flight requests).
    """
    try:
        from openjarvis.engine._discovery import get_engine

        cfg = config
        if cfg is None:
            from openjarvis.core.config import load_config

            cfg = load_config()

        pref = cfg.intelligence.preferred_engine
        key = pref or cfg.engine.default
        resolved = get_engine(cfg, key)

        if resolved is not None:
            plain_engine = resolved[1]
        else:
            from openjarvis.engine.ollama import OllamaEngine

            host = cfg.engine.ollama.host if cfg else ""
            plain_engine = OllamaEngine(host=host) if host else OllamaEngine()

        # Wrap with InstrumentedEngine so agent ticks are recorded
        # in telemetry (FLOPs, energy, cost savings).
        try:
            from openjarvis.telemetry.instrumented_engine import (
                InstrumentedEngine,
            )

            plain_engine = InstrumentedEngine(
                plain_engine,
                _amr._get_runtime_event_bus(runtime),
            )
        except Exception:
            pass  # telemetry is optional
        return _amr._LightweightSystem(plain_engine, model, cfg, runtime)
    except Exception:
        pass
    return _amr._LightweightSystem(engine, model, config, runtime)


def _parse_param_count(model_name: str) -> float:
    """Extract parameter count in billions from model name.

    Examples: 'qwen3.5:9b' -> 9.0, 'qwen3.5:0.8b' -> 0.8
    """
    m = _amr._re.search(r":(\d+(?:\.\d+)?)b", model_name.lower())
    return float(m.group(1)) if m else 0.0


def _pick_recommended_model(
    model_ids: list[str],
) -> dict[str, str]:
    """Pick the second-largest local *chat* model from a list.

    Embedding-only models (nomic-embed-text, etc.) are excluded — they return
    HTTP 400 "does not support chat" when used as the generation model.
    """
    local = [
        m
        for m in model_ids
        if not any(m.startswith(p) for p in _amr._CLOUD_PREFIXES)
        and not _amr.is_embed_only_model(m)
    ]
    if not local:
        # Fall back to any non-cloud model, still skipping embedders.
        local = [m for m in model_ids if not _amr.is_embed_only_model(m)]
    if not local:
        # Never recommend an embed-only model — chat would 400.
        return {
            "model": "",
            "reason": "No local chat model available",
        }
    sized = sorted(local, key=_amr._parse_param_count, reverse=True)
    if len(sized) == 1:
        return {"model": sized[0], "reason": "Only local chat model available"}
    pick = sized[1]  # second-largest
    params = _amr._parse_param_count(pick)
    return {
        "model": pick,
        "reason": f"Second-largest local model ({params}B parameters)",
    }


def build_tools_list() -> List[Dict[str, Any]]:
    """Build unified tools list from ToolRegistry + ChannelRegistry."""
    import os

    from openjarvis.core.credentials import TOOL_CREDENTIALS
    from openjarvis.core.registry import ChannelRegistry, ToolRegistry

    _amr._ensure_registries_populated()

    items: List[Dict[str, Any]] = []

    for name, tool_cls in ToolRegistry.items():
        if name in _amr._BROWSER_SUB_TOOLS:
            continue
        # `spec` is an instance @property on BaseTool subclasses, so
        # we have to instantiate the tool to read it. The earlier
        # implementation used getattr(tool_cls, 'spec') which returns
        # the property descriptor and crashed on spec.description,
        # silently dropping every real tool from the picker.
        try:
            tool_instance = tool_cls()
            spec = tool_instance.spec
        except Exception as exc:
            _amr.logger.debug("Could not instantiate tool %s: %s", name, exc)
            spec = None
        cred_keys = TOOL_CREDENTIALS.get(name, [])
        has_fallback = bool(spec and spec.metadata.get("fallback"))
        credentials_configured = (
            spec.metadata.get("credentials_configured") if spec else None
        )
        items.append(
            {
                "name": name,
                "description": spec.description if spec else "",
                "category": spec.category if spec else "",
                "source": "tool",
                "requires_credentials": len(cred_keys) > 0 and not has_fallback,
                "credential_keys": cred_keys,
                "configured": (
                    has_fallback
                    or (
                        bool(credentials_configured)
                        if credentials_configured is not None
                        else all(bool(os.environ.get(k)) for k in cred_keys)
                    )
                    if cred_keys
                    else True
                ),
            }
        )

    try:
        if any(ToolRegistry.contains(n) for n in _amr._BROWSER_SUB_TOOLS):
            items.append(
                {
                    "name": "browser",
                    "description": (
                        "Web browser automation"
                        " (navigate, click, type, screenshot, extract)"
                    ),
                    "category": "browser",
                    "source": "tool",
                    "requires_credentials": False,
                    "credential_keys": [],
                    "configured": True,
                }
            )
    except Exception:
        pass

    try:
        for name, _cls in ChannelRegistry.items():
            cred_keys = TOOL_CREDENTIALS.get(name, [])
            items.append(
                {
                    "name": name,
                    "description": (
                        f"{name.replace('_', ' ').title()} messaging channel"
                    ),
                    "category": "communication",
                    "source": "channel",
                    "requires_credentials": len(cred_keys) > 0,
                    "credential_keys": cred_keys,
                    "configured": (
                        all(bool(os.environ.get(k)) for k in cred_keys)
                        if cred_keys
                        else True
                    ),
                }
            )
    except Exception:
        pass

    return items


def _resolve_tool_specs(tool_config: Any) -> List[Dict[str, Any]]:
    """Compatibility wrapper for callers of the former route-local helper."""

    return _amr.resolve_tool_specs(tool_config)


def _build_managed_system_prompt(system_prompt: str, app_config: Any) -> str:
    """Build the streaming managed-agent system prompt via SystemPromptBuilder.

    Routes the agent's own ``system_prompt`` through the same builder the
    CLI/ask path uses, so SOUL.md / MEMORY.md / USER.md persona files are
    injected for streaming chat too (#431). Returns the assembled prompt
    (caller decides whether to append a SYSTEM message); an agent with
    neither persona nor template yields an empty string, preserving the
    prior no-SYSTEM-message behavior.
    """
    from openjarvis.prompt.builder import SystemPromptBuilder

    builder = SystemPromptBuilder(
        agent_template=system_prompt or "",
        memory_files_config=getattr(app_config, "memory_files", None),
        system_prompt_config=getattr(app_config, "system_prompt", None),
    )
    return builder.build()


def _sampler_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract per-agent sampler params from a managed agent's config (#386)."""
    out: Dict[str, Any] = {}
    for key in _amr._SAMPLER_PARAM_KEYS:
        val = config.get(key)
        if val is not None:
            out[key] = val
    return out


def _replay_history_messages(
    history: List[Dict[str, Any]],
    exclude_id: str,
) -> List[Any]:
    """Rebuild prior-turn LLM messages from stored managed-agent history.

    When a stored assistant turn recorded ``tool_calls``, replay them as an
    assistant tool-use message followed by the corresponding tool-result
    messages — so the model sees its own prior tool pattern instead of
    regressing to fabricated tool output on later turns. Without this, only
    the assistant's text is replayed and the tool-use signal is lost (#382).
    """
    from openjarvis.core.types import Message, Role, ToolCall

    messages: List[Any] = []
    for m in reversed(history):
        if m.get("id") == exclude_id:
            continue
        direction = m.get("direction")
        if direction == "user_to_agent":
            messages.append(Message(role=Role.USER, content=m.get("content") or ""))
        elif direction == "agent_to_user":
            stored = m.get("tool_calls")
            if stored:
                calls = []
                results = []
                for i, tc in enumerate(stored):
                    call_id = f"hist-{m.get('id', '')}-{i}"
                    calls.append(
                        ToolCall(
                            id=call_id,
                            name=tc.get("tool", ""),
                            arguments=tc.get("arguments") or "",
                        )
                    )
                    results.append(
                        Message(
                            role=Role.TOOL,
                            content=str(tc.get("result", "")),
                            tool_call_id=call_id,
                            name=tc.get("tool", ""),
                        )
                    )
                messages.append(
                    Message(
                        role=Role.ASSISTANT,
                        content=m.get("content") or None,
                        tool_calls=calls,
                    )
                )
                messages.extend(results)
            else:
                messages.append(
                    Message(role=Role.ASSISTANT, content=m.get("content") or "")
                )
    return messages


def _instantiate_managed_tool(
    tool_cls: Any,
    name: str,
    *,
    engine: Any,
    model: str,
    app_state: Any,
) -> Any:
    """Compatibility adapter for tests and non-managed route callers."""

    memory_backend = _amr._get_or_create_memory_backend(
        app_state,
        getattr(app_state, "config", None) if app_state is not None else None,
    )
    channel_backend = None
    if app_state is not None:
        channel_backend = getattr(app_state, "channel_backend", None) or getattr(
            app_state, "channel_bridge", None
        )
    return _amr.instantiate_registered_tool(
        tool_cls,
        name,
        engine=engine,
        model=model,
        memory_backend=memory_backend,
        channel_backend=channel_backend,
    )


def _build_deep_research_tools(
    engine: Any,
    model: str,
    knowledge_db_path: str = "",
) -> list[Any]:
    """Compatibility wrapper for existing channel and server integrations."""

    return _amr.build_deep_research_tools(engine, model, knowledge_db_path)


def _merge_tool_call_fragments(
    accumulated: Dict[int, Dict[str, Any]],
    fragments: List[Dict[str, Any]],
) -> None:
    """Merge incremental tool_call delta fragments into accumulated state.

    OpenAI-compatible APIs send tool_calls as incremental fragments keyed
    by ``index``. Each fragment may contain partial ``function.name`` and/or
    ``function.arguments`` strings that must be concatenated.
    """
    for frag in fragments:
        idx = frag.get("index", 0)
        if idx not in accumulated:
            accumulated[idx] = {
                "id": frag.get("id", ""),
                "type": "function",
                "function": {"name": "", "arguments": ""},
            }
        entry = accumulated[idx]
        if frag.get("id"):
            entry["id"] = frag["id"]
        fn = frag.get("function", {})
        if fn.get("name"):
            entry["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            entry["function"]["arguments"] += fn["arguments"]


def _get_mcp_tools(app_state: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (openai_tools_list, mcp_adapters_by_name).

    Lazily discovers MCP tools from config and caches them on ``app_state``
    so that subsequent requests reuse the same connections.
    """
    lock = _amr._mcp_state_lock(app_state, "_mcp_discovery_lock")
    with lock:
        return _amr._get_mcp_tools_locked(app_state)


def _sse_chunk(chunk_id: str, model: str, content: str) -> str:
    """Build a single SSE content chunk."""
    import json as _json

    data = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content},
                "finish_reason": None,
            }
        ],
    }
    return f"data: {_json.dumps(data)}\n\n"


def _tool_progress_label(tool_name: str, args: str) -> str:
    """Human-readable label for a tool call in progress."""
    labels = {
        "knowledge_search": "Searching your knowledge base",
        "knowledge_sql": "Querying data with SQL",
        "scan_chunks": "Scanning documents for semantic matches",
        "think": "Planning next step",
    }
    label = labels.get(tool_name, f"Using {tool_name}")
    if args and tool_name != "think":
        # Try to extract the query/question from args JSON
        try:
            import json as _json

            parsed = _json.loads(args)
            q = parsed.get("query") or parsed.get("question") or ""
            if q:
                label += f' — "{q[:50]}"'
        except Exception:
            pass
    return label


__all__ = [
    "_resolve_memory_backend",
    "_memory_backend_lock",
    "_get_or_create_memory_backend",
    "_mcp_state_lock",
    "_register_mcp_client",
    "_unregister_mcp_client",
    "_make_lightweight_system",
    "_parse_param_count",
    "_pick_recommended_model",
    "build_tools_list",
    "_resolve_tool_specs",
    "_build_managed_system_prompt",
    "_sampler_kwargs",
    "_replay_history_messages",
    "_instantiate_managed_tool",
    "_build_deep_research_tools",
    "_merge_tool_call_fragments",
    "_get_mcp_tools",
    "_sse_chunk",
    "_tool_progress_label",
]

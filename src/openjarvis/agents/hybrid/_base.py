"""LocalCloudAgent — shared base for hybrid local+cloud paradigm agents.

The hybrid paradigms (Minions, Conductor, Archon, Advisors, SkillOrchestra,
ToolOrchestra) all coordinate at least two models: a small **local** model
served by vLLM over an OpenAI-compatible endpoint, and a **cloud** model
reached via the Anthropic or OpenAI SDK.

Why not just use OpenJarvis's :class:`InferenceEngine` for both? Two reasons:

1. The reference hybrid adapters (``hybrid-local-cloud-compute/adapters/``) make
   raw SDK calls because some of them (Minions, Archon) construct external
   library objects that themselves create their own SDK clients. We mirror that
   here so the n=500 numbers stay reproducible during the port.
2. Cloud-side quirks (Opus 4.7 temperature stripping, GPT-5 family
   ``max_completion_tokens``) are paradigm-shaped — Minions needs structured
   outputs on the supervisor turn, SkillOrchestra needs them on the router,
   baseline_cloud does not. Keeping the SDK calls in the agent layer lets each
   paradigm decide the schema rather than fighting a shared engine API.

The base class therefore provides only:

- Standard ``run()`` contract returning an :class:`AgentResult` whose
  ``metadata`` carries the hybrid-result fields (``tokens_local``,
  ``tokens_cloud``, ``cost_usd``, ``latency_s``, ``traces``).
- ``_call_anthropic`` / ``_call_openai`` / ``_call_vllm`` helpers that handle
  Opus 4.7 temperature stripping, GPT-5 token-arg naming, vLLM
  ``enable_thinking`` kwargs, and basic token bookkeeping.
- ``_soft_fail_metadata`` for deterministic failure rows (e.g. Qwen JSON
  malformation) so the runner doesn't crash the whole cell.

Agents register themselves with ``@AgentRegistry.register("name")`` and become
discoverable via the existing SDK / CLI flow. The runner constructs them with
the cloud ``(engine, model)`` as the canonical pair, and paradigm-specific
kwargs (``local_model``, ``local_endpoint``, ``cloud_endpoint``, …) follow.
"""

from __future__ import annotations

import json
import os
import threading
import time
from abc import abstractmethod
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from openjarvis.agents._stubs import AgentContext, AgentResult, BaseAgent
from openjarvis.agents.hybrid._openai_retry import patch_openai_globally
from openjarvis.agents.hybrid._prices import (
    NO_TEMP_PREFIXES,
    is_gpt5_family,
    supports_temperature,
)
from openjarvis.agents.hybrid._prices import (
    cost as estimate_cost,
)
from openjarvis.engine._stubs import InferenceEngine

# Install OpenAI SDK retry + per-org concurrency cap at import time so
# every paradigm (advisors, conductor, minions, mini_swe_agent's cloud
# loop, archon, …) inherits the hardening without each call site having
# to remember to opt in. See ``_openai_retry.py`` for the env knobs
# (default: 4 concurrent, 8 retries, 2s/60s exponential backoff w/ jitter).
patch_openai_globally()

# Anthropic server-side web_search: $10 per 1000 searches.
WEB_SEARCH_COST_PER_CALL = 0.01

# OpenAI Responses-API hosted web_search tool: $10 per 1000 calls
# (2025-12 public list price for the `web_search` / `web_search_preview`
# tool, billed per tool call). Same shape as Anthropic, so we reuse the
# $0.01/call number — kept as a separate constant so it can drift.
OPENAI_WEB_SEARCH_COST_PER_CALL = 0.01

# Gemini 3 Google-Search grounding: billed at $14 per 1000 search queries.
# `_call_gemini_agent` reports the model's `web_search_queries`, so this is
# charged per query, not per outer generate_content request.
GEMINI_SEARCH_COST_PER_CALL = 0.014

# Tavily Search, advanced depth: 2 API credits per search request at $0.008
# per credit on the public pay-as-you-go plan. WebSearchTool captures actual
# credits when Tavily returns usage metadata; this is the fallback estimate.
TAVILY_SEARCH_COST_PER_CREDIT = 0.008
TAVILY_ADVANCED_SEARCH_CREDITS = 2
TAVILY_SEARCH_COST_PER_CALL = (
    TAVILY_SEARCH_COST_PER_CREDIT * TAVILY_ADVANCED_SEARCH_CREDITS
)

ANTHROPIC_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 8,
}


def build_web_search_tool(max_uses: int = 8) -> Dict[str, Any]:
    """Build an Anthropic server-side web_search tool block with a custom cap.

    Web_search is server-side: Anthropic runs the searches internally before
    returning, so ``max_uses`` is the only knob the caller has to bound cost
    per task. Defaults to 8 (matches ``ANTHROPIC_WEB_SEARCH_TOOL``).
    """
    return {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": int(max_uses),
    }


def tavily_search_context(
    query: str,
    *,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Run OpenJarvis WebSearchTool and return accounting-friendly metadata."""
    from openjarvis.tools.web_search import WebSearchTool

    tool = WebSearchTool(max_results=max_results)
    res = tool.execute(query=query, max_results=max_results)
    meta = dict(res.metadata or {})
    engine = str(meta.get("engine") or "unknown")
    credits = 0
    cost_usd = 0.0
    if engine == "tavily":
        try:
            credits = int(meta.get("credits") or TAVILY_ADVANCED_SEARCH_CREDITS)
        except (TypeError, ValueError):
            credits = TAVILY_ADVANCED_SEARCH_CREDITS
        cost_usd = credits * TAVILY_SEARCH_COST_PER_CREDIT
    text = res.content or ""
    if not res.success and not text:
        text = "(no search results)"
    return {
        "text": text,
        "success": bool(res.success),
        "engine": engine,
        "credits": credits,
        "cost_usd": cost_usd,
        "n_searches": 1 if (query or "").strip() else 0,
        "error": None if res.success else text,
    }


def web_search_cfg(method_cfg: Optional[Dict[str, Any]]) -> Tuple[bool, int]:
    """Parse ``method_cfg.web_search = { enabled, max_uses }``.

    Defaults: enabled=False, max_uses=8. ``enabled`` defaults to False so
    existing cells stay one-shot (backwards compat). Cells opting in flip
    ``enabled=true`` in the registry. Returns ``(enabled, max_uses)``.
    """
    if not method_cfg:
        return False, 8
    ws = method_cfg.get("web_search")
    if not isinstance(ws, dict):
        return False, 8
    return bool(ws.get("enabled", False)), int(ws.get("max_uses", 8))


# ---------- Thread-local trace buffer ----------
#
# Every call through ``_call_anthropic`` / ``_call_openai`` / ``_call_vllm``
# appends an event to the active trace if one is open. ``run()`` opens a fresh
# trace per task and writes the digested log to
# ``<log_dir>/<task_id>.json`` when it's done. Thread-local so concurrent
# tasks in the runner's ThreadPoolExecutor don't stomp each other's trace.

_TRACE_STATE = threading.local()


def _trace_events() -> Optional[List[Dict[str, Any]]]:
    return getattr(_TRACE_STATE, "events", None)


def _record_event(event: Dict[str, Any]) -> None:
    events = _trace_events()
    if events is not None:
        events.append(event)


def _open_trace() -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    _TRACE_STATE.events = events
    return events


def _close_trace() -> None:
    if hasattr(_TRACE_STATE, "events"):
        delattr(_TRACE_STATE, "events")


# ---------- Thread-local LLM-call counter ----------
#
# Parallel to the trace buffer: every cloud SDK call (anthropic / openai /
# gemini, including each turn of ``_call_anthropic_agent`` and each turn of
# the mini-SWE multi-turn loops) bumps ``cloud``; every local vLLM call
# bumps ``local``. ``run()`` opens a fresh pair per task, drops the totals
# into ``meta["n_cloud_calls"]`` / ``meta["n_local_calls"]``, then closes.
#
# Why thread-local and not an instance counter: agents are shared across
# the runner's ``ThreadPoolExecutor`` (one agent, N concurrent tasks). An
# attribute on ``self`` would race; this matches the trace buffer's
# pattern exactly so it composes with the rest of the per-task plumbing.

_CALL_COUNTS = threading.local()


def _call_counts() -> Optional[Dict[str, int]]:
    return getattr(_CALL_COUNTS, "counts", None)


def _bump_cloud_calls(n: int = 1) -> None:
    counts = _call_counts()
    if counts is not None:
        counts["cloud"] += int(n)


def _bump_local_calls(n: int = 1) -> None:
    counts = _call_counts()
    if counts is not None:
        counts["local"] += int(n)


def _open_call_counts() -> Dict[str, int]:
    counts: Dict[str, int] = {"cloud": 0, "local": 0}
    _CALL_COUNTS.counts = counts
    return counts


def _close_call_counts() -> None:
    if hasattr(_CALL_COUNTS, "counts"):
        delattr(_CALL_COUNTS, "counts")


# ---------- OpenRouter in-process rate limiter ----------
#
# OpenRouter enforces per-account RPM and concurrency limits. A single agent
# process running a wide ThreadPoolExecutor (Conductor's 7-worker pool fanned
# across the runner's per-task threads) can trivially blow past those caps,
# triggering 429s that the OpenAI SDK retries with backoff — wasted latency
# and noisy traces.
#
# We gate every ``_call_openrouter`` call through two limits, **shared across
# threads in this Python process** (singleton; lazy-initialized):
#
# - **Concurrency** — a ``threading.Semaphore``. Default 20 in-flight calls;
#   override via ``OJ_OPENROUTER_MAX_CONCURRENT``. Held only around the SDK
#   ``client.chat.completions.create`` invocation, not the bookkeeping.
# - **RPM** — a sliding window of timestamps in a ``deque``. Default 60
#   requests/minute; override via ``OJ_OPENROUTER_RPM``. If the deque has
#   already accumulated ``RPM`` timestamps within the last 60 seconds, the
#   caller sleeps until the oldest entry ages out, then proceeds. Every
#   completed call appends ``time.time()`` so the call we just made is
#   counted against the next window.
#
# Other cloud helpers (``_call_openai`` / ``_call_anthropic`` / ``_call_gemini``)
# are NOT rate-limited here — OpenAI and Anthropic have their own concurrency
# patch (``_openai_retry``) and Gemini's free-tier RPM is loose enough that
# we haven't hit it yet. Add limiters for those one-by-one if needed.

_OPENROUTER_LIMITER_LOCK = threading.Lock()
_OPENROUTER_LIMITER: Optional["_OpenRouterLimiter"] = None


class _OpenRouterLimiter:
    """Process-wide concurrency + sliding-window RPM gate for OpenRouter."""

    def __init__(self, max_concurrent: int, rpm: int) -> None:
        self.max_concurrent = int(max_concurrent)
        self.rpm = int(rpm)
        self._sem = threading.Semaphore(self.max_concurrent)
        self._window: Deque[float] = deque()
        self._window_lock = threading.Lock()

    def acquire_concurrency(self) -> None:
        self._sem.acquire()

    def release_concurrency(self) -> None:
        self._sem.release()

    def wait_for_rpm_slot(self) -> None:
        """Block until making one more call would not exceed RPM in 60s."""
        while True:
            with self._window_lock:
                now = time.time()
                cutoff = now - 60.0
                while self._window and self._window[0] < cutoff:
                    self._window.popleft()
                if len(self._window) < self.rpm:
                    return
                # Sleep until the oldest in-window call ages out, then recheck.
                sleep_s = 60.0 - (now - self._window[0]) + 0.01
            if sleep_s > 0:
                time.sleep(sleep_s)

    def record_call(self) -> None:
        with self._window_lock:
            self._window.append(time.time())


def _openrouter_limiter() -> _OpenRouterLimiter:
    global _OPENROUTER_LIMITER
    if _OPENROUTER_LIMITER is None:
        with _OPENROUTER_LIMITER_LOCK:
            if _OPENROUTER_LIMITER is None:
                max_concurrent = int(
                    os.environ.get("OJ_OPENROUTER_MAX_CONCURRENT", "20") or 20
                )
                rpm = int(os.environ.get("OJ_OPENROUTER_RPM", "60") or 60)
                _OPENROUTER_LIMITER = _OpenRouterLimiter(max_concurrent, rpm)
    return _OPENROUTER_LIMITER


def _serialize_block(block: Any) -> Dict[str, Any]:
    """Turn an Anthropic content block (text / tool_use / server_tool_use /
    web_search_tool_result / thinking) into a JSON-safe dict.

    Each block type carries different fields; we extract everything we can
    so the per-task log file is a complete record of what the model emitted
    (including every tool call request and tool result body).
    """
    out: Dict[str, Any] = {"type": getattr(block, "type", type(block).__name__)}
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
        if hasattr(block, attr):
            val = getattr(block, attr)
            # Nested content (e.g. web_search_tool_result.content is a list of
            # citation/result blocks). Recurse for completeness.
            if attr == "content" and isinstance(val, list):
                out[attr] = [_serialize_block(b) for b in val]
            else:
                out[attr] = _jsonable(val)
    return out


def _serialize_openai_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    """vLLM / OpenAI returns ChatCompletionMessageToolCall objects. Pull out
    id, type, name, and the (JSON-string) arguments so they're round-trippable."""
    out: List[Dict[str, Any]] = []
    if not tool_calls:
        return out
    for tc in tool_calls:
        fn = getattr(tc, "function", None)
        out.append(
            {
                "id": getattr(tc, "id", None),
                "type": getattr(tc, "type", "function"),
                "function": {
                    "name": getattr(fn, "name", None) if fn else None,
                    "arguments": getattr(fn, "arguments", None) if fn else None,
                },
            }
        )
    return out


def _jsonable(v: Any) -> Any:
    """Best-effort JSON-friendly conversion. Pydantic models → .model_dump(),
    dataclasses untouched (json.dumps handles them via default=str)."""
    if hasattr(v, "model_dump"):
        try:
            return v.model_dump()
        except Exception:
            pass
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


# Raw SDK calls live in their own module; they look helpers up here.
from openjarvis.agents.hybrid._base_sdk import SDKCallsMixin  # noqa: E402,I001


class LocalCloudAgent(SDKCallsMixin, BaseAgent):
    """Base for paradigm agents that coordinate a local + cloud model pair.

    Subclasses implement :meth:`_run_paradigm` rather than ``run`` so the
    base can wrap timing, metadata shaping, and soft-fail handling
    uniformly.

    The :meth:`run` contract takes the formatted task prompt as ``input``
    and reads paradigm-shaped data from ``context.metadata``:

    - ``context.metadata["task"]``: optional dict (the bench's raw task
      row, used by paradigms that look at hints / problem_statement / etc.).
    - ``context.metadata["task_id"]``: optional string identifier.

    Construction args:
    - ``engine``, ``model``: the cloud engine + model id (satisfies
      :class:`BaseAgent`'s contract; only used incidentally — we make raw
      SDK calls).
    - ``local_model``, ``local_endpoint``: vLLM-served local model and its
      OpenAI-compatible endpoint, e.g. ``"http://localhost:8001/v1"``.
    - ``cloud_endpoint``: ``"anthropic"`` or ``"openai"`` — picks the
      cloud SDK.
    - ``cfg``: paradigm-specific knobs (max_tokens, schemas, mode, …).
    """

    accepts_tools: bool = False
    # Hybrid agents directly invoke web-search and, in SWE mode, generated
    # shell commands without owning a ToolExecutor.
    uses_direct_operations: bool = True

    def __init__(
        self,
        engine: InferenceEngine,
        model: str,
        *,
        local_model: Optional[str] = None,
        local_endpoint: Optional[str] = None,
        cloud_endpoint: str = "anthropic",
        cfg: Optional[Dict[str, Any]] = None,
        bus: Optional[Any] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        capability_policy: Optional[Any] = None,
        rate_limiter: Optional[Any] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            engine,
            model,
            bus=bus,
            temperature=temperature,
            max_tokens=max_tokens,
            capability_policy=capability_policy,
            rate_limiter=rate_limiter,
            agent_id=agent_id,
        )
        self._cloud_model = model
        self._cloud_endpoint = (cloud_endpoint or "anthropic").lower()
        self._local_model = local_model
        self._local_endpoint = local_endpoint
        self._cfg: Dict[str, Any] = dict(cfg or {})

    # ------------------------------------------------------------------
    # SDK call helpers — raw clients, paradigm-shaped quirks applied
    # ------------------------------------------------------------------

    def _call_cloud(
        self,
        *,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Tuple[str, int, int]:
        """Dispatch a single cloud call by ``self._cloud_endpoint``.

        Returns (text, p_tok, c_tok). For Anthropic, the web_search count
        is discarded — paradigms that care should call ``_call_anthropic``
        directly.
        """
        if self._cloud_endpoint == "anthropic":
            text, p, c, _ = self._call_anthropic(
                self._cloud_model,
                user=user,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            return text, p, c
        if self._cloud_endpoint == "openai":
            return self._call_openai(
                self._cloud_model,
                user=user,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        if self._cloud_endpoint == "gemini":
            # Gemini helper doesn't accept tools / response_format kwargs.
            # Drop them rather than letting them surface as a TypeError so
            # paradigms that opportunistically pass these for OpenAI /
            # Anthropic still work when routed to Gemini.
            kwargs.pop("tools", None)
            kwargs.pop("tool_choice", None)
            kwargs.pop("response_format", None)
            kwargs.pop("output_config", None)
            return self._call_gemini(
                self._cloud_model,
                user=user,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        raise ValueError(f"unsupported cloud endpoint: {self._cloud_endpoint!r}")

    # ------------------------------------------------------------------
    # Result shaping
    # ------------------------------------------------------------------

    @staticmethod
    def _soft_fail_metadata(reason: str) -> Dict[str, Any]:
        """Metadata for a soft-fail row (Qwen JSON broke, Anthropic 400, etc.).

        The agent still returns an :class:`AgentResult` with empty content;
        the runner records it as score=0 without crashing the cell.
        """
        return {
            "tokens_local": 0,
            "tokens_cloud": 0,
            "cost_usd": 0.0,
            "latency_s": 0.0,
            "n_cloud_calls": 0,
            "n_local_calls": 0,
            "soft_error": reason,
            "traces": {"soft_error": reason},
        }

    @staticmethod
    def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        return estimate_cost(model, prompt_tokens, completion_tokens)

    # ------------------------------------------------------------------
    # Run contract
    # ------------------------------------------------------------------

    def _required_capabilities_for_run(
        self,
        context: Optional[AgentContext],
    ) -> List[str]:
        """Derive capabilities from direct operations reachable this run.

        Subclasses with worker pools may extend this hook based on the
        concrete worker/action types they expose, rather than relying only on
        generic configuration flags.
        """
        required = list(self.required_capabilities)
        task_meta = context.metadata.get("task", {}) if context is not None else {}
        if not isinstance(task_meta, dict):
            task_meta = {}
        swe_mode = (
            bool(self._cfg.get("swe_use_agent_loop"))
            and bool(task_meta.get("problem_statement"))
            and bool(task_meta.get("repo"))
            and bool(task_meta.get("base_commit"))
        )
        if bool(self._cfg.get("swe_use_agent_loop")) or bool(
            task_meta.get("repo") and task_meta.get("base_commit")
        ):
            required.extend(("code:execute", "file:read", "file:write"))
        if str(self._cfg.get("search_backend", "provider")).lower() == "tavily":
            required.append("network:fetch")
        web_search_enabled, _ = web_search_cfg(self._cfg)
        if web_search_enabled and not swe_mode:
            # Provider-hosted search is still an external fetch even when
            # ``search_backend`` remains at its default value.
            required.append("network:fetch")
        if self._cfg.get("retriever_url"):
            required.append("network:fetch")
        return list(dict.fromkeys(required))

    def run(
        self,
        input: str,
        context: Optional[AgentContext] = None,
        **kwargs: Any,
    ) -> AgentResult:
        denied = self._execution_denied_result(
            self._required_capabilities_for_run(context),
            operation="hybrid_agent_run",
        )
        if denied is not None:
            return denied
        self._emit_turn_start(input)
        t0 = time.time()
        events = _open_trace()
        counts = _open_call_counts()
        meta: Dict[str, Any]
        answer: str = ""
        soft_reason: Optional[str] = None
        exc_obj: Optional[BaseException] = None
        try:
            try:
                answer, meta = self._run_paradigm(input, context, **kwargs)
            except Exception as exc:
                soft = self._is_soft_failure(exc)
                if soft is None:
                    exc_obj = exc
                    raise
                soft_reason = soft
                meta = self._soft_fail_metadata(soft)
        finally:
            # Snapshot call counts BEFORE closing the thread-local state.
            # Subclasses don't track this themselves — every SDK call site
            # bumps the thread-local in this file, so the totals are
            # authoritative as of right now. Overwrites any value
            # ``_run_paradigm`` happened to set (it shouldn't set them).
            n_cloud = counts.get("cloud", 0)
            n_local = counts.get("local", 0)
            if "meta" in locals():
                meta["n_cloud_calls"] = int(n_cloud)
                meta["n_local_calls"] = int(n_local)
            # Persist the trace before the trace state is closed (and even on
            # hard failure, so we get a record of what we did before it broke).
            self._write_trace_log(
                context,
                input,
                answer,
                meta if "meta" in locals() else {},
                events,
                soft_reason,
                exc_obj,
            )
            _close_trace()
            _close_call_counts()
        meta.setdefault("latency_s", time.time() - t0)
        if soft_reason is not None:
            self._emit_turn_end(soft_error=soft_reason)
            return AgentResult(content="", metadata=meta, turns=0)
        self._emit_turn_end(**{k: v for k, v in meta.items() if k != "traces"})
        return AgentResult(
            content=answer,
            metadata=meta,
            turns=int(meta.get("turns", 0) or 0),
        )

    @staticmethod
    def record_trace_event(event: Dict[str, Any]) -> None:
        """Public hook for paradigm code that bypasses the SDK helpers
        (Minions's protocol loop, Archon's layer pipeline, …) to drop a
        custom event into the current task's trace.
        """
        _record_event({**event, "ts": event.get("ts", time.time())})

    def _write_trace_log(
        self,
        context: Optional[AgentContext],
        input: str,
        answer: str,
        meta: Dict[str, Any],
        events: List[Dict[str, Any]],
        soft_reason: Optional[str],
        exc: Optional[BaseException],
    ) -> None:
        log_dir = None
        task_id = "unknown"
        if context is not None:
            log_dir = context.metadata.get("log_dir")
            task_id = context.metadata.get("task_id") or task_id
        if not log_dir:
            return
        try:
            out_dir = Path(log_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            blob = {
                "task_id": task_id,
                "agent": self.agent_id,
                "cloud_model": self._cloud_model,
                "cloud_endpoint": self._cloud_endpoint,
                "local_model": self._local_model,
                "local_endpoint": self._local_endpoint,
                "cfg": self._cfg,
                "input": input,
                "answer": answer,
                "metadata": meta,
                "events": events,
                "soft_error": soft_reason,
                "error": (f"{type(exc).__name__}: {exc}" if exc is not None else None),
            }
            (out_dir / f"{task_id}.json").write_text(
                json.dumps(blob, indent=2, default=str)
            )
        except Exception:
            # Logging must never break a run.
            pass

    @abstractmethod
    def _run_paradigm(
        self,
        input: str,
        context: Optional[AgentContext],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        """Run the paradigm. Return ``(final_answer, metadata)``.

        Metadata should include the hybrid-shape fields:
        ``tokens_local``, ``tokens_cloud``, ``cost_usd``, optional
        ``latency_s`` (the base fills it if absent), and a ``traces`` dict.
        """

    # Subclasses override to declare deterministic failure modes they
    # want the base to swallow into a soft-fail row.
    def _is_soft_failure(self, exc: BaseException) -> Optional[str]:
        return None


__all__ = [
    "ANTHROPIC_WEB_SEARCH_TOOL",
    "GEMINI_SEARCH_COST_PER_CALL",
    "LocalCloudAgent",
    "NO_TEMP_PREFIXES",
    "OPENAI_WEB_SEARCH_COST_PER_CALL",
    "TAVILY_ADVANCED_SEARCH_CREDITS",
    "TAVILY_SEARCH_COST_PER_CALL",
    "TAVILY_SEARCH_COST_PER_CREDIT",
    "WEB_SEARCH_COST_PER_CALL",
    "_bump_cloud_calls",
    "_bump_local_calls",
    "build_web_search_tool",
    "estimate_cost",
    "is_gpt5_family",
    "supports_temperature",
    "tavily_search_context",
    "web_search_cfg",
]

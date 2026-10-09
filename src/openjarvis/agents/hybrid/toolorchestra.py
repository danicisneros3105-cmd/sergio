"""ToolOrchestraAgent — port of NVlabs ToolOrchestra (arXiv:2511.21689).

Two modes, gated by ``method_cfg.orchestrator_mode``:

* ``"prompted"`` (default, legacy): a cloud model (Opus etc.) plays the
  orchestrator, dispatching to a numbered worker pool via JSON
  ``{"action": "call_worker"|"final_answer", ...}`` actions. Useful as
  a prompted upper-bound reference point — NOT the paper's setup.

* ``"rl"`` (paper-faithful): the RL-trained ``nvidia/Orchestrator-8B``
  served on a local vLLM is the orchestrator. It emits OpenAI-style
  ``tool_calls`` (or ``<tool_call>{...}</tool_call>`` text blocks when
  vLLM's tool parser doesn't catch them) for three expert tools —
  ``enhance_reasoning``, ``answer``, ``search`` — exactly as in the
  upstream ``evaluation/tools.json``. Each tool's ``model`` arg
  (``answer-1``, ``reasoner-2``, ``search-3``, …) is mapped to a real
  backend through ``EXPERT_MODEL_MAPPING`` — by default the frontier
  Anthropic worker for `*-1` slots, gpt-5-mini for `*-2`, local Qwen
  for `*-3`. Search routes to the configured provider's server-side
  web-search helper when available.

  We do NOT reproduce the upstream Tavily / FAISS-wiki retriever, the
  code-interpreter sandbox, or the multi-vLLM mix (Llama-3.3-70B,
  Qwen-Math, Qwen-Coder); the expert pool collapses onto our existing
  worker types. Energy-wise, "expert" answers are cloud calls.

Pipeline per task (RL mode):

1. Orchestrator-8B reads `Problem: ...\\n\\n{context}\\n\\nChoose an
   appropriate tool.` with the three tools declared.
2. It emits one ``tool_call`` per turn — ``search`` updates the
   context, ``enhance_reasoning`` appends code/exec output (we run the
   tool as a plain LLM call, no sandbox — the model just gets prose
   back), ``answer`` produces the final answer and the loop stops.
3. Up to ``max_turns`` (default 8) turns; on parse failure we fall
   back to the strongest expert worker.

Prompted-mode pipeline:

1. Orchestrator (cloud) reads question + numbered worker pool.
2. Each turn it emits ``{"action": "call_worker", "worker_id": int,
   "input": str}`` or ``{"action": "final_answer", "answer": str}``.
3. Up to ``max_turns`` (default 6) calls before forcing a final-answer
   prompt; fallback to strongest worker on parse failure.

Workers come from ``cfg["workers"]`` or a sensible default pool (local
Qwen if vLLM up, plus provider-native web search, the configured frontier
cloud model, and gpt-5-mini).
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openjarvis.agents._stubs import AgentContext
from openjarvis.agents.hybrid._base import (
    ANTHROPIC_WEB_SEARCH_TOOL,
    GEMINI_SEARCH_COST_PER_CALL,
    OPENAI_WEB_SEARCH_COST_PER_CALL,
    WEB_SEARCH_COST_PER_CALL,
    LocalCloudAgent,
    tavily_search_context,
)
from openjarvis.agents.hybrid._prices import (
    PRICES,
    is_gpt5_family,
    supports_temperature,
)
from openjarvis.agents.hybrid.mini_swe_agent import (
    _clone_repo,
    _extract_diff,
    run_swe_agent_loop,
)
from openjarvis.agents.hybrid.toolorchestra_pools import (  # noqa: F401 — re-exported for existing imports
    _DEFAULT_WEB_SEARCH_MODEL,
    _PAPER_CODER_OPENROUTER,
    _PAPER_GENERALIST_TIER3_OPENROUTER,
    _TOOLORCH_SEARCH_TYPES,
    _TOOLORCH_VALID_TYPES,
    _default_pool,
    _expert_for,
    _paper_expert_for,
    _paper_pool,
    _resolve_worker_pool,
)
from openjarvis.core.registry import AgentRegistry

ORCHESTRATOR_SYS = """\
You are a tool-orchestrating agent. You coordinate a pool of workers to answer the user's question. Each turn you MUST emit exactly one JSON object — no prose, no markdown fences — taking one of two forms:

  {"action": "call_worker", "worker_id": <int>, "input": "<question or instruction for that worker>"}

  {"action": "final_answer", "answer": "<final answer to the user, respecting the question's answer-format rules>"}

Strategy:

- Call cheap / specialized workers first (small local model for extraction or arithmetic on given data; web_search for unknowns; specialist LLMs for code/math).
- Call the frontier worker (Opus / GPT-5) sparingly, for hard reasoning or a final synthesis pass.
- Stop and emit `final_answer` as soon as the previous worker output is sufficient. Do NOT call a worker just to paraphrase.
- The user only sees the `answer` field of `final_answer`, so make sure it follows any answer-format rules in the question.
"""

FORCE_FINAL_PROMPT = (
    "Worker-call budget exhausted. Emit `final_answer` now using everything "
    "you've learned. Respect the question's answer-format rules."
)


# ============================================================================
# RL-mode constants (Orchestrator-8B, paper-faithful).
# ============================================================================
#
# Verbatim copies of the upstream system prompt / user-prompt template / tools
# from `external/ToolOrchestra/evaluation/eval_hle.py` + `tools.json`. Don't
# edit the description text — Orchestrator-8B was RL-trained against this
# exact wording and pricing/latency table.

RL_ORCHESTRATOR_SYS = "You are good at using tools."

RL_TOOLS_SPEC: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "enhance_reasoning",
            "description": "tool to enhance answer model reasoning. analyze the problem, write code, execute it and return intermidiate results that will help solve the problem",
            "parameters": {
                "properties": {
                    "model": {
                        "description": "The model used to reason. Choices: ['reasoner-1', 'reasoner-2', 'reasoner-3']. reasoner-1 demonstrates strong understanding and reasoning capabilities, which usually provides reliable insights. reasoner-2 can analyze some problems, but could hallucinate and make mistakes in difficult scenarios. reasoner-3 can reason over the context and reveal the logic. \nModel | price per million input tokens | price per million output tokens | average latency\nreasoner-1 | $1.25 | $10 | 31s\nreasoner-2 | $0.25 | $2 | 25s\nreasoner-3 | $0.8 | $0.8 | 9s",
                        "type": "string",
                    }
                },
                "required": ["model"],
                "title": "parameters",
                "type": "object",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer",
            "description": "give the final answer. Not allowed to call if documents is empty.",
            "parameters": {
                "properties": {
                    "model": {
                        "description": "The model used to answer. Choices: ['answer-1', 'answer-2', 'answer-3', 'answer-4', 'answer-math-1', 'answer-math-2']. answer-1 exhibits strong functional calling abilities and performs excellent in most domains (math, physics, social science, etc.). answer-2 presents reasonable solutions in some tasks, but could get stuck in complex reasoning and specific domain knowledge. answer-3 could solve easy to medium tasks, but is not capable of tackling tasks with strong expertise and long-horizon planning. answer-4 demonstrates basic capability: it can understand basic instructions, do simple steps, yet it sometimes misreads details, mixes concepts. answer-math-1 can solve moderate (middle school) math problem, though it becomes incapable in more difficult tasks. answer-math-2 can follow simple instructions and perform easy (primary-level) math problems, but struggle in more complex logic. The table below shows the pricing and latency of each model:\nModel | price per million input tokens | price per million output tokens | average latency\nanswer-1 | $1.25 | $10 | 96s\nanswer-2 | $0.25 | $2 | 27s\nanswer-3 | $0.9 | $0.9 | 15s\nanswer-4 | $0.8 | $0.8 | 11s\nanswer-math-1 | $0.9 | $0.9 | 13s\nanswer-math-2 | $$0.2 | $0.2 | 9s",
                        "type": "string",
                    }
                },
                "required": ["model"],
                "title": "parameters",
                "type": "object",
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for missing information",
            "parameters": {
                "properties": {
                    "model": {
                        "description": "The model used to search for missing information. Choices: ['search-1', 'search-2', 'search-3']. search-1 usually identifies the missing information and can write concise queries for effective search. search-2 can reason over the context and write queries to find the missing content for answering questions. search-3 can also write queries to find information. The table below shows the pricing and latency:\nModel | price per million input tokens | price per million output tokens | average latency\nsearch-1 | $1.25 | $10 | 22s\nsearch-2 | $0.25 | $2 | 16s\nsearch-3 | $0.8 | $0.8 | 8s",
                        "type": "string",
                    }
                },
                "required": ["model"],
                "title": "parameters",
                "type": "object",
            },
        },
    },
]

# RL_ALL_TOOLS: argument-validation schema (mirrors eval_hle.py:104).
RL_ALL_TOOLS: Dict[str, Dict[str, List[str]]] = {
    "enhance_reasoning": {"model": ["reasoner-1", "reasoner-2", "reasoner-3"]},
    "answer": {
        "model": [
            "answer-1",
            "answer-2",
            "answer-3",
            "answer-4",
            "answer-math-1",
            "answer-math-2",
        ],
    },
    "search": {"model": ["search-1", "search-2", "search-3"]},
}

# Map the orchestrator's `model` slot to a concrete OpenJarvis worker spec.
# Tiers ranked by the upstream tools.json table (`*-1` = frontier,
# `*-2` = mid, `*-3` = local). math-1 / math-2 collapse onto the same
# tiers since we don't have Qwen-Math served.
#
# Each entry is a callable `(local_model, local_endpoint, cloud_model) -> worker_dict`
# so the substitution is deferred until we know the cell's resolved local/cloud
# pair. Worker dicts share the schema validated by `_resolve_worker_pool`.


# ============================================================================
# Paper-match expert mapping (2026-05-19).
# ============================================================================
# Maps the orchestrator's `model` slot to a paper-match worker spec. Differs
# from `_expert_for` in that it pulls in OpenRouter-hosted code/math/generalist
# models and routes `search` through Tavily, while `enhance_reasoning` is
# expected to produce code that the caller pipes through a Modal sandbox
# (handled at dispatch time, not here).
#
# Slot map (paper-faithful where we can; substitutions noted in toolorchestra
# paper-match docs `docs/26.5.19/toolorchestra-papermatch.md`):
#
#   reasoner-1 -> GPT-5 (frontier reasoner)
#   reasoner-2 -> GPT-5-mini (mid)
#   reasoner-3 -> local Qwen (Orchestrator-8B endpoint also serves this)
#   answer-1   -> GPT-5
#   answer-2   -> GPT-5-mini
#   answer-3   -> Llama-3.3-70B (OpenRouter, generalist tier-3 per spec)
#   answer-4   -> local Qwen
#   answer-math-1 -> Qwen-2.5-Coder-32B via OpenRouter
#                    (paper uses Qwen-2.5-Math-72B; not on OpenRouter — see doc)
#   answer-math-2 -> Qwen-2.5-Coder-32B via OpenRouter
#                    (paper uses Qwen-2.5-Math-7B; not on OpenRouter — see doc)
#   search-*   -> Tavily search (paper)
#
# `enhance_reasoning` is dispatched through the coder specialist regardless of
# slot tier — the orchestrator emits one of `reasoner-{1,2,3}` and the caller
# routes the same way in all three cases, then optionally extracts a python
# code block and execs it in Modal. (We keep the slot-aware routing inside the
# `reasoner-*` map above for parity, but the `enhance_reasoning` tool itself
# pins the coder regardless. See `_run_rl_paper` dispatch.)


# ---- Tavily + Modal helpers -------------------------------------------------


def _call_tavily_search(
    query: str,
    max_results: int = 5,
) -> Tuple[str, int, int, float, int]:
    """One-shot Tavily search. Returns (text, p_tok=0, c_tok=0, cost, uses).

    Token counts are reported as zero (no LLM was billed); the OpenJarvis
    accounting layer separately tallies tool-call counts. Falls back to
    DuckDuckGo if Tavily is unreachable (see ``WebSearchTool``).
    """
    res = tavily_search_context(query, max_results=max_results)
    return res["text"], 0, 0, float(res["cost_usd"]), int(res["n_searches"])


_MODAL_APP_NAME = "openjarvis-toolorchestra-sandbox"


def _call_modal_python(code: str, timeout_s: int = 60) -> Tuple[str, int]:
    """Execute a single Python snippet in a fresh Modal Sandbox.

    Returns ``(combined_stdout_stderr, returncode)``. Logs are capped at 8 KiB.
    Any exception (modal auth, network, sandbox boot failure) is captured into
    the returned string with a non-zero rc — we never raise back to the
    orchestrator loop. The sandbox is torn down at the end via ``terminate()``.
    """
    try:
        import modal

        app = modal.App.lookup(_MODAL_APP_NAME, create_if_missing=True)
        # python:3.12-slim is small + boots fast; the paper uses a generic
        # Python image too. We rely on stdlib only — no extra pip installs.
        image = modal.Image.debian_slim(python_version="3.12")
        sb = modal.Sandbox.create(
            "python",
            "-c",
            code,
            app=app,
            image=image,
            timeout=int(timeout_s),
        )
        sb.wait()
        try:
            out = sb.stdout.read() or ""
        except Exception:
            out = ""
        try:
            err = sb.stderr.read() or ""
        except Exception:
            err = ""
        rc = sb.returncode if sb.returncode is not None else -1
        try:
            sb.terminate()
        except Exception:
            pass
        combined = out + (("\n" + err) if err else "")
        if len(combined) > 8192:
            combined = combined[:8192] + "\n... (output truncated)"
        return combined, int(rc)
    except Exception as exc:
        return f"[modal-python error: {type(exc).__name__}: {exc}]", -1


_PY_CODE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def _extract_first_python_block(text: str) -> Optional[str]:
    """Return the first ```python ... ``` block (or ```...```), or None."""
    m = _PY_CODE_RE.search(text or "")
    return m.group(1).strip() if m else None


def _call_orchestrator_with_tool_calls(
    model: str,
    endpoint: str,
    *,
    user: str,
    system: str,
    max_tokens: int,
    temperature: float,
    tools: List[Dict[str, Any]],
    timeout: float = 600.0,
) -> Tuple[str, int, int, Any]:
    """Orchestrator-aware vLLM call. Returns (text, p_tok, c_tok, tool_calls).

    Mirrors ``LocalCloudAgent._call_vllm`` but ALSO surfaces the SDK-level
    ``tool_calls`` object so the RL-mode parser can match against it
    directly. Otherwise vLLM's tool parser silently swallows the tool call
    into the SDK field while leaving ``content == ''`` — and the text-tag
    parser sees nothing, falling through to the answer-1 fallback. (Bug
    observed 2026-05-19 on the paper-match smoke; same path was buggy on
    the default pool too, just less reproducibly.)
    """
    from openai import OpenAI

    client = OpenAI(base_url=endpoint, api_key="EMPTY", timeout=timeout)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    choice = resp.choices[0]
    message = choice.message
    text = message.content or ""
    tool_calls = getattr(message, "tool_calls", None)
    u = resp.usage
    p = getattr(u, "prompt_tokens", 0) if u else 0
    c = getattr(u, "completion_tokens", 0) if u else 0
    return text, p, c, tool_calls


# Regex for ``<tool_call>{...}</tool_call>`` blocks emitted by Orchestrator-8B
# when the vLLM tool parser doesn't catch them (e.g. `qwen3_xml` parser on a
# hermes-style template). Captures the JSON payload.
_TOOL_CALL_TAG_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _parse_rl_tool_call(content: str, sdk_tool_calls: Any) -> Optional[Dict[str, Any]]:
    """Return ``{"name": str, "arguments": dict}`` or None.

    Prefers the SDK-level ``tool_calls`` (when vLLM's parser matched), falls
    back to scraping ``<tool_call>{...}</tool_call>`` tags from the raw
    content. We take the first tool call only — Orchestrator-8B was trained
    to emit exactly one per turn.
    """
    # SDK-level path.
    if sdk_tool_calls:
        first = sdk_tool_calls[0]
        name = getattr(getattr(first, "function", None), "name", None)
        args_raw = getattr(getattr(first, "function", None), "arguments", None) or "{}"
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            args = {}
        if isinstance(name, str) and isinstance(args, dict):
            return {"name": name, "arguments": args}
    # Text-tag fallback.
    if not isinstance(content, str):
        return None
    m = _TOOL_CALL_TAG_RE.search(content)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name")
    args = obj.get("arguments", {})
    if not isinstance(name, str) or not isinstance(args, dict):
        return None
    return {"name": name, "arguments": args}


def _build_pool_block(workers: List[Dict[str, Any]]) -> str:
    return "\n".join(
        f"Worker {w['id']} ({w['name']}): {w['description']}" for w in workers
    )


def _build_user_prompt(
    question: str,
    workers: List[Dict[str, Any]],
    history: List[Dict[str, Any]],
) -> str:
    pieces = [
        f"Worker pool:\n{_build_pool_block(workers)}",
        f"User question:\n{question}",
    ]
    if history:
        pieces.append("Conversation so far (orchestrator turns and worker outputs):")
        for h in history:
            if h["role"] == "orchestrator":
                pieces.append(f"[Orchestrator turn {h['turn']}]\n{h['raw']}")
            else:
                pieces.append(
                    f"[Worker {h['worker_id']} ({h['worker_name']}) turn {h['turn']}]\n"
                    f"{h['output']}"
                )
    pieces.append(
        "Emit the next JSON action object now — exactly one object, no prose."
    )
    return "\n\n".join(pieces)


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return s


def _parse_action(text: str) -> Optional[Dict[str, Any]]:
    s = _strip_fences(text)
    # First try direct parse, then balanced-brace extraction.
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "action" in obj:
            return obj
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start : i + 1])
                    if isinstance(obj, dict) and "action" in obj:
                        return obj
                except json.JSONDecodeError:
                    return None
    return None


def _extract_final_answer_text(text: str) -> str:
    """Best-effort: pull the answer string from a malformed action emission.

    Tries `"answer": "..."` regex, then the GAIA-style `FINAL ANSWER:` line.
    """
    m = re.search(r'"answer"\s*:\s*"((?:\\.|[^"\\])*)"', text, re.DOTALL)
    if m:
        # Decode JSON escapes without mangling non-ASCII text (a plain
        # ``unicode_escape`` decode turns "café" into "cafÃ©").
        try:
            return json.loads(f'"{m.group(1)}"')
        except json.JSONDecodeError:
            return m.group(1)
    m = re.search(r"FINAL\s*ANSWER\s*:\s*(.+?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if m:
        return m.group(1).strip()
    return text.strip()


# ---------- Worker pool ----------


def _call_worker(
    worker: Dict[str, Any], prompt: str, cfg: Dict[str, Any]
) -> Tuple[str, int, int, bool, float, int]:
    """Returns (text, p_tok, c_tok, is_local, extra_cost, n_web_searches)."""
    wtype = worker.get("type", "openai")
    max_tok = int(cfg.get("worker_max_tokens", 4096))
    temp = float(cfg.get("worker_temperature", 0.2))

    if wtype == "vllm":
        text, p, c = LocalCloudAgent._call_vllm(
            worker["model"],
            worker["base_url"],
            user=prompt,
            max_tokens=max_tok,
            temperature=temp,
            enable_thinking=False,
        )
        return text, p, c, True, 0.0, 0
    if wtype == "openai":
        is_gpt5 = is_gpt5_family(worker["model"])
        eff_temp = 1.0 if is_gpt5 else temp
        # GPT-5 is a reasoning model: hidden reasoning tokens count against
        # `max_completion_tokens`, so a 4096 cap can be fully consumed by
        # reasoning and leave 0 visible content (empty answer). Give the
        # reasoning headroom on top of the answer budget.
        eff_max_tok = max(max_tok, 16384) if is_gpt5 else max_tok
        text, p, c = LocalCloudAgent._call_openai(
            worker["model"],
            user=prompt,
            max_tokens=eff_max_tok,
            temperature=eff_temp,
        )
        return text, p, c, False, 0.0, 0
    if wtype == "gemini":
        text, p, c = LocalCloudAgent._call_gemini(
            worker["model"],
            user=prompt,
            max_tokens=max_tok,
            temperature=temp,
        )
        return text, p, c, False, 0.0, 0
    if wtype == "anthropic":
        eff_temp = temp if supports_temperature(worker["model"]) else 0.0
        text, p, c, _ = LocalCloudAgent._call_anthropic(
            worker["model"],
            user=prompt,
            max_tokens=max_tok,
            temperature=eff_temp,
        )
        return text, p, c, False, 0.0, 0
    if wtype == "anthropic-web-search":
        eff_temp = temp if supports_temperature(worker["model"]) else 0.0
        text, p, c, n_searches = LocalCloudAgent._call_anthropic(
            worker["model"],
            user=prompt,
            max_tokens=max_tok,
            temperature=eff_temp,
            tools=[ANTHROPIC_WEB_SEARCH_TOOL],
            tool_choice={"type": "any"},
        )
        extra = n_searches * WEB_SEARCH_COST_PER_CALL
        return text, p, c, False, extra, n_searches
    if wtype == "openai-web-search":
        eff_temp = 1.0 if is_gpt5_family(worker["model"]) else temp
        text, p, c, n_searches, _ = LocalCloudAgent._call_openai_agent(
            worker["model"],
            user=prompt,
            max_tokens=max(max_tok, 16384)
            if is_gpt5_family(worker["model"])
            else max_tok,
            temperature=eff_temp,
        )
        extra = n_searches * OPENAI_WEB_SEARCH_COST_PER_CALL
        return text, p, c, False, extra, n_searches
    if wtype == "gemini-web-search":
        text, p, c, n_searches, _ = LocalCloudAgent._call_gemini_agent(
            worker["model"],
            user=prompt,
            max_tokens=max_tok,
            temperature=temp,
        )
        extra = n_searches * GEMINI_SEARCH_COST_PER_CALL
        return text, p, c, False, extra, n_searches
    if wtype == "tavily-search":
        max_results = int(cfg.get("tavily_max_results", 5))
        text, p, c, extra, n_searches = _call_tavily_search(
            str(prompt),
            max_results=max_results,
        )
        return text, p, c, False, extra, n_searches
    if wtype == "openrouter":
        text, p, c = LocalCloudAgent._call_openrouter(
            worker["model"],
            user=prompt,
            max_tokens=max_tok,
            temperature=temp,
        )
        return text, p, c, False, 0.0, 0
    if wtype == "modal-python":
        # `prompt` is the python code string to exec.
        timeout_s = int(cfg.get("modal_python_timeout_s", 60))
        out, _rc = _call_modal_python(str(prompt), timeout_s=timeout_s)
        # No LLM tokens consumed; report 0 in/out. Cost is whatever Modal
        # charges per sandbox-second — not tracked here.
        return out, 0, 0, False, 0.0, 0
    raise ValueError(f"unsupported worker type: {wtype!r}")


def _swe_call_worker(
    worker: Dict[str, Any],
    prompt: str,
    cfg: Dict[str, Any],
    task: Dict[str, Any],
    workdir: Path,
    turn: int,
) -> Tuple[str, int, int, bool, float, int, int]:
    """SWE-bench worker dispatch: route solver workers through
    run_swe_agent_loop on a shared workdir. Web-search workers fall back
    to the regular one-shot dispatch (search isn't an agent loop).

    Trailing ``bash_turns`` (last element) counts agent-loop turns so the
    caller can surface ``tool_calls`` per row. Fallbacks to one-shot
    workers return 0 bash turns (no agent loop ran)."""
    wtype = worker.get("type", "openai")
    if wtype in _TOOLORCH_SEARCH_TYPES:
        # Search workers stay one-shot.
        text, p, c, is_local, extra, n_searches = _call_worker(worker, prompt, cfg)
        return text, p, c, is_local, extra, n_searches, 0
    if wtype == "vllm":
        backbone = "local"
        endpoint = worker.get("base_url")
        loop_cloud_endpoint = "anthropic"  # unused when backbone=local
    elif wtype in ("anthropic", "openai", "gemini"):
        backbone = "cloud"
        endpoint = None
        loop_cloud_endpoint = wtype
    else:
        # Unknown type — one-shot fallback.
        text, p, c, is_local, extra, n_searches = _call_worker(worker, prompt, cfg)
        return text, p, c, is_local, extra, n_searches, 0
    out = run_swe_agent_loop(
        task,
        backbone=backbone,
        backbone_model=worker["model"],
        cloud_endpoint=loop_cloud_endpoint,
        local_endpoint=endpoint,
        initial_prompt=prompt,
        max_turns=int(cfg.get("swe_max_turns", 30)),
        bash_timeout=int(cfg.get("swe_bash_timeout_s", 120)),
        output_cap=int(cfg.get("swe_output_cap", 10_000)),
        turn_max_tokens=int(cfg.get("swe_turn_max_tokens", 4096)),
        trace_prefix=f"toolorch_turn{turn}",
        workdir=workdir,
    )
    is_local = backbone == "local"
    return (
        out["final_summary"] or out["answer"],
        out["tokens_in"],
        out["tokens_out"],
        is_local,
        0.0,
        0,
        int(out["turns"]),
    )


# The RL (paper) loop lives in its own module; it looks helpers up here.
from openjarvis.agents.hybrid.toolorchestra_rl import PaperOrchestratorMixin  # noqa: E402,I001


@AgentRegistry.register("toolorchestra")
class ToolOrchestraAgent(PaperOrchestratorMixin, LocalCloudAgent):
    """Multi-turn dispatcher over a mixed worker pool.

    Two modes (see module docstring): ``method_cfg.orchestrator_mode``
    is ``"prompted"`` (default, cloud-as-orchestrator) or ``"rl"``
    (paper-faithful, drives ``nvidia/Orchestrator-8B`` on a local vLLM).
    """

    agent_id = "toolorchestra"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Validate `method_cfg.worker_pool` early — surfaces config errors
        # at agent construction rather than on the first task. No-op when
        # the override is absent.
        if self._cfg.get("worker_pool") is not None:
            _resolve_worker_pool(
                self._cfg,
                self._local_model,
                self._local_endpoint,
                self._cloud_model,
                self._cloud_endpoint,
            )
        # Validate `orchestrator_mode` (typo-checked here, not on first task).
        mode = str(self._cfg.get("orchestrator_mode", "prompted")).lower()
        if mode not in ("prompted", "rl"):
            raise ValueError(
                f"toolorchestra: orchestrator_mode must be 'prompted' or 'rl'; "
                f"got {mode!r}"
            )

    @staticmethod
    def _worker_required_capabilities(
        worker: Dict[str, Any],
        *,
        swe_mode: bool = False,
    ) -> List[str]:
        """Return direct-operation capabilities for one concrete dispatch."""
        worker_type = str(worker.get("type", worker.get("endpoint", "openai"))).lower()
        if worker_type in _TOOLORCH_SEARCH_TYPES:
            return ["network:fetch"]
        if swe_mode:
            return ["code:execute", "file:read", "file:write"]
        if worker_type == "modal-python":
            return ["code:execute"]
        return []

    def _call_worker_secured(
        self,
        worker: Dict[str, Any],
        prompt: str,
        cfg: Dict[str, Any],
    ) -> Tuple[str, int, int, bool, float, int]:
        """Gate the selected worker immediately before its direct action."""
        required = self._worker_required_capabilities(worker)
        if required:
            authorization = self._authorize_direct_operation(
                required,
                operation="toolorchestra_worker",
            )
            if not authorization.success:
                return authorization.content, 0, 0, False, 0.0, 0
        return _call_worker(worker, prompt, cfg)

    def _swe_call_worker_secured(
        self,
        worker: Dict[str, Any],
        prompt: str,
        cfg: Dict[str, Any],
        task: Dict[str, Any],
        workdir: Path,
        turn: int,
    ) -> Tuple[str, int, int, bool, float, int, int]:
        """Gate a selected SWE/search worker immediately before dispatch."""
        worker_type = str(worker.get("type", "openai")).lower()
        required = self._worker_required_capabilities(
            worker,
            swe_mode=worker_type not in _TOOLORCH_SEARCH_TYPES,
        )
        if required:
            authorization = self._authorize_direct_operation(
                required,
                operation="toolorchestra_swe_worker",
            )
            if not authorization.success:
                return authorization.content, 0, 0, False, 0.0, 0, 0
        return _swe_call_worker(worker, prompt, cfg, task, workdir, turn)

    def _call_modal_python_secured(
        self,
        code: str,
        *,
        timeout_s: int,
    ) -> Tuple[str, int]:
        """Gate generated Python immediately before sandbox execution."""
        authorization = self._authorize_direct_operation(
            ["code:execute"],
            operation="toolorchestra_modal_python",
        )
        if not authorization.success:
            return authorization.content, -1
        return _call_modal_python(code, timeout_s=timeout_s)

    def _run_paradigm(
        self,
        input: str,
        context: Optional[AgentContext],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        mode = str(self._cfg.get("orchestrator_mode", "prompted")).lower()
        if mode == "rl":
            return self._run_rl(input, context, **kwargs)
        return self._run_prompted(input, context, **kwargs)

    def _required_capabilities_for_run(
        self,
        context: Optional[AgentContext],
    ) -> List[str]:
        """Cover the concrete workers/actions exposed by this run.

        ToolOrchestra's default pool contains a hosted-search worker even
        when ``search_backend`` is not ``tavily``.  RL paper mode additionally
        exposes Tavily and generated Python in Modal.  Deriving from those
        actual action types keeps the gate aligned with dispatch behavior.
        """
        required = super()._required_capabilities_for_run(context)
        mode = str(self._cfg.get("orchestrator_mode", "prompted")).lower()
        if mode == "rl":
            # Both the default expert mapping and the paper mapping expose a
            # search action; paper mode also executes generated Python.
            required.append("network:fetch")
            if str(self._cfg.get("pool", "")).lower() == "paper":
                required.append("code:execute")
            return list(dict.fromkeys(required))

        workers = self._cfg.get("workers")
        if not workers:
            workers = _resolve_worker_pool(
                self._cfg,
                self._local_model,
                self._local_endpoint,
                self._cloud_model,
                self._cloud_endpoint,
            )
        worker_types = {
            str(worker.get("type", worker.get("endpoint", "openai"))).lower()
            for worker in workers
            if isinstance(worker, dict)
        }
        if worker_types.intersection(_TOOLORCH_SEARCH_TYPES):
            required.append("network:fetch")
        if "modal-python" in worker_types:
            required.append("code:execute")
        return list(dict.fromkeys(required))

    # ------------------------------------------------------------------
    # Legacy prompted-orchestrator path.
    # ------------------------------------------------------------------
    def _run_prompted(
        self,
        input: str,
        context: Optional[AgentContext],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        cfg = self._cfg
        question = input
        # Resolution order (strict replace, no merge):
        #   1. `cfg["workers"]` — legacy direct override, used by tests.
        #   2. `cfg["worker_pool"]` — cell-config override; validated +
        #      $local/$cloud substituted.
        #   3. `_default_pool(...)` — heterogeneous default.
        if cfg.get("workers"):
            workers = cfg["workers"]
        else:
            workers = _resolve_worker_pool(
                cfg,
                self._local_model,
                self._local_endpoint,
                self._cloud_model,
                self._cloud_endpoint,
            )
        if not workers:
            raise RuntimeError("toolorchestra: empty worker pool")

        max_turns = int(cfg.get("max_turns", 6))
        orch_max_tokens = int(cfg.get("orchestrator_max_tokens", 1024))

        task_meta = (context.metadata.get("task") if context is not None else {}) or {}
        swe_mode = (
            bool(cfg.get("swe_use_agent_loop"))
            and bool(task_meta.get("problem_statement"))
            and bool(task_meta.get("repo"))
            and bool(task_meta.get("base_commit"))
        )
        shared_workdir: Optional[Path] = None
        if swe_mode:
            shared_workdir = Path(
                tempfile.mkdtemp(
                    prefix=f"toolorch-swe-{task_meta.get('task_id', 'x')}-"
                )
            )
            try:
                _clone_repo(task_meta["repo"], task_meta["base_commit"], shared_workdir)
            except Exception:
                shutil.rmtree(shared_workdir, ignore_errors=True)
                raise
            self.record_trace_event(
                {
                    "kind": "toolorchestra_swe_workdir",
                    "workdir": str(shared_workdir),
                    "repo": task_meta["repo"],
                    "base_commit": task_meta["base_commit"],
                }
            )

        # try/finally guards ``shared_workdir`` against exceptions raised
        # anywhere in the turn loop, the worker calls, the fallback, or
        # the diff-extraction step. Without this, at n=500 SWE-bench an
        # exception leaves hundreds of MB of cloned repos in tempdir.
        try:
            history: List[Dict[str, Any]] = []
            tokens_local = 0
            tokens_cloud = 0
            cost = 0.0
            n_web_searches_total = 0
            # tool_calls: bash turns from SWE subloops + web_search uses
            # from GAIA. Orchestrator dispatch turns are NOT counted (they
            # produce text only — calling a worker is one tool call's worth
            # of "delegation" but the actual tool action happens inside).
            tool_calls = 0
            final_answer: Optional[str] = None
            forced_final = False
            parse_failures = 0

            for turn in range(1, max_turns + 1):
                sys_prompt = ORCHESTRATOR_SYS
                if turn == max_turns and final_answer is None:
                    sys_prompt = ORCHESTRATOR_SYS + "\n\n" + FORCE_FINAL_PROMPT
                    forced_final = True

                user = _build_user_prompt(question, workers, history)
                text, o_in, o_out = self._call_cloud(
                    user=user,
                    system=sys_prompt,
                    max_tokens=orch_max_tokens,
                    temperature=0.0,
                )
                tokens_cloud += o_in + o_out
                cost += self.cost_usd(self._cloud_model, o_in, o_out)

                action = _parse_action(text)
                history.append(
                    {
                        "role": "orchestrator",
                        "turn": turn,
                        "raw": text,
                        "action": action,
                    }
                )
                self.record_trace_event(
                    {
                        "kind": "toolorchestra_action",
                        "turn": turn,
                        "action": action,
                        "raw": text,
                    }
                )

                if action is None:
                    parse_failures += 1
                    if parse_failures >= 2 or forced_final:
                        final_answer = _extract_final_answer_text(text)
                        break
                    continue

                kind = action.get("action")
                if kind == "final_answer":
                    final_answer = str(action.get("answer", "")).strip()
                    break
                if kind == "call_worker":
                    wid = action.get("worker_id")
                    w_input = action.get("input", "")
                    if not isinstance(wid, int) or not (0 <= wid < len(workers)):
                        parse_failures += 1
                        if parse_failures >= 2 or forced_final:
                            final_answer = _extract_final_answer_text(text)
                            break
                        continue
                    worker = workers[wid]
                    if swe_mode and shared_workdir is not None:
                        (
                            w_text,
                            w_in,
                            w_out,
                            is_local,
                            extra_cost,
                            n_searches,
                            bash_turns,
                        ) = self._swe_call_worker_secured(
                            worker,
                            str(w_input),
                            cfg,
                            task_meta,
                            shared_workdir,
                            turn,
                        )
                        tool_calls += bash_turns
                    else:
                        w_text, w_in, w_out, is_local, extra_cost, n_searches = (
                            self._call_worker_secured(worker, str(w_input), cfg)
                        )
                    if is_local:
                        tokens_local += w_in + w_out
                    else:
                        tokens_cloud += w_in + w_out
                        cost += self.cost_usd(worker["model"], w_in, w_out) + extra_cost
                    n_web_searches_total += n_searches
                    tool_calls += n_searches
                    history.append(
                        {
                            "role": "worker",
                            "turn": turn,
                            "worker_id": wid,
                            "worker_name": worker["name"],
                            "worker_model": worker["model"],
                            "output": w_text,
                            "tokens_in": w_in,
                            "tokens_out": w_out,
                            "n_web_searches": n_searches,
                        }
                    )
                    continue
                # Unknown action kind — treat as parse failure.
                parse_failures += 1

            if final_answer is None:
                # Hard fallback: call the strongest non-search worker directly.
                # "Strongest" = highest output-token price in `_prices.PRICES`,
                # which tracks model capability tier closely enough for this.
                # Search workers are excluded — they answer fact-lookup
                # questions, not synthesis.
                non_search = [
                    w for w in workers if w.get("type") not in _TOOLORCH_SEARCH_TYPES
                ] or workers
                worker = max(
                    non_search,
                    key=lambda w: PRICES.get(w.get("model", ""), (0.0, 0.0))[1],
                )
                if swe_mode and shared_workdir is not None:
                    (ans, w_in, w_out, is_local, extra_cost, _, bash_turns) = (
                        self._swe_call_worker_secured(
                            worker,
                            question,
                            cfg,
                            task_meta,
                            shared_workdir,
                            max_turns + 1,
                        )
                    )
                    tool_calls += bash_turns
                else:
                    ans, w_in, w_out, is_local, extra_cost, _ = (
                        self._call_worker_secured(worker, question, cfg)
                    )
                if is_local:
                    tokens_local += w_in + w_out
                else:
                    tokens_cloud += w_in + w_out
                    cost += self.cost_usd(worker["model"], w_in, w_out) + extra_cost
                history.append(
                    {
                        "role": "worker",
                        "turn": max_turns + 1,
                        "worker_id": worker["id"],
                        "worker_name": worker["name"],
                        "worker_model": worker["model"],
                        "output": ans,
                        "tokens_in": w_in,
                        "tokens_out": w_out,
                        "fallback": True,
                    }
                )
                final_answer = ans

            # In SWE mode, the authoritative output is the working-tree diff —
            # frame it (the runner extracts it via the scorer's ```diff fence).
            if swe_mode and shared_workdir is not None:
                patch = _extract_diff(shared_workdir)
                if patch.strip():
                    final_answer = (
                        f"{final_answer}\n\n```diff\n{patch}```"
                        if final_answer
                        else f"```diff\n{patch}```"
                    )

            meta = {
                "tokens_local": tokens_local,
                "tokens_cloud": tokens_cloud,
                "cost_usd": cost,
                "turns": len([h for h in history if h["role"] == "orchestrator"]),
                "web_search_uses": n_web_searches_total,
                "tool_calls": int(tool_calls),
                "traces": {
                    "history": history,
                    "forced_final": forced_final,
                    "parse_failures": parse_failures,
                    "workers": workers,
                    "n_web_searches": n_web_searches_total,
                    "note": (
                        "inference-only port; the RL-trained Nemotron-Orchestrator-8B "
                        "is NOT in the loop. Results are preliminary."
                    ),
                },
            }
            return final_answer, meta
        finally:
            if shared_workdir is not None:
                shutil.rmtree(shared_workdir, ignore_errors=True)


__all__ = ["ToolOrchestraAgent"]

"""The mini-SWE agent's local-model loop (vLLM / Ollama tool calling) and its
context management: token estimates and compaction of old turns.

Split out of ``mini_swe_agent.py``; its names are looked up on that module
at call time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import openjarvis.agents.hybrid.mini_swe_agent as _swe


def _get_tiktoken_enc() -> Any:
    global _TIKTOKEN_ENC, _TIKTOKEN_WARNED
    if _TIKTOKEN_ENC is not None:
        return _TIKTOKEN_ENC
    try:
        import tiktoken

        _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        if not _TIKTOKEN_WARNED:
            print(
                f"[mini_swe_agent] tiktoken unavailable ({exc!r}); falling back to len(s)//4",
                flush=True,
            )
            _TIKTOKEN_WARNED = True
        _TIKTOKEN_ENC = False
    return _TIKTOKEN_ENC


def _estimate_prompt_tokens(messages: List[Dict[str, Any]]) -> int:
    enc = _swe._get_tiktoken_enc()
    total = 0
    for m in messages:
        total += 4  # per-message overhead
        c = m.get("content")
        if isinstance(c, str):
            s = c
        elif isinstance(c, list):
            parts = []
            for block in c:
                if isinstance(block, dict):
                    parts.append(str(block.get("content") or block.get("text") or ""))
            s = "\n".join(parts)
        else:
            s = ""
        for tc in m.get("tool_calls") or []:
            try:
                s += "\n" + (tc["function"]["arguments"] or "")
                s += "\n" + (tc["function"].get("name") or "")
            except (KeyError, TypeError):
                pass
        tcid = m.get("tool_call_id")
        if tcid:
            s += "\n" + str(tcid)
        if enc:
            total += len(enc.encode(s, disallowed_special=()))
        else:
            total += len(s) // 4
    return total


def _parse_exit_code(content: Any) -> str:
    if not isinstance(content, str):
        return "?"
    for pat in _swe._EXIT_PATTERNS:
        m = pat.search(content)
        if m:
            return m.group(1)
    return "?"


def _identify_turns(messages: List[Dict[str, Any]]) -> List[Tuple[int, int]]:
    """Return list of (start_idx, end_idx_exclusive) for each assistant+tools turn.

    A turn = one assistant message (with or without tool_calls) plus any
    immediately-following tool messages. System + initial user are skipped.
    """
    turns: List[Tuple[int, int]] = []
    i = 0
    n = len(messages)
    while i < n:
        role = messages[i].get("role")
        if role == "assistant":
            j = i + 1
            while j < n and messages[j].get("role") == "tool":
                j += 1
            turns.append((i, j))
            i = j
        else:
            i += 1
    return turns


def _compact_local_messages(
    messages: List[Dict[str, Any]],
    *,
    client: Any,
    model: str,
    keep_last: int,
    trace_prefix: str,
    compact_at_tokens: int = 24_000,
) -> List[Dict[str, Any]]:
    if len(messages) < 2:
        return messages
    system_msg = messages[0]
    initial_user = messages[1]

    turns = _swe._identify_turns(messages)
    if len(turns) <= keep_last:
        return messages

    keep_turns = turns[-keep_last:]
    old_turns = turns[:-keep_last]
    keep_start = keep_turns[0][0]

    # Stage 1: elide tool observations in old turns.
    before_tokens = _swe._estimate_prompt_tokens(messages)
    new_messages: List[Dict[str, Any]] = list(messages)
    n_tool_elided = 0
    for s, e in old_turns:
        for k in range(s, e):
            m = new_messages[k]
            if m.get("role") != "tool":
                continue
            orig = m.get("content")
            if not isinstance(orig, str):
                continue
            n_chars = len(orig)
            if n_chars <= 200:
                continue
            exit_code = _swe._parse_exit_code(orig)
            stub = f"[tool output elided: {n_chars} chars, exit={exit_code}]"
            new_messages[k] = {
                "role": "tool",
                "tool_call_id": m.get("tool_call_id"),
                "content": stub,
            }
            n_tool_elided += 1

    after_stage1_tokens = _swe._estimate_prompt_tokens(new_messages)
    _swe._record_event(
        {
            "kind": f"{trace_prefix}_compact",
            "stage": "1",
            "msgs_before": len(messages),
            "msgs_after": len(new_messages),
            "before_tokens": before_tokens,
            "after_tokens": after_stage1_tokens,
            "n_tool_elided": n_tool_elided,
            "n_turns_folded": 0,
            "ts": _swe.time.time(),
        }
    )

    if after_stage1_tokens <= compact_at_tokens:
        return new_messages

    # Stage 2: fold old turns into a single synthetic system summary.
    middle = new_messages[2:keep_start]
    tail = new_messages[keep_start:]
    if not middle:
        return new_messages

    summary_input = [
        {"role": "system", "content": _swe._COMPACT_PROMPT},
        {
            "role": "user",
            "content": _swe.json.dumps(
                [
                    {
                        "role": m.get("role"),
                        "content": m.get("content")
                        if isinstance(m.get("content"), str)
                        else str(m.get("content"))[:4000],
                    }
                    for m in middle
                ],
                default=str,
            )[:60_000],
        },
    ]
    summary = ""
    try:
        if client is not None:
            resp = client.chat.completions.create(
                model=model,
                messages=summary_input,
                temperature=0.0,
                max_tokens=1024,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            _swe._bump_local_calls()
            summary = (resp.choices[0].message.content or "").strip()[:2000]
    except Exception as exc:
        summary = f"[compaction summary failed: {exc!r}; older turns dropped]"
    if not summary:
        summary = "[no summary produced; older turns dropped]"

    n_turns_folded = len(old_turns)
    synthetic = {
        "role": "system",
        "content": f"[turns 1–{n_turns_folded} elided: {summary}]",
    }
    folded = [system_msg, initial_user, synthetic, *tail]
    after_stage2_tokens = _swe._estimate_prompt_tokens(folded)
    _swe._record_event(
        {
            "kind": f"{trace_prefix}_compact",
            "stage": "2",
            "msgs_before": len(new_messages),
            "msgs_after": len(folded),
            "before_tokens": after_stage1_tokens,
            "after_tokens": after_stage2_tokens,
            "n_tool_elided": n_tool_elided,
            "n_turns_folded": n_turns_folded,
            "summary_chars": len(summary),
            "ts": _swe.time.time(),
        }
    )
    return folded


def _loop_local(
    problem: str,
    workdir: Path,
    *,
    model: str,
    endpoint: str,
    max_turns: int,
    bash_timeout: int,
    output_cap: int,
    turn_max_tokens: int,
    trace_prefix: str,
    compact_at_tokens: int = 22_000,
    compact_keep_last: int = 3,
) -> Dict[str, Any]:
    # Qwen-27B has a 32k context. With ``max_tokens=turn_max_tokens`` reserved
    # for output (default 4096) plus ~1k for the bash tool schema + system
    # prompt + format overhead, the practical input ceiling is ~27k. We
    # compact at 22k so there's slack for one more tool result before the
    # next turn's pre-call check fires again. Earlier we used 24k + keep=4
    # but still saw 28k-input 400s on the n=100 SWE sweep (the keep window
    # alone routinely exceeded the budget once bash outputs piled up).
    from openai import OpenAI

    client = OpenAI(base_url=endpoint, api_key="EMPTY", timeout=600.0)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _swe.SYSTEM_PROMPT},
        {"role": "user", "content": problem},
    ]
    tokens_in = 0
    tokens_out = 0
    final_text = ""
    turns = 0
    for turn in range(1, max_turns + 1):
        turns = turn
        if (
            compact_at_tokens > 0
            and _swe._estimate_prompt_tokens(messages) > compact_at_tokens
        ):
            messages = _swe._compact_local_messages(
                messages,
                client=client,
                model=model,
                keep_last=compact_keep_last,
                trace_prefix=trace_prefix,
                compact_at_tokens=compact_at_tokens,
            )
        t0 = _swe.time.time()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0,
                max_tokens=turn_max_tokens,
                tools=[_swe.BASH_TOOL_OPENAI],
                tool_choice="auto",
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except Exception as exc:
            # Emergency compaction on a context-length 400 from vLLM /
            # OpenAI ("maximum context length is N tokens"). Our pre-call
            # estimator can undercount when tool args / tool_call_ids /
            # template overhead spike, so the budget check missed and the
            # server walled the call. Compact aggressively (keep_last=1)
            # and retry once. Re-raise on anything else or on a second
            # failure — the runner records the row as errored.
            from openjarvis.engine._base import looks_like_context_length_error

            msg = str(exc)
            is_ctx = looks_like_context_length_error(msg)
            if not is_ctx:
                raise
            _swe._record_event(
                {
                    "kind": f"{trace_prefix}_emergency_compact",
                    "turn": turn,
                    "error": msg[:300],
                    "tokens_before": _swe._estimate_prompt_tokens(messages),
                    "ts": _swe.time.time(),
                }
            )
            messages = _swe._compact_local_messages(
                messages,
                client=client,
                model=model,
                keep_last=1,
                trace_prefix=trace_prefix,
                compact_at_tokens=max(8_000, compact_at_tokens // 2),
            )
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0,
                max_tokens=turn_max_tokens,
                tools=[_swe.BASH_TOOL_OPENAI],
                tool_choice="auto",
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        _swe._bump_local_calls()
        latency = _swe.time.time() - t0
        u = resp.usage
        tokens_in += getattr(u, "prompt_tokens", 0) if u else 0
        tokens_out += getattr(u, "completion_tokens", 0) if u else 0
        choice = resp.choices[0]
        message = choice.message
        tool_calls = list(getattr(message, "tool_calls", None) or [])
        text = message.content or ""

        _swe._record_event(
            {
                "kind": f"{trace_prefix}_turn",
                "turn": turn,
                "finish_reason": choice.finish_reason,
                "tokens_in": getattr(u, "prompt_tokens", 0) if u else 0,
                "tokens_out": getattr(u, "completion_tokens", 0) if u else 0,
                "latency_s": latency,
                "text": text,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in tool_calls
                ],
                "ts": _swe.time.time(),
            }
        )

        # Match the OpenAI cloud branch: content="" (not None) when only
        # tool_calls are present; omit ``tool_calls`` entirely when there
        # are none (vs. setting it to None) so the message validates
        # against the strict OpenAI schema if it ever gets replayed by
        # the compactor's summarizer call.
        assistant_local_msg: Dict[str, Any] = {
            "role": "assistant",
            "content": text or "",
        }
        if tool_calls:
            assistant_local_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_local_msg)

        if not tool_calls:
            final_text = text.strip()
            break

        for tc in tool_calls:
            try:
                args = _swe.json.loads(tc.function.arguments or "{}")
            except _swe.json.JSONDecodeError:
                args = {}
            if tc.function.name != "bash":
                obs = f"unknown tool: {tc.function.name!r}"
            else:
                command = str(args.get("command", ""))
                result = _swe._run_bash(
                    command,
                    workdir,
                    timeout=bash_timeout,
                    output_cap=output_cap,
                )
                _swe._record_event(
                    {
                        "kind": f"{trace_prefix}_bash",
                        "turn": turn,
                        "command": command,
                        **result,
                        "ts": _swe.time.time(),
                    }
                )
                obs = _swe._format_observation(result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": obs,
                }
            )

    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "turns": turns,
        "final_summary": final_text,
        "max_turns_hit": turns == max_turns and not final_text,
    }


__all__ = [
    "_get_tiktoken_enc",
    "_estimate_prompt_tokens",
    "_parse_exit_code",
    "_identify_turns",
    "_compact_local_messages",
    "_loop_local",
]

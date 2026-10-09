"""Cloud tool-use loops of the mini SWE agent: Anthropic, OpenAI and Gemini,
each driving the same bash tool until the model submits.

Split out of ``mini_swe_agent.py``; its helpers are looked up on that
module at call time, so behaviour (and anything patched there) is
unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import openjarvis.agents.hybrid.mini_swe_agent as _swe


def _loop_cloud_anthropic(
    problem: str,
    workdir: Path,
    *,
    model: str,
    max_turns: int,
    bash_timeout: int,
    output_cap: int,
    turn_max_tokens: int,
    trace_prefix: str,
) -> Dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic(timeout=600.0, max_retries=5)
    messages: List[Dict[str, Any]] = [{"role": "user", "content": problem}]

    tokens_in = 0
    tokens_out = 0
    final_text = ""
    turns = 0
    for turn in range(1, max_turns + 1):
        turns = turn
        kwargs: Dict[str, Any] = {
            "model": model,
            "system": _swe.SYSTEM_PROMPT,
            "max_tokens": turn_max_tokens,
            "tools": [_swe.BASH_TOOL_ANTHROPIC],
            "messages": messages,
        }
        if _swe.supports_temperature(model):
            kwargs["temperature"] = 0.0
        t0 = _swe.time.time()
        msg = client.messages.create(**kwargs)
        _swe._bump_cloud_calls()
        latency = _swe.time.time() - t0
        tokens_in += msg.usage.input_tokens
        tokens_out += msg.usage.output_tokens

        content_blocks: List[Dict[str, Any]] = []
        tool_uses: List[Tuple[str, str, Dict[str, Any]]] = []
        text_parts: List[str] = []
        for block in msg.content:
            btype = getattr(block, "type", None)
            if btype == "tool_use":
                tool_uses.append((block.id, block.name, dict(block.input or {})))
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": dict(block.input or {}),
                    }
                )
            elif hasattr(block, "text"):
                text_parts.append(block.text)
                content_blocks.append({"type": "text", "text": block.text})
            else:
                content_blocks.append({"type": btype or "unknown"})

        _swe._record_event(
            {
                "kind": f"{trace_prefix}_turn",
                "turn": turn,
                "stop_reason": msg.stop_reason,
                "tokens_in": msg.usage.input_tokens,
                "tokens_out": msg.usage.output_tokens,
                "latency_s": latency,
                "content_blocks": content_blocks,
                "ts": _swe.time.time(),
            }
        )

        messages.append(
            {
                "role": "assistant",
                "content": [_swe._anthropic_assistant_block(b) for b in msg.content],
            }
        )

        if not tool_uses:
            final_text = "\n".join(text_parts).strip()
            break

        tool_result_blocks: List[Dict[str, Any]] = []
        for tu_id, tu_name, tu_input in tool_uses:
            if tu_name != "bash":
                obs = f"unknown tool: {tu_name!r}"
                _swe._record_event(
                    {
                        "kind": f"{trace_prefix}_unknown_tool",
                        "turn": turn,
                        "name": tu_name,
                        "input": tu_input,
                        "ts": _swe.time.time(),
                    }
                )
            else:
                command = str(tu_input.get("command", ""))
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
            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu_id,
                    "content": obs,
                }
            )
        messages.append({"role": "user", "content": tool_result_blocks})

    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "turns": turns,
        "final_summary": final_text,
        "max_turns_hit": turns == max_turns and not final_text,
    }


def _loop_cloud_openai(
    problem: str,
    workdir: Path,
    *,
    model: str,
    max_turns: int,
    bash_timeout: int,
    output_cap: int,
    turn_max_tokens: int,
    trace_prefix: str,
) -> Dict[str, Any]:
    """OpenAI Chat Completions multi-turn loop. Mirrors the Anthropic
    branch: each turn the model either calls ``bash`` (one or more parallel
    tool_calls) or produces a no-tool-call final message that terminates
    the loop. The final message's text is returned as ``final_summary``;
    the patch comes from ``git diff`` on the workdir.

    Quirks:
    - GPT-5 family rejects ``temperature`` and uses ``max_completion_tokens``
      instead of ``max_tokens``. We branch on ``is_gpt5_family`` for both.
    - ``tool_calls`` arguments arrive as JSON-string blobs; we tolerate
      malformed JSON by treating it as an empty arg dict (matches the
      ``_loop_local`` behavior).
    """
    from openai import OpenAI

    client = OpenAI(timeout=600.0)

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
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": [_swe.BASH_TOOL_OPENAI],
            "tool_choice": "auto",
        }
        if _swe.is_gpt5_family(model):
            kwargs["max_completion_tokens"] = turn_max_tokens
        else:
            kwargs["max_tokens"] = turn_max_tokens
            kwargs["temperature"] = 0.0
        t0 = _swe.time.time()
        resp = client.chat.completions.create(**kwargs)
        _swe._bump_cloud_calls()
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
                "endpoint": "openai",
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

        # Append the assistant turn (including any tool_calls) so the
        # follow-up tool messages have the right call ids to reference.
        # OpenAI Chat Completions rejects ``content: null`` with a 400
        # ("expected a string, got null") on the next turn when this
        # message gets replayed. Use ``""`` — explicitly allowed by the
        # schema when ``tool_calls`` is present, and equivalent to
        # "assistant had no visible text, only tool calls".
        assistant_msg: Dict[str, Any] = {
            "role": "assistant",
            "content": text or "",
        }
        if tool_calls:
            assistant_msg["tool_calls"] = [
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
        messages.append(assistant_msg)

        if not tool_calls:
            # Silent-truncation recovery: ``finish_reason='length'`` means
            # the response was cut mid-generation. If a tool call was
            # forming when the cap hit, ``tool_calls`` is empty AND ``text``
            # is empty/short — treating that as "model done" exits the loop
            # with a useless empty final_summary (observed on gpt-5-mini SWE
            # cells, 2026-05-15). Inject a one-shot recovery nudge and let
            # the loop continue; only terminate naturally on ``stop``.
            if (
                choice.finish_reason == "length"
                and not text.strip()
                and turn < max_turns
            ):
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was truncated by the token limit "
                            "before producing a tool call or final summary. Retry: "
                            "either issue ONE bash tool call (short command, no large "
                            "output) or send a brief one-line final summary with no "
                            "tool calls to end the loop."
                        ),
                    }
                )
                _swe._record_event(
                    {
                        "kind": f"{trace_prefix}_recover",
                        "turn": turn,
                        "reason": "length_truncation_no_tool_call",
                        "ts": _swe.time.time(),
                    }
                )
                continue
            # No tool call → the model is done. Same termination rule as
            # the Anthropic branch.
            final_text = text.strip()
            break

        for tc in tool_calls:
            try:
                args = _swe.json.loads(tc.function.arguments or "{}")
            except _swe.json.JSONDecodeError:
                args = {}
            if tc.function.name != "bash":
                obs = f"unknown tool: {tc.function.name!r}"
                _swe._record_event(
                    {
                        "kind": f"{trace_prefix}_unknown_tool",
                        "turn": turn,
                        "name": tc.function.name,
                        "input": args,
                        "ts": _swe.time.time(),
                    }
                )
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


def _loop_cloud_gemini(
    problem: str,
    workdir: Path,
    *,
    model: str,
    max_turns: int,
    bash_timeout: int,
    output_cap: int,
    turn_max_tokens: int,
    trace_prefix: str,
) -> Dict[str, Any]:
    """google-genai multi-turn loop (Gemini Developer API, v1.64).

    Tool-use plumbing diverges from OpenAI/Anthropic enough to warrant a
    parallel branch:

    - Parameters must be a Schema-shaped dict with capitalized type names
      ("OBJECT", "STRING"). The lower-case JSON-Schema form is silently
      dropped — the model never produces a call.
    - We explicitly disable ``automatic_function_calling`` so the SDK
      stops at the FunctionCall part and we drive the loop ourselves.
    - Termination heuristic: stop when the model's response has zero
      function_call parts. Same intent as Anthropic ("no tool_use blocks")
      and OpenAI ("empty tool_calls"). Gemini occasionally emits a turn
      with both text and function_call parts; we still treat that as a
      tool turn (matches Anthropic's behavior with mixed content).
    - System prompt goes on the config, not the contents list (Gemini
      convention).
    - The function-response part body is a free-form dict; we wrap the
      bash observation in ``{"output": str}``.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(http_options=types.HttpOptions(timeout=600_000))
    bash_tool = types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="bash",
                description=_swe.BASH_TOOL_ANTHROPIC["description"],
                parameters=_swe.BASH_TOOL_GEMINI_PARAMETERS,
            ),
        ]
    )

    contents: List[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=problem)]),
    ]
    tokens_in = 0
    tokens_out = 0
    final_text = ""
    turns = 0
    for turn in range(1, max_turns + 1):
        turns = turn
        cfg = types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=turn_max_tokens,
            system_instruction=_swe.SYSTEM_PROMPT,
            tools=[bash_tool],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True,
            ),
        )
        t0 = _swe.time.time()
        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=cfg,
        )
        _swe._bump_cloud_calls()
        latency = _swe.time.time() - t0
        um = getattr(resp, "usage_metadata", None)
        p = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
        c = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
        tokens_in += p
        tokens_out += c

        # Pull parts out of the first candidate. Defensive against the
        # zero-candidate / safety-filtered case (returns empty parts and
        # we'll terminate on the next branch).
        cand_parts: List[Any] = []
        try:
            cand_content = resp.candidates[0].content
            cand_parts = list(getattr(cand_content, "parts", None) or [])
        except Exception:
            cand_content = None
            cand_parts = []

        text_parts: List[str] = []
        function_calls: List[Tuple[str, Dict[str, Any]]] = []
        for part in cand_parts:
            fc = getattr(part, "function_call", None)
            if fc is not None:
                fc_args = dict(getattr(fc, "args", None) or {})
                function_calls.append((fc.name, fc_args))
            elif getattr(part, "text", None):
                text_parts.append(part.text)

        finish_reason = None
        try:
            finish_reason = str(resp.candidates[0].finish_reason)
        except Exception:
            pass

        _swe._record_event(
            {
                "kind": f"{trace_prefix}_turn",
                "turn": turn,
                "endpoint": "gemini",
                "finish_reason": finish_reason,
                "tokens_in": p,
                "tokens_out": c,
                "latency_s": latency,
                "text": "\n".join(text_parts),
                "tool_calls": [
                    {"name": name, "arguments": args} for name, args in function_calls
                ],
                "ts": _swe.time.time(),
            }
        )

        # Append the model's content as-is so the next turn sees its own
        # prior function_call parts (Gemini requires this for the
        # function_response to bind).
        if cand_content is not None:
            contents.append(cand_content)
        else:
            # Safety-filtered / empty — synthesize an empty model turn so
            # the conversation stays well-formed and exit the loop.
            contents.append(types.Content(role="model", parts=[]))

        if not function_calls:
            # Silent-failure recovery for Gemini's quirky finish reasons:
            #   MALFORMED_FUNCTION_CALL — model wanted to call bash but
            #     produced unparseable args (24/100 of broken n=100 SWE
            #     cells, 2026-05-15). Empty text + empty function_calls →
            #     loop would exit with no final summary.
            #   MAX_TOKENS — same shape as OpenAI's ``length``; truncated
            #     mid-generation, no tool call landed.
            # Inject a recovery nudge and let the loop continue; only
            # treat genuine ``STOP`` with text as a final answer.
            fr_str = str(finish_reason or "")
            empty_text = not any(t.strip() for t in text_parts)
            recoverable = (
                empty_text
                and turn < max_turns
                and ("MALFORMED_FUNCTION_CALL" in fr_str or "MAX_TOKENS" in fr_str)
            )
            if recoverable:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=(
                                    "Your previous response had no parsable function call "
                                    "and no final text (finish_reason="
                                    f"{fr_str}). Retry: either issue ONE well-formed "
                                    "`bash` function call (short command, valid JSON-ish "
                                    "args) or send a brief final text message with no "
                                    "function call to end the loop."
                                )
                            )
                        ],
                    )
                )
                _swe._record_event(
                    {
                        "kind": f"{trace_prefix}_recover",
                        "turn": turn,
                        "reason": f"empty_response_{fr_str}",
                        "ts": _swe.time.time(),
                    }
                )
                continue
            final_text = "\n".join(text_parts).strip()
            break

        response_parts: List[Any] = []
        for name, args in function_calls:
            if name != "bash":
                obs = f"unknown tool: {name!r}"
                _swe._record_event(
                    {
                        "kind": f"{trace_prefix}_unknown_tool",
                        "turn": turn,
                        "name": name,
                        "input": args,
                        "ts": _swe.time.time(),
                    }
                )
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
            response_parts.append(
                types.Part.from_function_response(
                    name=name,
                    response={"output": obs},
                )
            )
        contents.append(types.Content(role="user", parts=response_parts))

    return {
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "turns": turns,
        "final_summary": final_text,
        "max_turns_hit": turns == max_turns and not final_text,
    }


__all__ = ["_loop_cloud_anthropic", "_loop_cloud_openai", "_loop_cloud_gemini"]

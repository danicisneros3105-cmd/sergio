"""Anthropic (Claude) calls for :class:`~openjarvis.engine.cloud.CloudEngine`:
message preparation with prompt caching, generate, stream and full stream
with tool calls.

Split out of ``cloud.py`` to keep it readable. Module-level helpers are
looked up on ``openjarvis.engine.cloud`` at call time, so behaviour (and
anything patched there) is unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Dict, List, Tuple

import openjarvis.engine.cloud as _cloud
from openjarvis.core.types import Message
from openjarvis.engine._stubs import StreamChunk


class AnthropicMixin:
    def _prepare_anthropic_messages(
        self,
        messages: Sequence[Message],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Extract system text and convert messages to Anthropic format."""
        system_text = ""
        chat_msgs: List[Dict[str, Any]] = []
        for m in messages:
            if m.role.value == "system":
                system_text = m.content
            elif m.role.value == "tool":
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id or "",
                    "content": m.content,
                }
                if (
                    chat_msgs
                    and chat_msgs[-1]["role"] == "user"
                    and isinstance(chat_msgs[-1]["content"], list)
                    and chat_msgs[-1]["content"]
                    and chat_msgs[-1]["content"][-1].get("type") == "tool_result"
                ):
                    chat_msgs[-1]["content"].append(tool_result_block)
                else:
                    chat_msgs.append(
                        {
                            "role": "user",
                            "content": [tool_result_block],
                        }
                    )
            elif m.role.value == "assistant" and m.tool_calls:
                content_blocks: List[Dict[str, Any]] = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    args = tc.arguments
                    if isinstance(args, str):
                        try:
                            args = _cloud.json.loads(args)
                        except (_cloud.json.JSONDecodeError, TypeError):
                            args = {"input": args}
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": args if isinstance(args, dict) else {},
                        }
                    )
                chat_msgs.append({"role": "assistant", "content": content_blocks})
            else:
                chat_msgs.append({"role": m.role.value, "content": m.content})
        return system_text, chat_msgs

    def _generate_anthropic(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if self._anthropic_client is None:
            raise _cloud.EngineConnectionError(
                "Anthropic client not available — set "
                "ANTHROPIC_API_KEY and install "
                "openjarvis[inference-cloud]"
            )
        system_text, chat_msgs = self._prepare_anthropic_messages(messages)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": chat_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            create_kwargs["system"] = system_text

        # Convert and pass tools in Anthropic format
        raw_tools = kwargs.pop("tools", None)
        if raw_tools:
            create_kwargs["tools"] = _cloud._convert_tools_to_anthropic(raw_tools)

        # Apply structured output via Anthropic's tool_choice pattern
        response_format = kwargs.pop("response_format", None)
        if response_format is not None:
            from openjarvis.engine._stubs import ResponseFormat

            if isinstance(response_format, ResponseFormat):
                json_tool = {
                    "name": "json_output",
                    "description": "Output structured JSON response",
                    "input_schema": response_format.schema or {"type": "object"},
                }
                if "tools" not in create_kwargs:
                    create_kwargs["tools"] = [json_tool]
                else:
                    create_kwargs["tools"].append(json_tool)
                create_kwargs["tool_choice"] = {
                    "type": "tool",
                    "name": "json_output",
                }

        t0 = _cloud.time.monotonic()
        resp = self._anthropic_client.messages.create(**create_kwargs)
        elapsed = _cloud.time.monotonic() - t0

        # Walk every block in resp.content. Anthropic returns several kinds:
        #   - text                       (plain assistant text)
        #   - tool_use                   (model wants the caller to run a tool)
        #   - server_tool_use            (model invoked a server-side tool,
        #                                 e.g. web_search; carries the actual
        #                                 query the model issued)
        #   - web_search_tool_result     (server-tool result body)
        #   - tool_result                (caller-side tool result echo)
        #   - thinking                   (Opus reasoning trace)
        # ``content_blocks`` keeps the full serialized list for trace
        # observability. ``tool_calls`` is the narrow caller-executable
        # surface — only ``tool_use`` blocks (server_tool_use lives in
        # content_blocks since Anthropic already ran it server-side).
        # ``tool_results`` aggregates both result kinds.
        content_parts: list[str] = []
        tool_calls: list[Dict[str, Any]] = []
        tool_results: list[Dict[str, Any]] = []
        content_blocks: list[Dict[str, Any]] = []
        for block in resp.content:
            btype = getattr(block, "type", None) or type(block).__name__
            serialized = _cloud._serialize_anthropic_block(block)
            content_blocks.append(serialized)
            if btype == "tool_use":
                block_id = getattr(block, "id", None)
                if not block_id:
                    _cloud.logger.warning(
                        "Anthropic tool_use block without an id; skipping. "
                        "Round-trip into the next assistant turn would fail "
                        "Anthropic's tool_use_id matching."
                    )
                    continue
                tool_calls.append(
                    {
                        "id": block_id,
                        "name": getattr(block, "name", ""),
                        "arguments": _cloud.json.dumps(getattr(block, "input", None))
                        if isinstance(getattr(block, "input", None), dict)
                        else str(getattr(block, "input", "")),
                    }
                )
            elif btype in ("web_search_tool_result", "tool_result"):
                tool_results.append(serialized)
            elif hasattr(block, "text"):
                content_parts.append(block.text)

        content = "\n".join(content_parts) if content_parts else ""
        prompt_tokens = resp.usage.input_tokens if resp.usage else 0
        completion_tokens = resp.usage.output_tokens if resp.usage else 0

        result: Dict[str, Any] = {
            "content": content,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "model": resp.model,
            "finish_reason": resp.stop_reason or "stop",
            "cost_usd": _cloud.estimate_cost(model, prompt_tokens, completion_tokens),
            "ttft": elapsed,
            "content_blocks": content_blocks,
        }

        if tool_calls:
            result["tool_calls"] = tool_calls
        if tool_results:
            result["tool_results"] = tool_results

        return result

    async def _stream_anthropic(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if self._anthropic_client is None:
            raise _cloud.EngineConnectionError("Anthropic client not available")
        system_text = ""
        chat_msgs: List[Dict[str, Any]] = []
        for m in messages:
            if m.role.value == "system":
                system_text = m.content
            else:
                chat_msgs.append({"role": m.role.value, "content": m.content})
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": chat_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            create_kwargs["system"] = system_text
        with self._anthropic_client.messages.stream(**create_kwargs) as stream:
            for text in stream.text_stream:
                yield text

    async def _stream_full_anthropic(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Yield StreamChunks from an Anthropic streaming response."""
        if self._anthropic_client is None:
            raise _cloud.EngineConnectionError("Anthropic client not available")
        system_text, chat_msgs = self._prepare_anthropic_messages(messages)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": chat_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            create_kwargs["system"] = system_text
        raw_tools = kwargs.pop("tools", None)
        if raw_tools:
            create_kwargs["tools"] = _cloud._convert_tools_to_anthropic(raw_tools)
        kwargs.pop("tool_choice", None)

        with self._anthropic_client.messages.stream(**create_kwargs) as stream:
            tool_index = -1
            for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        tool_index += 1
                        yield _cloud.StreamChunk(
                            tool_calls=[
                                {
                                    "index": tool_index,
                                    "id": block.id,
                                    "function": {"name": block.name, "arguments": ""},
                                }
                            ]
                        )
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield _cloud.StreamChunk(content=delta.text)
                    elif delta.type == "input_json_delta":
                        yield _cloud.StreamChunk(
                            tool_calls=[
                                {
                                    "index": tool_index,
                                    "function": {"arguments": delta.partial_json},
                                }
                            ]
                        )
                elif event.type == "message_delta":
                    stop_reason = event.delta.stop_reason
                    finish = "tool_calls" if stop_reason == "tool_use" else "stop"
                    yield _cloud.StreamChunk(finish_reason=finish)

            # End-of-stream parity with ``_generate_anthropic``: emit
            # ``content_blocks`` (every block kind, including server_tool_use
            # and thinking) and ``tool_results`` (web_search_tool_result +
            # tool_result) so streaming traces see what non-streaming traces
            # see.
            try:
                final_msg = stream.get_final_message()
            except Exception as exc:  # noqa: BLE001 — SDK shape varies
                _cloud.logger.debug(
                    "Anthropic stream.get_final_message() failed: %s", exc
                )
                final_msg = None
            if final_msg is not None and getattr(final_msg, "content", None):
                content_blocks: list[Dict[str, Any]] = []
                tool_results: list[Dict[str, Any]] = []
                for block in final_msg.content:
                    btype = getattr(block, "type", None) or type(block).__name__
                    serialized = _cloud._serialize_anthropic_block(block)
                    content_blocks.append(serialized)
                    if btype in ("web_search_tool_result", "tool_result"):
                        tool_results.append(serialized)
                if content_blocks or tool_results:
                    yield _cloud.StreamChunk(
                        content_blocks=content_blocks or None,
                        tool_results=tool_results or None,
                    )


__all__ = ["AnthropicMixin"]

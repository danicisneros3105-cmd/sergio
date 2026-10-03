"""Tools: phone calls and WhatsApp messages.

* Calls and messages to the owner's own numbers run directly.
* Anything to a third party waits for the user's approval in the approval
  bell (or ``sergio approvals approve``), runs exactly as approved, once.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_SETUP_HINT = (
    "Phone features are not set up yet: enable [phone] in config.toml and add "
    "the Twilio/WhatsApp keys to ~/.openjarvis/sergio.env (see LEEME.md)."
)


class _PhoneTool(BaseTool):
    def __init__(
        self,
        *,
        config: Any = None,
        approvals: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if config is None:
            from openjarvis.core.config import load_config

            config = load_config()
        self._config = config
        self._approvals = approvals
        self._sleep = sleep
        self._clock = clock

    def _ok(self, content: str, **meta: Any) -> ToolResult:
        return ToolResult(tool_name=self.tool_id, content=content, metadata=meta)

    def _fail(self, content: str, **meta: Any) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_id, content=content, success=False, metadata=meta
        )

    def _approve(
        self, params: dict[str, Any], description: str, payload: dict[str, Any]
    ) -> tuple[dict | None, ToolResult | None]:
        """Skip approval for owner numbers; otherwise use the approval queue."""
        from openjarvis.phone.numbers import is_owner
        from openjarvis.unified.approvals import default_store, request_approval

        approval_id = str(params.get("approval_id") or "").strip()
        if not approval_id and is_owner(
            payload["to"], self._config.phone.owner_numbers
        ):
            return payload, None
        if self._approvals is None:
            self._approvals = default_store()
        decision = request_approval(
            self._approvals,
            action_type=self.tool_id,
            description=description,
            payload=payload,
            approval_id=approval_id,
            wait_seconds=float(self._config.phone.approval_wait_seconds),
            sleep=self._sleep,
            clock=self._clock,
        )
        if decision.payload is not None:
            return decision.payload, None
        meta = {"approval_id": decision.action_id}
        if decision.status == "pending":
            meta["pending"] = True
        return None, self._fail(decision.message, **meta)


@ToolRegistry.register("phone_call")
class PhoneCallTool(_PhoneTool):
    tool_id = "phone_call"

    @property
    def spec(self) -> ToolSpec:
        phone = self._config.phone
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Make a real phone call with Sergio's voice and return the "
                "transcript when it ends. Use it to book a table, ask a "
                "business something, or call the user (reminders). Give the "
                "full international number and a precise goal with every "
                "detail needed (names, date, time, number of people). Calls to "
                "anyone but the user wait for the user's approval; Sergio "
                "always says it is an AI assistant."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "number": {
                        "type": "string",
                        "description": "International number, e.g. +593991234567.",
                    },
                    "goal": {
                        "type": "string",
                        "description": "What the call must achieve, with all details.",
                    },
                    "approval_id": {
                        "type": "string",
                        "description": "From an earlier call still awaiting approval.",
                    },
                },
                "required": ["number", "goal"],
            },
            category="phone",
            timeout_seconds=float(phone.approval_wait_seconds)
            + float(phone.max_call_minutes) * 60
            + 120,
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.phone import calls
        from openjarvis.phone.numbers import to_e164

        if not self._config.phone.enabled:
            return self._fail(_SETUP_HINT)
        goal = str(params.get("goal") or "").strip()
        if not params.get("approval_id"):
            if not goal:
                return self._fail("The 'goal' parameter is required.")
            try:
                to = to_e164(str(params.get("number") or ""))
            except ValueError as exc:
                return self._fail(str(exc))
        else:
            to = ""
        try:
            calls.credentials()
            calls.public_base(self._config)
        except calls.PhoneConfigError as exc:
            return self._fail(f"{exc}. {_SETUP_HINT}")

        approved, refusal = self._approve(
            params,
            f"Sergio will call {to}: {goal}",
            {"to": to, "goal": goal},
        )
        if refusal is not None:
            return refusal

        record = calls.new_call(calls.OUTBOUND, approved["to"], goal=approved["goal"])
        try:
            record = calls.place_call(self._config, record)
        except Exception as exc:  # noqa: BLE001 — Twilio/network errors
            calls.update(record.id, status=calls.FAILED, error=str(exc))
            return self._fail(f"Could not place the call: {exc}", call_id=record.id)
        return self._wait(record.id)

    def _wait(self, call_id: str) -> ToolResult:
        from openjarvis.phone import calls

        limit = self._clock() + float(self._config.phone.max_call_minutes) * 60 + 90
        while self._clock() < limit:
            record = calls.load(call_id)
            if record and record.done:
                return describe(record, self)
            self._sleep(2.0)
        return self._ok(
            f"The call is still running (call_id='{call_id}'). Check it later "
            "with phone_call_status.",
            call_id=call_id,
        )


def describe(record: Any, tool: _PhoneTool) -> ToolResult:
    """Human-readable outcome of a finished call."""
    from openjarvis.phone import calls

    if record.status == calls.FAILED:
        return tool._fail(
            f"The call to {record.to} did not happen: {record.error or 'failed'}.",
            call_id=record.id,
        )
    lines = [f"Call to {record.to} finished."]
    if record.summary:
        lines.append(f"Result: {record.summary}")
    if record.transcript:
        lines.append("Transcript:")
        lines += [
            f"- {'Sergio' if t['role'] == 'sergio' else 'Them'}: {t['text']}"
            for t in record.transcript[-40:]
        ]
    return tool._ok("\n".join(lines), call_id=record.id)


@ToolRegistry.register("phone_call_status")
class PhoneCallStatusTool(_PhoneTool):
    tool_id = "phone_call_status"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description="Status, result and transcript of a phone call by call_id.",
            parameters={
                "type": "object",
                "properties": {"call_id": {"type": "string"}},
                "required": ["call_id"],
            },
            category="phone",
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.phone import calls

        call_id = str(params.get("call_id") or "")
        record = calls.load(call_id) if call_id.isalnum() else None
        if record is None:
            return self._fail(f"Unknown call_id '{call_id}'.")
        if not record.done:
            return self._ok(f"The call to {record.to} is {record.status}.")
        return describe(record, self)


@ToolRegistry.register("whatsapp_send")
class WhatsAppSendTool(_PhoneTool):
    tool_id = "whatsapp_send"

    def __init__(self, *, channel: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._channel = channel

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Send a WhatsApp text message from Sergio's WhatsApp number. "
                "Messages to anyone but the user wait for the user's approval. "
                "WhatsApp only allows free text to people who wrote to Sergio "
                "in the last 24 hours."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "International number, e.g. +593991234567.",
                    },
                    "text": {"type": "string", "description": "Message text."},
                    "approval_id": {"type": "string"},
                },
                "required": ["to", "text"],
            },
            category="phone",
            timeout_seconds=float(self._config.phone.approval_wait_seconds) + 30,
        )

    def execute(self, **params: Any) -> ToolResult:
        from openjarvis.phone.numbers import digits, to_e164

        text = str(params.get("text") or "").strip()
        if not params.get("approval_id"):
            if not text:
                return self._fail("The 'text' parameter is required.")
            try:
                to = to_e164(str(params.get("to") or ""))
            except ValueError as exc:
                return self._fail(str(exc))
        else:
            to = ""
        channel = self._channel
        if channel is None:
            from openjarvis.channels.whatsapp import WhatsAppChannel

            channel = WhatsAppChannel()
        if not getattr(channel, "_token", "") or not getattr(
            channel, "_phone_number_id", ""
        ):
            return self._fail(
                "WhatsApp needs WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID "
                "in ~/.openjarvis/sergio.env (see LEEME.md)."
            )
        approved, refusal = self._approve(
            params,
            f"Sergio will send a WhatsApp to {to}: {text}",
            {"to": to, "text": text},
        )
        if refusal is not None:
            return refusal
        # The Cloud API takes the number without '+'.
        if channel.send(digits(approved["to"]), approved["text"]):
            return self._ok(f"WhatsApp sent to {approved['to']}.")
        return self._fail(
            "WhatsApp did not accept the message. If this person has not written "
            "to Sergio in the last 24 hours, WhatsApp only allows approved "
            "template messages."
        )


__all__ = ["PhoneCallStatusTool", "PhoneCallTool", "WhatsAppSendTool", "describe"]

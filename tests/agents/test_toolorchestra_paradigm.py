"""ToolOrchestraAgent: action parsing and the prompted multi-turn loop."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from openjarvis.agents.hybrid import toolorchestra as t
from openjarvis.agents.hybrid.toolorchestra import ToolOrchestraAgent

WORKERS = [
    {
        "id": 0,
        "name": "local",
        "model": "qwen-local",
        "type": "vllm",
        "description": "cheap",
    },
    {
        "id": 1,
        "name": "opus",
        "model": "claude-opus-4-7",
        "type": "anthropic",
        "description": "strong",
    },
]


def test_parse_action_variants():
    assert (
        t._parse_action('{"action": "final_answer", "answer": "42"}')["answer"] == "42"
    )
    fenced = '```json\n{"action": "call_worker", "worker_id": 1, "input": "hi"}\n```'
    assert t._parse_action(fenced)["worker_id"] == 1
    prose = 'Sure! {"action": "final_answer", "answer": "{nested}"} done'
    assert t._parse_action(prose)["answer"] == "{nested}"
    assert t._parse_action("no json at all") is None
    assert t._parse_action('{"not_an_action": 1}') is None
    assert t._parse_action("{broken") is None


def test_final_answer_rescue_keeps_accents_and_escapes():
    raw = '{"action": "final_answer", "answer": "Un café en Cuenca\\n\\"rico\\""'
    assert t._extract_final_answer_text(raw) == 'Un café en Cuenca\n"rico"'
    assert t._extract_final_answer_text("blah\nFINAL ANSWER: Quito ") == "Quito"
    assert t._extract_final_answer_text("  plain  ") == "plain"


def test_rl_tool_call_parsing():
    sdk = [NS(function=NS(name="search", arguments='{"q": "x"}'))]
    assert t._parse_rl_tool_call("", sdk) == {"name": "search", "arguments": {"q": "x"}}
    bad_args = [NS(function=NS(name="search", arguments="{nope"))]
    assert t._parse_rl_tool_call("", bad_args) == {"name": "search", "arguments": {}}
    tagged = '<tool_call>{"name": "answer", "arguments": {"text": "ok"}}</tool_call>'
    assert t._parse_rl_tool_call(tagged, None) == {
        "name": "answer",
        "arguments": {"text": "ok"},
    }
    assert t._parse_rl_tool_call("<tool_call>[1]</tool_call>", None) is None
    assert t._parse_rl_tool_call("<tool_call>{bad</tool_call>", None) is None
    assert t._parse_rl_tool_call(None, None) is None


def test_user_prompt_lists_pool_and_history():
    history = [
        {"role": "orchestrator", "turn": 1, "raw": "{...}"},
        {
            "role": "worker",
            "turn": 1,
            "worker_id": 1,
            "worker_name": "opus",
            "output": "partial",
        },
    ]
    prompt = t._build_user_prompt("Q?", WORKERS, history)
    assert "Worker 1 (opus): strong" in prompt
    assert "[Worker 1 (opus) turn 1]\npartial" in prompt
    assert prompt.endswith("exactly one object, no prose.")


def test_rejects_unknown_mode():
    with pytest.raises(ValueError, match="orchestrator_mode"):
        ToolOrchestraAgent(
            MagicMock(), "claude-opus-4-7", cfg={"orchestrator_mode": "magic"}
        )


class _Run:
    def __init__(self, replies, cfg=None):
        self.agent = ToolOrchestraAgent(
            MagicMock(), "claude-opus-4-7", cfg={"workers": WORKERS, **(cfg or {})}
        )
        self.replies = list(replies)
        self.systems = []
        self.dispatched = []
        self.agent._call_cloud = self._orchestrate
        self.agent._call_worker_secured = self._worker
        self.agent.record_trace_event = lambda event: None

    def _orchestrate(self, *, user, system, **kw):
        self.systems.append(system)
        return self.replies.pop(0), 50, 10

    def _worker(self, worker, prompt, cfg):
        self.dispatched.append((worker["name"], prompt))
        return f"{worker['name']} says hi", 20, 5, worker["type"] == "vllm", 0.0, 0


def _act(**kw):
    return json.dumps(kw)


def test_call_worker_then_answer():
    run = _Run(
        [
            _act(action="call_worker", worker_id=0, input="draft"),
            _act(action="final_answer", answer="done"),
        ]
    )
    answer, meta = run.agent._run_paradigm("Q?", None)
    assert answer == "done" and run.dispatched == [("local", "draft")]
    assert (
        meta["turns"] == 2
        and meta["tokens_local"] == 25
        and meta["tokens_cloud"] == 120
    )
    assert meta["traces"]["forced_final"] is False


def test_bad_worker_ids_and_garbage_end_in_rescue():
    run = _Run(
        [_act(action="call_worker", worker_id=7, input="x"), 'oops "answer": "rescued"']
    )
    answer, meta = run.agent._run_paradigm("Q?", None)
    assert answer == "rescued" and meta["traces"]["parse_failures"] == 2


def test_last_turn_forces_final_then_falls_back_to_strongest_worker():
    replies = [_act(action="call_worker", worker_id=0, input="a"), _act(action="think")]
    run = _Run(replies, cfg={"max_turns": 2})
    answer, meta = run.agent._run_paradigm("Q?", None)
    assert t.FORCE_FINAL_PROMPT in run.systems[-1]
    assert answer == "opus says hi"  # fallback: priciest non-search worker
    assert meta["traces"]["history"][-1]["fallback"] is True


def test_empty_pool(monkeypatch):
    agent = ToolOrchestraAgent(MagicMock(), "claude-opus-4-7", cfg={})
    monkeypatch.setattr(t, "_resolve_worker_pool", lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="empty worker pool"):
        agent._run_paradigm("Q", None)


def test_capabilities_follow_the_pool():
    search = {
        "id": 2,
        "name": "web",
        "model": "gpt-5-mini",
        "type": next(iter(t._TOOLORCH_SEARCH_TYPES)),
    }
    assert ToolOrchestraAgent._worker_required_capabilities(search) == ["network:fetch"]
    assert ToolOrchestraAgent._worker_required_capabilities(
        {"type": "modal-python"}
    ) == ["code:execute"]
    assert ToolOrchestraAgent._worker_required_capabilities(
        {"type": "openai"}, swe_mode=True
    ) == [
        "code:execute",
        "file:read",
        "file:write",
    ]
    agent = ToolOrchestraAgent(
        MagicMock(), "claude-opus-4-7", cfg={"workers": WORKERS + [search]}
    )
    assert "network:fetch" in agent._required_capabilities_for_run(None)
    rl = ToolOrchestraAgent(
        MagicMock(), "claude-opus-4-7", cfg={"orchestrator_mode": "rl", "pool": "paper"}
    )
    assert {"network:fetch", "code:execute"} <= set(
        rl._required_capabilities_for_run(None)
    )

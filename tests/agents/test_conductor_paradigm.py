"""ConductorAgent: plan parsing, prompt building and the plan-then-execute run."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from openjarvis.agents.hybrid import conductor as c
from openjarvis.agents.hybrid.conductor import ConductorAgent

WORKERS = [
    {
        "id": 0,
        "name": "local",
        "model": "qwen-local",
        "endpoint": "vllm",
        "description": "cheap",
    },
    {
        "id": 1,
        "name": "mini",
        "model": "gpt-5-mini",
        "endpoint": "openai",
        "description": "fast",
    },
    {
        "id": 2,
        "name": "opus",
        "model": "claude-opus-4-7",
        "endpoint": "anthropic",
        "description": "strong",
    },
]


# -- parsing -------------------------------------------------------------------


def test_strip_fences_and_json_plan():
    plan = {
        "model_id": [0, 2],
        "subtasks": ["draft", "finish"],
        "access_list": [[], "all"],
    }
    text = "```json\n" + json.dumps(plan) + "\n```"
    assert c._strip_fences(text) == json.dumps(plan)
    assert c._parse_plan(text, 3) == (plan, None)


def test_literal_python_plan_style():
    text = "model_id = [1]\nsubtasks = ['answer it']\naccess_list = [[]]"
    parsed, err = c._parse_plan(text, 3)
    assert err is None and parsed["model_id"] == [1]
    assert c._try_literal("model_id = [1]") is None
    nested = (
        "model_id = [0] + [2]\nsubtasks = ['a [x]', \"b ]\"]\naccess_list = [[], [0]]"
    )
    parsed, err = c._parse_plan(nested, 3)
    assert err is None
    assert parsed == {
        "model_id": [0, 2],
        "subtasks": ["a [x]", "b ]"],
        "access_list": [[], [0]],
    }


@pytest.mark.parametrize(
    "plan,needle",
    [
        ([], "not a dict"),
        ({"model_id": [0]}, "missing key"),
        ({"model_id": 0, "subtasks": [], "access_list": []}, "must be lists"),
        ({"model_id": [0], "subtasks": ["a", "b"], "access_list": [[]]}, "unequal"),
        ({"model_id": [], "subtasks": [], "access_list": []}, "1..5"),
        ({"model_id": [9], "subtasks": ["a"], "access_list": [[]]}, "out of range"),
        ({"model_id": [0], "subtasks": [" "], "access_list": [[]]}, "non-empty"),
        ({"model_id": [0], "subtasks": ["a"], "access_list": ["x"]}, "list or"),
        (
            {"model_id": [0, 1], "subtasks": ["a", "b"], "access_list": [[], [1]]},
            "bad ref",
        ),
    ],
)
def test_validate_plan_errors(plan, needle):
    assert needle in c._validate_plan(plan, 3)


def test_unparseable_plan():
    assert c._parse_plan("I will just answer.", 3) == (
        None,
        "could not parse a valid plan",
    )


# -- prompts -------------------------------------------------------------------


def test_step_prompt_includes_only_allowed_history():
    prior = [{"subtask": "s0", "output": "o0"}, {"subtask": "s1", "output": "o1"}]
    some = c._build_step_prompt("Q?", "do it", prior, [1])
    assert "[Step 1 response]\no1" in some and "o0" not in some
    every = c._build_step_prompt("Q?", "do it", prior, "all")
    assert "o0" in every and "o1" in every
    none = c._build_step_prompt("Q?", "do it", prior, [])
    assert "Previous routing" not in none and none.endswith("Your subtask:\ndo it")


def test_conductor_prompt_search_constraint():
    plain = c._build_conductor_prompt("Q?", WORKERS)
    assert "Model 2 (opus): strong" in plain and "WEB SEARCH" not in plain
    provider = c._build_conductor_prompt("Q?", WORKERS, web_search_enabled=True)
    assert "[1, 2]" in provider and "Only these model indices" in provider
    tavily = c._build_conductor_prompt(
        "Q?", WORKERS, web_search_enabled=True, search_backend="tavily"
    )
    assert "[0, 1, 2]" in tavily and "Tavily" in tavily
    blind = c._build_conductor_prompt("Q?", WORKERS[:1], web_search_enabled=True)
    assert "No model in this pool" in blind


def test_search_costs_by_endpoint():
    assert c._worker_search_cost_per_call("openai") == c.OPENAI_WEB_SEARCH_COST_PER_CALL
    assert c._worker_search_cost_per_call("gemini") == c.GEMINI_SEARCH_COST_PER_CALL
    assert c._worker_search_cost_per_call("anthropic") == c.WEB_SEARCH_COST_PER_CALL


# -- the run -------------------------------------------------------------------


class _Run:
    """A ConductorAgent whose planner and workers are scripted."""

    def __init__(self, plans, cfg=None):
        self.agent = ConductorAgent(
            MagicMock(), "claude-opus-4-7", cfg={"workers": WORKERS, **(cfg or {})}
        )
        self.plans = list(plans)
        self.calls = []
        self.events = []
        self.agent._call_cloud = self._plan
        self.agent._call_worker_secured = self._worker
        self.agent.record_trace_event = self.events.append

    def _plan(self, **kw):
        return self.plans.pop(0), 100, 20

    def _worker(self, worker, prompt, cfg, **kw):
        self.calls.append((worker["name"], prompt, kw))
        is_local = worker["endpoint"] == "vllm"
        return (
            f"out-{worker['name']}",
            10,
            5,
            is_local,
            1 if kw.get("web_search_tool") else 0,
            0.0,
        )


def test_plan_then_execute():
    plan = {
        "model_id": [0, 2],
        "subtasks": ["draft", "polish"],
        "access_list": [[], [0]],
    }
    run = _Run([json.dumps(plan)])
    answer, meta = run.agent._run_paradigm("What is X?", None)
    assert answer == "out-opus"
    assert [name for name, _, _ in run.calls] == ["local", "opus"]
    assert "out-local" in run.calls[1][1]  # step 1 sees step 0's output
    assert (
        meta["turns"] == 3
        and meta["tokens_local"] == 15
        and meta["tokens_cloud"] == 15 + 120
    )
    assert meta["traces"]["fallback_used"] is False and meta["cost_usd"] > 0
    assert run.events[0]["kind"] == "conductor_plan"


def test_retry_then_fallback_to_strongest_worker():
    good = {"model_id": [1], "subtasks": ["answer"], "access_list": [[]]}
    retried = _Run(["no plan here", json.dumps(good)])
    answer, meta = retried.agent._run_paradigm("Q", None)
    assert answer == "out-mini" and len(meta["traces"]["parse_attempts"]) == 2
    fallback = _Run(["nope", "still nope"])
    answer, meta = fallback.agent._run_paradigm("Q", None)
    assert answer == "out-opus" and meta["traces"]["fallback_used"] is True


def test_web_search_routing_warning_and_count():
    plan = {
        "model_id": [0, 1],
        "subtasks": ["guess", "search"],
        "access_list": [[], "all"],
    }
    run = _Run([json.dumps(plan)], cfg={"web_search": {"enabled": True}})
    _, meta = run.agent._run_paradigm("Who won?", None)
    kinds = [e["kind"] for e in run.events]
    assert "conductor_search_routing_warning" in kinds
    assert meta["web_search_uses"] == 2 and meta["tool_calls"] == 2


def test_web_search_without_capable_worker_fails_loud():
    run = _Run([json.dumps({"model_id": [0], "subtasks": ["x"], "access_list": [[]]})])
    run.agent._cfg["workers"] = WORKERS[:1]
    run.agent._cfg["web_search"] = {"enabled": True}
    with pytest.raises(ValueError, match="no search-capable worker"):
        run.agent._run_paradigm("Q", None)


def test_empty_pool_is_an_error(monkeypatch):
    agent = ConductorAgent(MagicMock(), "claude-opus-4-7", cfg={})
    monkeypatch.setattr(c, "_resolve_worker_pool", lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="empty worker pool"):
        agent._run_paradigm("Q", None)

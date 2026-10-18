"""Tests for delegating tasks to OpenClacky."""

from __future__ import annotations

import json
import subprocess

from openjarvis.core.config import JarvisConfig
from openjarvis.tools.approval_store import ApprovalStore
from openjarvis.tools.clacky_task import ClackyTaskTool, summarize_events


class AutoDecide(ApprovalStore):
    """Approval store whose user answers *decision* right after queueing."""

    def __init__(self, db_path, decision="approved"):
        super().__init__(str(db_path))
        self.decision = decision
        self.queued = []

    def queue_action(self, **kwargs):
        action = super().queue_action(**kwargs)
        self.queued.append(action)
        if self.decision:
            self.update_status(action.id, self.decision)
        return action


def _ndjson(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


def _config(tmp_path) -> JarvisConfig:
    cfg = JarvisConfig()
    cfg.intelligence.default_model = "qwen3:8b"
    root = tmp_path / "clacky"
    (root / "bin").mkdir(parents=True, exist_ok=True)
    cfg.extensions.clacky.path = str(root)
    cfg.extensions.clacky.timeout_seconds = 42
    return cfg


def _which(name: str) -> str:
    return f"/usr/bin/{name}"


def test_summarize_events_keeps_last_message_tools_and_cost():
    out = _ndjson(
        {"type": "system", "message": "Agent started"},
        {"type": "assistant_message", "content": "Working on it"},
        {"type": "tool_call", "name": "terminal", "args": {}},
        {"type": "tool_call", "name": "write"},
        {"type": "assistant_message", "content": "Moved 3 files."},
        {"type": "done", "total_cost": 0.0123},
    )
    assert summarize_events("noise\n" + out + "{bad json") == (
        "Moved 3 files.",
        ["terminal", "write"],
        "",
        0.0123,
    )


def test_execute_runs_clacky_with_shared_model(tmp_path):
    calls = {}

    def runner(cmd, **kwargs):
        calls["cmd"], calls["kwargs"] = cmd, kwargs
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=_ndjson(
                {"type": "tool_call", "name": "browser"},
                {"type": "assistant_message", "content": "Done."},
                {"type": "done", "total_cost": 0.5},
            ),
            stderr="",
        )

    store = AutoDecide(tmp_path / "a.db")
    tool = ClackyTaskTool(
        config=_config(tmp_path), runner=runner, which=_which, approvals=store
    )
    assert tool.spec.requires_confirmation is False  # approval queue instead
    assert tool.spec.timeout_seconds == 42 + 300
    result = tool.execute(task="Open example.com", working_dir=str(tmp_path))

    assert result.success, result.content
    assert result.content.startswith("Done.")
    assert "browser" in result.content
    assert result.cost_usd == 0.5
    cmd = calls["cmd"]
    assert cmd[:3] == ["/usr/bin/bundle", "exec", "ruby"]
    assert cmd[-2:] == ["-m", "Open example.com"]
    assert "--json" in cmd and cmd[cmd.index("--path") + 1] == str(tmp_path)
    env = calls["kwargs"]["env"]
    assert env["CLACKY_MODEL"] == "qwen3:8b"
    assert env["BUNDLE_GEMFILE"].endswith("Gemfile")
    assert calls["kwargs"]["timeout"] == 42


def test_execute_reports_agent_errors_and_timeouts(tmp_path):
    def failing(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout=_ndjson({"type": "error", "message": "401 bad key"}),
            stderr="",
        )

    tool = ClackyTaskTool(
        config=_config(tmp_path),
        runner=failing,
        which=_which,
        approvals=AutoDecide(tmp_path / "a.db"),
    )
    result = tool.execute(task="x", working_dir=str(tmp_path))
    assert not result.success and "401 bad key" in result.content

    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 42)

    tool = ClackyTaskTool(
        config=_config(tmp_path),
        runner=slow,
        which=_which,
        approvals=AutoDecide(tmp_path / "b.db"),
    )
    assert (
        "no terminó" in tool.execute(task="x", working_dir=str(tmp_path)).content
    )  # Spanish, the owner reads it


def test_execute_validates_inputs_and_environment(tmp_path):
    cfg = _config(tmp_path)
    tool = ClackyTaskTool(config=cfg, runner=None, which=_which)
    assert "required" in tool.execute(task="  ").content
    assert (
        "does not exist"
        in tool.execute(task="x", working_dir=str(tmp_path / "nope")).content
    )

    assert (
        "Ruby"
        in ClackyTaskTool(config=cfg, which=lambda n: None).execute(task="x").content
    )

    cfg.intelligence.default_model = ""
    assert (
        "default_model"
        in ClackyTaskTool(config=cfg, which=_which).execute(task="x").content
    )

    cfg.extensions.clacky.enabled = False
    assert (
        "apagado" in ClackyTaskTool(config=cfg, which=_which).execute(task="x").content
    )

    cfg.extensions.clacky.enabled = True
    cfg.extensions.clacky.path = str(tmp_path / "missing")
    assert (
        "no está instalado"
        in ClackyTaskTool(config=cfg, which=_which).execute(task="x").content
    )


def _never_run(cmd, **kwargs):
    raise AssertionError("OpenClacky must not run without approval")


def test_denied_task_never_runs(tmp_path):
    store = AutoDecide(tmp_path / "a.db", decision="denied")
    tool = ClackyTaskTool(
        config=_config(tmp_path), runner=_never_run, which=_which, approvals=store
    )
    result = tool.execute(task="Delete my Downloads", working_dir=str(tmp_path))
    assert not result.success and "did not approve" in result.content
    assert store.queued[0].description.endswith("Delete my Downloads")


def test_pending_task_resumes_with_the_approved_payload(tmp_path):
    cfg = _config(tmp_path)
    cfg.extensions.clacky.approval_wait_seconds = 3
    store = AutoDecide(tmp_path / "a.db", decision=None)
    clock = iter(range(100))
    tool = ClackyTaskTool(
        config=cfg,
        runner=_never_run,
        which=_which,
        approvals=store,
        sleep=lambda s: None,
        clock=lambda: next(clock),
    )
    waiting = tool.execute(task="Organize Downloads", working_dir=str(tmp_path))
    assert not waiting.success and waiting.metadata["pending"] is True
    action_id = waiting.metadata["approval_id"]
    assert action_id in waiting.content

    store.update_status(action_id, "approved")
    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=_ndjson({"type": "assistant_message", "content": "Ok"}),
            stderr="",
        )

    tool._runner = runner
    # The model cannot swap the task after approval: the stored payload wins.
    done = tool.execute(approval_id=action_id, task="rm -rf /")
    assert done.success and done.content.startswith("Ok")
    assert calls[0][-1] == "Organize Downloads"
    assert store.get_action(action_id).status == "executed"
    again = tool.execute(approval_id=action_id)
    assert not again.success and "already used" in again.content
    assert "Unknown approval_id" in tool.execute(approval_id="nope").content


def test_same_task_reuses_the_open_request_and_is_high_risk(tmp_path):
    cfg = _config(tmp_path)
    cfg.extensions.clacky.approval_wait_seconds = 0
    store = AutoDecide(tmp_path / "a.db", decision=None)
    tool = ClackyTaskTool(config=cfg, runner=_never_run, which=_which, approvals=store)
    first = tool.execute(task="Install VLC", working_dir=str(tmp_path))
    second = tool.execute(task="Install VLC", working_dir=str(tmp_path))
    assert first.metadata["approval_id"] == second.metadata["approval_id"]
    assert len(store.list_pending()) == 1
    assert store.list_pending()[0].tier == "high"
    assert "sergio approvals approve" in first.content


def test_one_approval_runs_the_task_only_once(tmp_path):
    store = AutoDecide(tmp_path / "a.db", decision=None)
    action = store.queue_action(
        action_type="clacky_task",
        description="x",
        payload={"task": "Buy milk", "working_dir": str(tmp_path)},
        permission_key="clacky_task",
        tier="high",
    )
    store.update_status(action.id, "approved")
    assert store.transition(action.id, "approved", "executed") is True
    assert store.transition(action.id, "approved", "executed") is False


def test_missing_workdir_keeps_the_approval_usable(tmp_path):
    store = AutoDecide(tmp_path / "a.db", decision=None)
    gone = tmp_path / "gone"
    gone.mkdir()
    action = store.queue_action(
        action_type="clacky_task",
        description="x",
        payload={"task": "t", "working_dir": str(gone)},
        permission_key="clacky_task",
        tier="high",
    )
    store.update_status(action.id, "approved")
    gone.rmdir()
    tool = ClackyTaskTool(
        config=_config(tmp_path), runner=_never_run, which=_which, approvals=store
    )
    result = tool.execute(approval_id=action.id)
    assert "does not exist" in result.content
    assert store.get_action(action.id).status == "approved"

"""MiniSWEAgent — vendored, ~330-line port of mini-SWE-agent v2.

Single-LLM agent loop with a ``bash`` tool, run inside a per-task git
clone. The model iterates: read files, grep, run tests, edit, retry —
the environment-interaction loop that turns SWE-bench from "predict the
patch blind" (~0.30) into "actually fix the bug" (~0.77 for frontier
models).

Two ways to use this module:

1. **Standalone agent** — :class:`MiniSWEAgent` registered as
   ``mini_swe_agent``. Use it directly as the agent for a cell.
2. **As a worker subroutine inside another paradigm** — call
   :func:`run_swe_agent_loop(task, ...)`. Returns a dict with the final
   patch, token totals, cost, etc. This is how Minions / Conductor /
   Advisors / SkillOrchestra / ToolOrchestra / Archon swap their
   one-shot worker call for a real agent loop when running SWE-bench.

Differences vs. the upstream
(https://github.com/swe-agent/mini-swe-agent):

- No Docker sandbox. We clone the SWE-bench repo into a tempdir and
  exec bash there. Network is available (pip etc.). Treat outputs as
  untrusted — model can run ``rm -rf`` against its own workdir, but the
  workdir is disposable. Don't run this on a host with secrets in the
  CWD.
- One tool, ``bash``. No separate ``submit`` — the loop ends when the
  model produces a turn with no tool calls. We extract the patch from
  ``git diff`` in the workdir at that point.
- Trace events captured via the LocalCloudAgent thread-local trace
  buffer so every bash invocation + result lands in
  ``experiments/<cell>/logs/<task_id>.json``.
"""

from __future__ import annotations

import json  # noqa: F401 - mini_swe_local_loop looks it up here
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from openjarvis.agents._stubs import AgentContext
from openjarvis.agents.hybrid._base import (
    LocalCloudAgent,
    _bump_local_calls,  # noqa: F401 - used by mini_swe_local_loop
    _record_event,
)

# Also used by the cloud loops (mini_swe_cloud_loops.py), which look these
# names up on this module; the `x as x` form marks them as re-exports.
from openjarvis.agents.hybrid._base import _bump_cloud_calls as _bump_cloud_calls
from openjarvis.agents.hybrid._prices import cost as estimate_cost
from openjarvis.agents.hybrid._prices import is_gpt5_family as is_gpt5_family
from openjarvis.agents.hybrid._prices import (
    supports_temperature as supports_temperature,
)
from openjarvis.agents.hybrid.mini_swe_prompts import (  # noqa: F401 (re-exported)
    BASH_TOOL_ANTHROPIC,
    BASH_TOOL_GEMINI_PARAMETERS,
    BASH_TOOL_OPENAI,
    SYSTEM_PROMPT,
)
from openjarvis.core.registry import AgentRegistry

# ---------- Workdir / bash plumbing ----------

# Models trained on SWE-bench Docker images (Qwen especially) reflexively
# prefix commands with ``cd /testbed`` — the standard container repo path.
# Our harness has no ``/testbed``; the repo is cloned into a per-task
# tempdir and bash already runs with ``cwd`` set to it. An un-rewritten
# ``cd /testbed`` errors with "No such file or directory" and, chained with
# ``&&``, aborts the whole command — so the agent burns every turn and
# never lands an edit. We rewrite ``/testbed`` references to the real
# workdir so those commands run as intended.
_TESTBED_CD_RE = re.compile(r"^\s*cd\s+/testbed(?:/\S*)?\s*(?:&&|;)\s*")


def _rewrite_testbed_paths(command: str, workdir: Path) -> str:
    """Neutralize hard-coded ``/testbed`` paths in a model-issued command.

    - A leading ``cd /testbed && ...`` (or ``;``) is stripped — bash already
      runs in the repo root, so the rest of the command is correct as-is.
    - Any remaining ``/testbed`` occurrences (e.g. ``cat /testbed/foo.py``)
      are rewritten to the real workdir.
    """
    wd = str(workdir)
    new = _TESTBED_CD_RE.sub("", command)
    # Bare ``cd /testbed`` with nothing after it → no-op into the workdir.
    if re.fullmatch(r"\s*cd\s+/testbed/?\s*", new):
        new = f"cd {wd}"
    # Replace any other /testbed path references (word-boundary so we don't
    # clobber e.g. /testbedrock).
    new = re.sub(r"/testbed(?=/|\b)", wd, new)
    return new


def _clone_repo(repo: str, base_commit: str, dest: Path) -> None:
    """Shallow-fetch the SWE-bench repo at the right commit into ``dest``."""
    url = f"https://github.com/{repo}.git"
    subprocess.run(
        ["git", "clone", "--quiet", url, str(dest)],
        check=True,
        timeout=300,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "--quiet", base_commit],
        cwd=str(dest),
        check=True,
        timeout=120,
        capture_output=True,
    )


def _decode_bash_output(raw: bytes, exit_code: int) -> str:
    """Safely decode bash stdout/stderr bytes into a str the LLM can read.

    The model sometimes runs commands that produce binary output (``cat``
    on a ``.pyc`` / ``.png`` / packed extension, a ``find`` that pipes a
    binary blob, ``xxd`` on a libc, ...). Decoding those with strict UTF-8
    raises ``UnicodeDecodeError`` deep inside ``Popen.communicate()`` and
    crashes the whole agent loop (1 errored row in the n=100 sweep per
    such command). We:

    1. Decode with ``errors="replace"`` so partial / mixed output is
       always recoverable as a str.
    2. If the result looks predominantly binary — contains a NUL byte OR
       has more than ~5% U+FFFD replacement chars after decode — replace
       it with a one-line stub so the model can keep working without
       drowning in Mojibake. Threshold checked against the *bytes* length
       (no NUL byte ⇒ probably text-ish; LLMs handle the occasional
       replacement char fine).
    """
    if not raw:
        return ""
    decoded = raw.decode("utf-8", errors="replace")
    if b"\x00" in raw or decoded.count("�") * 20 > len(decoded):
        return f"[binary output: {len(raw)} bytes, exit={exit_code}]"
    return decoded


def _run_bash(
    command: str, workdir: Path, *, timeout: int = 120, output_cap: int = 10_000
) -> Dict[str, Any]:
    """Run one shell command in ``workdir``. Returns dict with stdout, stderr,
    exit_code, and a ``truncated`` flag if output was clamped.

    The command is launched in its own process group (``start_new_session``)
    so a model-issued command that backgrounds a long-lived child (a dev
    server, ``sleep``, a hung test runner) can be killed *as a tree* on
    timeout. Plain ``subprocess.run(..., capture_output=True, timeout=...)``
    only kills the direct child and then re-blocks on ``communicate()``
    draining the pipe — which a surviving grandchild holds open forever,
    silently wedging the whole agent loop.
    """
    t0 = time.time()
    command = _rewrite_testbed_paths(command, workdir)
    # Capture as bytes (no ``text=True``) so a tool invocation that emits
    # binary output (compiled artifact, image, PDF, gzipped tarball) can't
    # crash the loop on a strict UTF-8 decode mid-``communicate()``. We
    # decode below with ``errors="replace"`` and, if the result looks
    # binary (null byte or >5% replacement chars), substitute a stub so
    # the model doesn't waste tokens / context on Mojibake.
    proc = subprocess.Popen(
        ["bash", "-lc", command],
        cwd=str(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout_b, stderr_b = proc.communicate(timeout=timeout)
        exit_code = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        # Kill the whole process group so backgrounded grandchildren can't
        # keep the stdout/stderr pipe open and deadlock the drain below.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                break
            try:
                proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                continue
        try:
            stdout_b, stderr_b = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            stdout_b, stderr_b = b"", b""
        stdout_b = stdout_b or b""
        stderr_b = stderr_b or b""
        exit_code = -1
        timed_out = True
    stdout = _decode_bash_output(stdout_b, exit_code)
    stderr = _decode_bash_output(stderr_b, exit_code)
    truncated = False
    if len(stdout) > output_cap:
        stdout = (
            stdout[:output_cap] + f"\n…[+{len(stdout) - output_cap} chars truncated]"
        )
        truncated = True
    if len(stderr) > output_cap:
        stderr = (
            stderr[:output_cap] + f"\n…[+{len(stderr) - output_cap} chars truncated]"
        )
        truncated = True
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "truncated": truncated,
        "latency_s": time.time() - t0,
    }


def _format_observation(result: Dict[str, Any]) -> str:
    parts = [f"exit_code: {result['exit_code']}"]
    if result.get("timed_out"):
        parts.append("[TIMED OUT]")
    if result.get("truncated"):
        parts.append("[output truncated]")
    if result["stdout"]:
        parts.append(f"--- stdout ---\n{result['stdout']}")
    if result["stderr"]:
        parts.append(f"--- stderr ---\n{result['stderr']}")
    return "\n".join(parts)


def _extract_diff(workdir: Path) -> str:
    """``git diff`` against the base commit — the final SWE-bench patch."""
    proc = subprocess.run(
        ["git", "diff", "--no-color"],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.stdout


def _anthropic_assistant_block(block: Any) -> Dict[str, Any]:
    """Convert an Anthropic content block back into the dict shape the API
    expects for assistant-role messages."""
    btype = getattr(block, "type", None)
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    if hasattr(block, "text"):
        return {"type": "text", "text": block.text}
    return {"type": btype or "unknown"}


# ---------- Reusable agent-loop entry point ----------


def run_swe_agent_loop(
    task: Dict[str, Any],
    *,
    backbone: str,  # "cloud" or "local"
    backbone_model: str,
    cloud_endpoint: str = "anthropic",
    local_endpoint: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    max_turns: int = 30,
    bash_timeout: int = 120,
    bash_timeout_s: Optional[int] = None,
    output_cap: int = 10_000,
    turn_max_tokens: int = 4096,
    trace_prefix: str = "mini_swe",
    workdir: Optional[Path] = None,
    compact_at_tokens: int = 24_000,
    compact_keep_last: int = 4,
) -> Dict[str, Any]:
    """Run a mini-SWE-agent loop for one SWE-bench task. Returns:

    .. code-block:: python

        {
          "answer":         str,   # final framed answer with ```diff fence
          "patch":          str,   # raw unified diff from git diff
          "final_summary":  str,   # the no-tool-call assistant text (may be empty)
          "tokens_in":      int,
          "tokens_out":     int,
          "tokens_local":   int,   # bookkeeping split for paradigms
          "tokens_cloud":   int,
          "cost_usd":       float,
          "turns":          int,
          "max_turns_hit":  bool,
          "workdir":        str,
        }

    Captures every bash invocation + LLM turn into the active trace buffer
    via :func:`_record_event` from the LocalCloudAgent base, so callers
    don't have to do their own per-call instrumentation.

    Args:
      task: SWE-bench-shaped dict with ``repo`` + ``base_commit`` + ``task_id``
        + (optional) ``problem_statement`` / ``hints_text``.
      backbone: ``"cloud"`` to drive the loop with the cloud model
        (Anthropic only today), ``"local"`` for vLLM.
      backbone_model: model id for the loop's backbone.
      cloud_endpoint / local_endpoint: SDK targets.
      initial_prompt: if set, used as the first user message (paradigms
        embed orchestrator context in here). If None, falls back to the
        task's problem_statement.
      workdir: pre-cloned repo path. If None, this function clones the
        repo into a tempdir and cleans it up at the end. Paradigms that
        want to chain multiple subloops over the same working tree can
        manage their own workdir.
    """
    if bash_timeout_s is not None:
        bash_timeout = int(bash_timeout_s)
    repo = task.get("repo") or ""
    base_commit = task.get("base_commit") or ""
    if not repo or not base_commit:
        raise ValueError(
            f"run_swe_agent_loop needs task['repo'] + task['base_commit']; "
            f"got repo={repo!r}, base_commit={base_commit!r}"
        )

    own_workdir = workdir is None
    if own_workdir:
        workdir = Path(tempfile.mkdtemp(prefix=f"mini-swe-{task.get('task_id', 'x')}-"))
        try:
            _clone_repo(repo, base_commit, workdir)
        except Exception:
            shutil.rmtree(workdir, ignore_errors=True)
            raise

    _record_event(
        {
            "kind": f"{trace_prefix}_setup",
            "repo": repo,
            "base_commit": base_commit,
            "workdir": str(workdir),
            "owns_workdir": own_workdir,
            "backbone": backbone,
            "backbone_model": backbone_model,
            "ts": time.time(),
        }
    )

    user_prompt = initial_prompt or task.get("problem_statement") or ""

    try:
        if backbone == "cloud":
            result = _loop_cloud(
                user_prompt,
                workdir,
                model=backbone_model,
                cloud_endpoint=cloud_endpoint,
                max_turns=max_turns,
                bash_timeout=bash_timeout,
                output_cap=output_cap,
                turn_max_tokens=turn_max_tokens,
                trace_prefix=trace_prefix,
            )
        elif backbone == "local":
            if not local_endpoint:
                raise ValueError(
                    "run_swe_agent_loop(backbone='local') needs local_endpoint"
                )
            result = _loop_local(
                user_prompt,
                workdir,
                model=backbone_model,
                endpoint=local_endpoint,
                max_turns=max_turns,
                bash_timeout=bash_timeout,
                output_cap=output_cap,
                turn_max_tokens=turn_max_tokens,
                trace_prefix=trace_prefix,
                compact_at_tokens=compact_at_tokens,
                compact_keep_last=compact_keep_last,
            )
        else:
            raise ValueError(f"unsupported backbone: {backbone!r}")

        patch = _extract_diff(workdir)
        framed = result["final_summary"] or "[mini-swe-agent produced no summary text]"
        if patch.strip():
            framed = f"{framed}\n\n```diff\n{patch}```"

        return {
            "answer": framed,
            "patch": patch,
            "final_summary": result["final_summary"],
            "tokens_in": result["tokens_in"],
            "tokens_out": result["tokens_out"],
            "tokens_local": result["tokens_in"] + result["tokens_out"]
            if backbone == "local"
            else 0,
            "tokens_cloud": result["tokens_in"] + result["tokens_out"]
            if backbone == "cloud"
            else 0,
            "cost_usd": (
                estimate_cost(backbone_model, result["tokens_in"], result["tokens_out"])
                if backbone == "cloud"
                else 0.0
            ),
            "turns": result["turns"],
            "max_turns_hit": result["max_turns_hit"],
            "workdir": str(workdir),
        }
    finally:
        if own_workdir:
            shutil.rmtree(workdir, ignore_errors=True)


# ---------- Cloud loop (dispatcher → per-endpoint multi-turn tool loops) ----------


def _loop_cloud(
    problem: str,
    workdir: Path,
    *,
    model: str,
    cloud_endpoint: str,
    max_turns: int,
    bash_timeout: int,
    output_cap: int,
    turn_max_tokens: int,
    trace_prefix: str,
) -> Dict[str, Any]:
    """Route to the right per-endpoint cloud loop. Anthropic path is the
    original byte-identical implementation (16 cells in the n=100 sweep
    depend on its exact behavior). OpenAI / Gemini paths added 2026-05-15
    to unblock the 8 SWE cells that were stuck on Anthropic-only support."""
    if cloud_endpoint == "anthropic":
        return _loop_cloud_anthropic(
            problem,
            workdir,
            model=model,
            max_turns=max_turns,
            bash_timeout=bash_timeout,
            output_cap=output_cap,
            turn_max_tokens=turn_max_tokens,
            trace_prefix=trace_prefix,
        )
    if cloud_endpoint == "openai":
        return _loop_cloud_openai(
            problem,
            workdir,
            model=model,
            max_turns=max_turns,
            bash_timeout=bash_timeout,
            output_cap=output_cap,
            turn_max_tokens=turn_max_tokens,
            trace_prefix=trace_prefix,
        )
    if cloud_endpoint == "gemini":
        return _loop_cloud_gemini(
            problem,
            workdir,
            model=model,
            max_turns=max_turns,
            bash_timeout=bash_timeout,
            output_cap=output_cap,
            turn_max_tokens=turn_max_tokens,
            trace_prefix=trace_prefix,
        )
    raise ValueError(
        f"mini-SWE-agent cloud backbone unsupported endpoint: {cloud_endpoint!r}"
    )


# ---------- Cloud loop (OpenAI multi-turn with function tools) ----------


# ---------- Cloud loop (Gemini multi-turn with function tools) ----------


# ---------- Local loop (vLLM, OpenAI-compatible multi-turn with tools) ----------

_COMPACT_PROMPT = (
    "Summarize the SWE-bench agent trajectory so far in under 2000 characters. "
    "Preserve: filenames touched, hypotheses tested, what worked, what failed, "
    "and the current plan. Be terse — no preamble, no quoted output, just facts."
)

_TIKTOKEN_ENC = None
_TIKTOKEN_WARNED = False


_EXIT_PATTERNS = (
    re.compile(r"exit_code\s*[=:]\s*(-?\d+)"),
    re.compile(r"returncode\s*[=:]\s*(-?\d+)"),
    re.compile(r"\bexit\s+(-?\d+)\b"),
)


# ---------- Standalone agent ----------


@AgentRegistry.register("mini_swe_agent")
class MiniSWEAgent(LocalCloudAgent):
    """Single-model bash-loop agent for SWE-bench-shaped tasks.

    Configurable knobs via ``cfg``:

    - ``backbone`` (str, default ``"cloud"``): ``"cloud"`` or ``"local"``.
    - ``max_turns`` (int, default 30): hard cap on tool turns.
    - ``bash_timeout_s`` (int, default 120): per-command timeout.
    - ``output_cap`` (int, default 10_000): per-command stdout/stderr cap.
    - ``turn_max_tokens`` (int, default 4096): max_tokens per LLM turn.
    """

    agent_id = "mini_swe_agent"
    required_capabilities = ("code:execute", "file:read", "file:write")

    def _run_paradigm(
        self,
        input: str,
        context: Optional[AgentContext],
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, Any]]:
        cfg = self._cfg
        task: Dict[str, Any] = {}
        if context is not None:
            task = context.metadata.get("task") or {}

        backbone = cfg.get("backbone", "cloud")
        model = self._cloud_model if backbone == "cloud" else (self._local_model or "")

        out = run_swe_agent_loop(
            task,
            backbone=backbone,
            backbone_model=model,
            cloud_endpoint=self._cloud_endpoint,
            local_endpoint=self._local_endpoint,
            initial_prompt=input,
            max_turns=int(cfg.get("max_turns", 30)),
            bash_timeout=int(cfg.get("bash_timeout_s", 120)),
            output_cap=int(cfg.get("output_cap", 10_000)),
            turn_max_tokens=int(cfg.get("turn_max_tokens", 4096)),
        )
        meta = {
            "tokens_local": out["tokens_local"],
            "tokens_cloud": out["tokens_cloud"],
            "cost_usd": out["cost_usd"],
            "turns": out["turns"],
            "traces": {
                "backbone": backbone,
                "max_turns_hit": out["max_turns_hit"],
                "patch_chars": len(out["patch"]),
                "final_summary": out["final_summary"],
            },
        }
        return out["answer"], meta


__all__ = ["MiniSWEAgent", "run_swe_agent_loop", "SYSTEM_PROMPT"]


# The cloud and local loops live in their own modules; they look helpers up
# here, so behaviour (and anything patched here) is unchanged.
from openjarvis.agents.hybrid import mini_swe_local_loop as _local  # noqa: E402,I001
from openjarvis.agents.hybrid.mini_swe_cloud_loops import (  # noqa: E402,I001
    _loop_cloud_anthropic,
    _loop_cloud_gemini,
    _loop_cloud_openai,
)

_get_tiktoken_enc = _local._get_tiktoken_enc
_estimate_prompt_tokens = _local._estimate_prompt_tokens
_parse_exit_code = _local._parse_exit_code
_identify_turns = _local._identify_turns
_compact_local_messages = _local._compact_local_messages
_loop_local = _local._loop_local

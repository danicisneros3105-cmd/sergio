"""The coding tools, registered for agents: long documents, TDD, refactors,
debugging, review, docs drift, optimisation and polyglot run/translate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import ToolSpec
from openjarvis.tools.deep_think_tool import EngineTool


def _spec(name: str, description: str, props: dict[str, Any], required: list[str]) -> ToolSpec:
    return ToolSpec(name=name, description=description,
                    parameters={"type": "object", "properties": props, "required": required},
                    category="coding", cost_estimate=0.01, latency_estimate=30.0)


def _run(name: str, fn: Callable[[], Any]) -> ToolResult:
    try:
        out = fn()
    except Exception as exc:  # noqa: BLE001 — tell the agent, don't crash it
        return ToolResult(tool_name=name, content=f"{name} failed: {exc}", success=False)
    text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=1, default=str)
    return ToolResult(tool_name=name, content=text[:20000], success=True)


S = {"type": "string"}


@ToolRegistry.register("long_context_qa")
class LongContextTool(EngineTool):
    tool_id = "long_context_qa"

    @property
    def spec(self) -> ToolSpec:
        return _spec("long_context_qa", "Answer a question about a very long file or text (books, logs, codebases) "
                     "with citations to line ranges.", {"question": S, "path": S, "text": S}, ["question"])

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.intelligence.long_context import answer_long

        def go() -> dict:
            text = Path(p["path"]).read_text("utf-8", errors="replace") if p.get("path") else str(p.get("text") or "")
            r = answer_long(p["question"], text, self.llm())
            return {"answer": r.answer, "chunks_read": r.read, "chunks_total": r.chunks}

        return _run("long_context_qa", go)


@ToolRegistry.register("tdd_codegen")
class TDDTool(EngineTool):
    tool_id = "tdd_codegen"

    @property
    def spec(self) -> ToolSpec:
        return _spec("tdd_codegen", "Write Python code test-first: generates pytest tests from a spec, then the code, "
                     "and runs the tests until they pass.", {"spec": S, "module": S}, ["spec"])

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.tools.code_generator import tdd

        def go() -> dict:
            r = tdd(p["spec"], self.llm(), module=p.get("module") or "solution")
            return {"passed": r.ok, "rounds": r.rounds, "code": r.code, "tests": r.tests,
                    "pytest": r.last_run.output[-1500:]}

        return _run("tdd_codegen", go)


@ToolRegistry.register("safe_refactor")
class RefactorTool(EngineTool):
    tool_id = "safe_refactor"

    @property
    def spec(self) -> ToolSpec:
        return _spec("safe_refactor", "Refactor several files at once, safely: a symbol rename (old_name/new_name) or "
                     "an instruction; compiles and runs test_cmd, rolling everything back on failure.",
                     {"root": S, "old_name": S, "new_name": S, "instruction": S,
                      "files": {"type": "array", "items": S}, "test_cmd": S}, ["root"])

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.tools.refactor import llm_refactor, rename_symbol

        root = Path(p["root"])
        files = [root / f for f in p.get("files") or []]

        def go() -> dict:
            if p.get("old_name") and p.get("new_name"):
                r = rename_symbol(root, p["old_name"], p["new_name"], files=files or None, test_cmd=p.get("test_cmd", ""))
            else:
                r = llm_refactor(p.get("instruction", ""), files, self.llm(), test_cmd=p.get("test_cmd", ""), cwd=root)
            return {"ok": r.ok, "changed": r.changed, "reason": r.reason, "summary": r.summary, "renames": r.renames}

        return _run("safe_refactor", go)


@ToolRegistry.register("debug_trace")
class DebugTool(EngineTool):
    tool_id = "debug_trace"

    @property
    def spec(self) -> ToolSpec:
        return _spec("debug_trace", "Find the root cause of a crash: give a stack trace (Python or JavaScript) or a "
                     "command to run; returns the frame that matters, the cause and a fix.",
                     {"traceback": S, "command": S, "cwd": S}, [])

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.tools.debugger import analyse, debug_run

        def go() -> Any:
            if p.get("command"):
                d = debug_run(p["command"], self.llm(), cwd=p.get("cwd"))
                if d is None:
                    return "The command ran without a stack trace."
            else:
                d = analyse(p.get("traceback", ""), self.llm(), root=Path(p["cwd"]) if p.get("cwd") else None)
            return {"exception": f"{d.trace.exc_type}: {d.trace.message}",
                    "where": f"{d.culprit.file}:{d.culprit.line} in {d.culprit.func}", "hint": d.hint,
                    "root_cause": d.root_cause, "fix": d.fix, "patch": d.patch}

        return _run("debug_trace", go)


@ToolRegistry.register("code_review")
class ReviewTool(EngineTool):
    tool_id = "code_review"

    @property
    def spec(self) -> ToolSpec:
        return _spec("code_review", "Review code for real bugs: static checks (ruff, AST, secrets) plus a model review "
                     "of a git diff or files, ranked by severity.",
                     {"paths": {"type": "array", "items": S}, "repo": S, "base": S}, [])

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.tools.code_review import as_dicts, git_diff, review

        def go() -> list:
            paths = [Path(x) for x in p.get("paths") or []]
            diff = git_diff(Path(p["repo"]), p.get("base") or "HEAD") if p.get("repo") else ""
            if p.get("repo") and not paths:
                paths = [Path(p["repo"]) / line[6:] for line in diff.splitlines() if line.startswith("+++ b/")]
            return as_dicts(review(paths, self.llm(), diff=diff))

        return _run("code_review", go)


@ToolRegistry.register("doc_drift")
class DocsTool(EngineTool):
    tool_id = "doc_drift"

    @property
    def spec(self) -> ToolSpec:
        return _spec("doc_drift", "Find documentation that no longer matches the code (docstring params, returns, "
                     "Markdown references) and optionally write missing docstrings.",
                     {"paths": {"type": "array", "items": S}, "markdown": {"type": "array", "items": S},
                      "write_docstrings": {"type": "boolean"}}, ["paths"])

    def execute(self, **p: Any) -> ToolResult:
        from dataclasses import asdict

        from openjarvis.tools.doc_generator import (
            add_docstrings,
            docstring_drift,
            markdown_drift,
        )

        def go() -> dict:
            paths = [Path(x) for x in p["paths"]]
            drift = [asdict(d) for path in paths if path.suffix == ".py" for d in docstring_drift(path)]
            drift += [asdict(d) for md in p.get("markdown") or [] for d in markdown_drift(Path(md), paths)]
            written = 0
            if p.get("write_docstrings"):
                for path in paths:
                    new, n = add_docstrings(path.read_text("utf-8"), self.llm())
                    if n:
                        path.write_text(new, "utf-8")
                        written += n
            return {"drift": drift, "docstrings_written": written}

        return _run("doc_drift", go)


@ToolRegistry.register("optimize_code")
class OptimizeTool(EngineTool):
    tool_id = "optimize_code"

    @property
    def spec(self) -> ToolSpec:
        return _spec("optimize_code", "Profile a Python script (hotspots), or speed up one function: the faster version "
                     "is kept only if it gives the same results and is measured faster.",
                     {"script": S, "source": S, "function": S, "inputs_json": S}, [])

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.tools.optimizer import (
            format_profile,
            optimize_function,
            profile_script,
        )

        def go() -> Any:
            if p.get("script"):
                return format_profile(profile_script(Path(p["script"])))
            r = optimize_function(p["source"], p["function"], json.loads(p.get("inputs_json") or "[]"), self.llm())
            return {"accepted": r.accepted, "speedup": r.speedup, "reason": r.reason,
                    "code": r.candidate if r.accepted else r.original}

        return _run("optimize_code", go)


@ToolRegistry.register("polyglot")
class PolyglotTool(EngineTool):
    tool_id = "polyglot"

    @property
    def spec(self) -> ToolSpec:
        return _spec("polyglot", "Run code in Python, JavaScript, TypeScript, Bash, Ruby, Go, Rust, C, C++, Java, PHP or "
                     "Lua, or translate code between them (verified by comparing outputs).",
                     {"code": S, "language": S, "translate_to": S, "stdin": S}, ["code"])

    def execute(self, **p: Any) -> ToolResult:
        from openjarvis.tools.polyglot import detect, run, translate

        def go() -> dict:
            lang = p.get("language") or detect(p["code"])
            if p.get("translate_to"):
                t = translate(p["code"], p["translate_to"], self.llm(), source=lang,
                              stdin_cases=(p.get("stdin") or "",))
                return {"code": t.code, "verified": t.verified, "note": t.note}
            r = run(p["code"], lang, p.get("stdin") or "")
            return {"ok": r.ok, "language": r.language, "stdout": r.stdout[-8000:], "stderr": r.stderr[-2000:]}

        return _run("polyglot", go)


__all__ = ["DebugTool", "DocsTool", "LongContextTool", "OptimizeTool", "PolyglotTool", "RefactorTool", "ReviewTool",
           "TDDTool"]

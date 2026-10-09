"""Self-correction loop: generate -> check -> reflect -> generate again.

Built as a LangGraph state machine (the graph is explicit: nodes, a
conditional edge and a round limit), with a plain loop as fallback when
LangGraph is not installed. Every failed check becomes a written
reflection the next attempt reads; when an attempt passes after failing,
the fix is stored as a lesson in long-term memory.
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict


class State(TypedDict, total=False):
    task: str
    notes: list[str]
    candidate: Any
    ok: bool
    report: str
    rounds: int
    history: list[dict[str, Any]]


Generate = Callable[[str, list[str]], Any]
Check = Callable[[Any], tuple[bool, str]]
Reflect = Callable[[str, Any, str], str]


def _default_reflect(task: str, candidate: Any, report: str) -> str:
    return f"Attempt failed the check: {report}. Fix exactly that and keep everything that already works."


def self_correct(
    task: str,
    generate: Generate,
    check: Check,
    reflect: Reflect | None = None,
    max_rounds: int = 3,
    remember: Callable[[str], Any] | None = None,
    topic: str = "",
) -> dict[str, Any]:
    """Run the loop. Returns {"result", "ok", "rounds", "history", "engine"}.
    *remember* (e.g. memory.remember for lessons) receives what fixed a
    failure, so the next similar task starts with it."""
    reflect = reflect or _default_reflect

    def gen_node(state: State) -> State:
        candidate = generate(state["task"], state.get("notes", []))
        return {"candidate": candidate, "rounds": state.get("rounds", 0) + 1}

    def check_node(state: State) -> State:
        try:
            ok, report = check(state["candidate"])
        except Exception as exc:  # noqa: BLE001 — a crashing check is a failed check
            ok, report = False, f"{type(exc).__name__}: {exc}"
        history = [
            *state.get("history", []),
            {"round": state["rounds"], "ok": ok, "report": report[:500]},
        ]
        return {"ok": ok, "report": report, "history": history}

    def reflect_node(state: State) -> State:
        note = reflect(state["task"], state["candidate"], state["report"])
        return {"notes": [*state.get("notes", []), note]}

    def route(state: State) -> str:
        return "done" if state["ok"] or state["rounds"] >= max_rounds else "again"

    start: State = {"task": task, "notes": [], "rounds": 0, "history": []}
    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(State)
        graph.add_node("generate", gen_node)
        graph.add_node("check", check_node)
        graph.add_node("reflect", reflect_node)
        graph.add_edge(START, "generate")
        graph.add_edge("generate", "check")
        graph.add_conditional_edges("check", route, {"done": END, "again": "reflect"})
        graph.add_edge("reflect", "generate")
        final = graph.compile().invoke(start, {"recursion_limit": 4 * max_rounds + 4})
        engine = "langgraph"
    except ImportError:
        final = dict(start)
        while True:
            final.update(gen_node(final))
            final.update(check_node(final))
            if route(final) == "done":
                break
            final.update(reflect_node(final))
        engine = "loop"
    failures = [h["report"] for h in final.get("history", []) if not h["ok"]]
    if remember and final.get("ok") and failures:
        try:
            remember(
                f"{topic or task[:80]}: un intento falló por «{failures[-1][:200]}» y se corrigió en la ronda "
                f"{final['rounds']}."
            )
        except Exception:  # noqa: BLE001 — memory is a bonus
            pass
    return {
        "result": final.get("candidate"),
        "ok": bool(final.get("ok")),
        "rounds": final.get("rounds", 0),
        "history": final.get("history", []),
        "engine": engine,
    }


__all__ = ["self_correct"]

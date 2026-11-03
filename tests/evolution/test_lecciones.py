"""Self-improvement remembers why a try was rejected (no blind repeats)."""

from __future__ import annotations

from openjarvis.evolution import automejora as A
from openjarvis.tools.automejora_tool import AutomejoraTool


def _rows(*items):
    return [
        {"id": str(i), "state": s, "files": f, "reason": r, "checks": c}
        for i, (s, f, r, c) in enumerate(items)
    ]


def test_lessons_list_only_rejected_tries_newest_first(monkeypatch):
    rows = _rows(
        ("rechazada", ["a.py"], "primero", "ruff ok\npruebas fallan"),
        ("aplicada", ["b.py"], "bien", "todo ok"),
        ("rechazada", ["c.py"], "segundo", "ruff: E501"),
    )
    monkeypatch.setattr(A, "history", lambda: rows)
    got = A.lessons()
    assert [r["reason"] for r in got] == ["segundo", "primero"]
    assert got[1]["why"] == "pruebas fallan"
    assert A.failed_before(["a.py", "z.py"]) == 1 and A.failed_before(["b.py"]) == 0


def test_tool_shows_lessons_and_warns_after_repeated_failures(monkeypatch):
    rows = _rows(
        ("rechazada", ["a.py"], "uno", "x"), ("rechazada", ["a.py"], "dos", "y")
    )
    monkeypatch.setattr(A, "history", lambda: rows)
    out = AutomejoraTool().execute(action="lecciones")
    assert out.success and "dos" in out.content and "uno" in out.content

    def fake(reason, changes, **k):
        return A.Mejora("id", reason, ["a.py"], state="rechazada", checks="falló")

    monkeypatch.setattr(A, "improve", fake)
    res = AutomejoraTool().execute(
        action="probar", motivo="otro", cambios=[{"path": "a.py", "new": "x"}]
    )
    assert not res.success and "lecciones" in res.content

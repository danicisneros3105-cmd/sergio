"""`sergio pensar`: a question by default, practice, improvement and status."""

from __future__ import annotations

import json

from click.testing import CliRunner

from openjarvis.cli.pensar_cmd import pensar
from openjarvis.intelligence import _llm


def _fake(monkeypatch, tmp_path, fn):
    monkeypatch.setenv("OPENJARVIS_HOME", str(tmp_path))
    monkeypatch.setattr(_llm.LLM, "default", classmethod(lambda cls: cls(fn)))


def test_a_bare_question_is_answered_with_confidence(monkeypatch, tmp_path):
    def fn(prompt):
        if "CONSTITUTION" in prompt:
            return '{"violations": []}'
        if "PROPOSED ANSWER" in prompt:
            return '{"confidence": 90, "unknowns": ["la zona horaria"]}'
        return "FINAL ANSWER: 17:25"

    _fake(monkeypatch, tmp_path, fn)
    out = CliRunner().invoke(pensar, ["¿a", "qué", "hora", "llega?", "--estrategia", "consistency"])
    assert out.exit_code == 0, out.output
    assert "17:25" in out.output and "Estrategia: consistency" in out.output and "zona horaria" in out.output
    js = CliRunner().invoke(pensar, ["preguntar", "x", "--json", "--estrategia", "direct"])
    assert json.loads(js.output)["strategy"] == "direct"


def test_practice_moves_levels_and_status_shows_them(monkeypatch, tmp_path):
    def fn(prompt):
        if "Compute exactly:" in prompt:
            expr = prompt.split("Compute exactly:")[1].split("\n")[0]
            return f"FINAL ANSWER: {eval(expr)}"  # noqa: S307 — generated digits only
        return "FINAL ANSWER: ?"

    _fake(monkeypatch, tmp_path, fn)
    out = CliRunner().invoke(pensar, ["practicar", "--rondas", "2", "--lote", "3", "--temas", "arithmetic"])
    assert out.exit_code == 0, out.output and "arithmetic: nivel 1 → 3" in out.output
    assert "arithmetic: nivel 1 → 3" in out.output
    status = CliRunner().invoke(pensar, ["estado"])
    assert "arithmetic 3" in status.output


def test_improve_keeps_the_better_prompt(monkeypatch, tmp_path):
    def fn(prompt):
        if "You improve instructions" in prompt or "REWRITING" in prompt:
            return '{"prompts": ["Be exact. Solve the problem. End with: FINAL ANSWER: <answer>"]}'
        return "FINAL ANSWER: 0"

    _fake(monkeypatch, tmp_path, fn)
    out = CliRunner().invoke(pensar, ["mejorar", "--rondas", "1"])
    assert out.exit_code == 0, out.output and "Aciertos:" in out.output
    assert (tmp_path / "intelligence" / "solve_prompt.json").exists()

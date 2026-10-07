"""Permanent skills: built-in and learned rules that load by topic."""

from __future__ import annotations

from openjarvis.coach import skills


def test_built_in_skills_load_by_topic():
    names = [s["nombre"] for s in skills.match("hazme un render en Blender de una silla")]
    assert names[0] == "Blender de producción"
    rules = skills.rules_for("gradea este clip S-Log3 en DaVinci para YouTube")
    assert "0.336" in rules and "Rec.709" in rules
    assert skills.rules_for("¿qué hora es?") == ""
    assert len(skills.rules_for("compara cada uno de estos productos y haz un informe en blender con color")) <= skills.MAX_CHARS


def test_a_manual_becomes_a_skill_that_loads_by_itself(tmp_path):
    seen = {}

    def ask(prompt, **kw):
        seen.update(kw)
        return {"nombre": "Fotografía de producto", "claves": ["foto de producto", "fondo blanco"],
                "reglas": ["Luz difusa a 45°", "Fondo blanco puro"]}

    saved = skills.learn("", "manual", ask=ask, folder=tmp_path, pdf=b"%PDF-1.4 fake")
    assert saved["reglas"] == 2 and seen["media"][0][1] == "application/pdf"
    rules = skills.rules_for("haz una foto de producto con fondo blanco", (tmp_path,))
    assert "Luz difusa a 45°" in rules

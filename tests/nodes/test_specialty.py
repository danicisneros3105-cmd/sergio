"""Each Node does something the others do not, and code checks it delivers."""

from __future__ import annotations

from openjarvis.nodes import specialty


def test_each_node_has_its_own_instruments_and_way_of_thinking():
    s = specialty.SPECIALTIES
    assert "image_generate" in s["hous"].toolkit and "image_generate" not in s["tennessee"].toolkit
    assert "web_search" in s["manchas"].toolkit
    assert "verified_math" in s["tennessee"].toolkit
    assert s["tennessee"].effort == "high" and s["tennessee"].temperature < s["hous"].temperature
    assert len({sp.does for sp in s.values()}) == 4


def test_the_toolkit_adds_to_the_owners_rules_without_repeating():
    tools = specialty.tools_with_toolkit("hous", ["web_search", "file_write"])
    assert tools[:2] == ["web_search", "file_write"]
    assert tools.count("web_search") == 1 and "video_create" in tools
    assert specialty.tools_with_toolkit("", ["a"]) == ["a"]


def test_tennessee_always_gives_a_verdict_with_numbers():
    assert "Veredicto" in specialty.missing("tennessee", "¿Me conviene?", "Depende.", [])
    assert "números" in specialty.missing("tennessee", "x", "Veredicto: no conviene.", [])
    assert specialty.missing("tennessee", "x", "Margen 12 %.\nVeredicto: no conviene.", []) is None


def test_hous_shows_the_visual_when_one_is_asked_for():
    lack = specialty.missing("hous", "Hazme un logo para la cafetería", "Pensé en un grano.", [])
    assert "image_generate" in lack
    assert specialty.missing("hous", "Hazme un logo", "Listo.", ["image_generate"]) is None
    assert specialty.missing("hous", "¿Qué opinas del nombre?", "Me gusta.", []) is None


def test_manchas_cites_what_it_found():
    answer = "Hay tres tendencias. Fuentes: https://a.example/1"
    assert "fuentes" in specialty.missing("manchas", "investiga", answer, ["web_search"])
    two = answer + " https://b.example/2"
    assert specialty.missing("manchas", "investiga", two, ["web_search"]) is None
    assert specialty.missing("manchas", "hola", "Hola, señor.", []) is None


def test_rihno_says_first_what_is_ready():
    long_first = "x" * 200 + "\nresto"
    assert specialty.missing("rihno", "ordena", long_first, []) is not None
    assert specialty.missing("rihno", "ordena", "Listo: escritorio ordenado.\n- a", []) is None

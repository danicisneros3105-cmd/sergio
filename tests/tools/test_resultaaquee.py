"""Tests for ResultaQuee video creation, 3D cutaway explainer style, and connectome integration."""

from __future__ import annotations

import json

from openjarvis.connectome import neurons
from openjarvis.tools import commerce_intel as ci
from openjarvis.tools.app_control import SergioAppControlTool
from openjarvis.tools.video_create import build_social_pack, plan
from openjarvis.tools.video_style import available, find_style
from openjarvis.video_essay import genres


def test_resultaaquee_style_profile_is_available_and_findable():
    styles = available()
    slugs = [s["slug"] for s in styles]
    assert "resultaaquee" in slugs

    style = find_style("resultaaquee")
    assert style is not None
    assert style["name"] == "Resulta Quee"
    assert style["aspect"] == "9:16"
    assert style["text"]["accent"] == "#00FFA3"
    assert "Seamless Loop" in "".join(style["signature"])

    # Aliases
    alias_match = find_style("resulta que")
    assert alias_match is not None
    assert alias_match["slug"] == "resultaaquee"


def test_genres_detects_resultaaquee_and_applies_motion_pass():
    prompt1 = "Haz un reel estilo resultaaquee sobre por que los aviones tienen un agujero en la ventana"
    assert genres.detect(prompt1) == "resultaaquee"

    prompt2 = "por que la pantalla de tu movil siente tu dedo y el plastico nada"
    assert genres.detect(prompt2) == "resultaaquee"

    g = genres.GENRES["resultaaquee"]
    assert g.style == "resultaaquee"
    assert g.name.startswith("Resulta Quee")


def test_plan_uses_resultaaquee_script_formula(monkeypatch):
    captured_prompt = []

    def fake_ask(prompt_text, json_mode=True, check=None):
        captured_prompt.append(prompt_text)
        return json.dumps(
            {
                "title": "El Secreto de la Pantalla",
                "scenes": [
                    {
                        "say": "¿Por qué tu móvil detecta tu dedo pero un lápiz plástico no hace nada?",
                        "picture": "3D isometric cutaway render of a modern smartphone glass screen showing capacitive grid layer and glowing electrons on dark studio background.",
                    },
                    {
                        "say": "Todos creen que es por la presión o el calor de tu piel, pero eso es falso.",
                        "picture": "Macro X-Ray view of glass cross section showing capacitive electrostatic field lines undisturbed by plastic pen.",
                    },
                    {
                        "say": "Resulta que tu cuerpo conduce electricidad y distorsiona el campo electrostático al tocar el cristal.",
                        "picture": "Neon green energy discharge and electron flux from human fingertip into indium tin oxide sensor matrix.",
                    },
                    {
                        "say": "Por eso con guantes de lana no funciona, a menos que tengan hilo de plata conductor.",
                        "picture": "Exploded 3D view of capacitive touch controller IC chip processing touch coordinates with high precision.",
                    },
                ],
            }
        )

    script = plan(
        "Por qué la pantalla táctil detecta tu dedo",
        4,
        ask=fake_ask,
        style="resultaaquee",
    )
    assert len(script["scenes"]) == 4
    assert len(captured_prompt) == 1
    assert (
        "RESULTA_QUE_SCRIPT_PROMPT" in str(plan)
        or "@resultaaquee" in captured_prompt[0]
    )


def test_build_social_pack_generates_viral_kit():
    scenes = [
        {"say": "¿Por qué las ventanas de los aviones tienen un agujero diminuto?"},
        {
            "say": "Resulta que equilibra la presión entre el cristal exterior y la cabina."
        },
        {"say": "Por eso nunca debes preocuparte cuando veas..."},
    ]
    pack = build_social_pack(
        "Por qué los aviones tienen un agujero en la ventana",
        "El Agujero del Avión",
        scenes,
    )
    assert "¿Por qué" in pack["titulo_viral"]
    assert "#resultaque" in pack["copy_publicacion"]
    assert "💬" in pack["comentario_fijado"]
    assert "conecta gramaticalmente" in pack["bucle_infinito"]


def test_sergio_app_control_handles_resultaaquee_action():
    tool = SergioAppControlTool()
    res = tool.execute(
        action="video_create",
        platform="resultaaquee",
        content="Por qué las ventanas de los aviones tienen un diminuto agujero",
    )
    assert res.success
    assert "resultaaquee" in res.content
    assert "subtítulos sincronizados sin retraso" in res.content


def test_connectome_neuron_selects_video_for_resultaaquee():
    phrase = (
        "Sergio, haz un video estilo resultaaquee explicando como funciona el Face ID"
    )
    sel = neurons.select(neurons.normalise(phrase), {})
    assert sel is not None
    assert "video" in sel.neurons or "sergio_app" in sel.tools


def test_concierge_enhanced_mandate_and_tracking_code(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    plan_res = ci.execute_concierge_plan(
        "Mi vuelo comercial se canceló. Necesito un jet privado listo en dos horas y suite de lujo preparada.",
        category_hint="travel_aviation",
        destination="Ginebra / Suiza",
        when="en 2 horas",
    )
    assert plan_res["codigo_seguimiento"].startswith("CNG-TRA-")
    assert plan_res["sla_minutos"] == 15
    assert "VIP MANDATE & EXECUTIVE REQUISITION" in plan_res["carta_vip_mandato"]
    assert "travel_aviation" == plan_res["categoria_clave"]
    assert plan_res["ruta_tier1"]["nombre"] != ""
    assert plan_res["ruta_tier2"]["nombre"] != ""

    dossier = tmp_path / "Sergio" / "concierge"
    files = list(dossier.glob("orden_*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert plan_res["codigo_seguimiento"] in content
    assert "Carta de Requerimiento VIP" in content
    assert "Ruta Tier 1" in content
    assert "Ruta Tier 2" in content

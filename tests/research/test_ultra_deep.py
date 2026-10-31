"""Tests for Ultra Deep Research: 10 specialist dimensions, parallel workers,
forensic quote verification, confidence score, and executive synthesis."""

from __future__ import annotations

import json

from openjarvis.research.deep import (
    ULTRA_PERSPECTIVES,
    Report,
    UltraDeepResearch,
)
from openjarvis.tools.deep_research_web import DeepResearchWebTool

PAGES = {
    "https://tech.example/spec": "El motor de micro-rotor calibre 240 tiene 27 rubíes y una reserva de marcha de 48 horas certificada por el laboratorio suizo.",
    "https://market.example/price": "En subasta pública el reloj de micro-rotor alcanzó un valor histórico de 85.000 dólares con garantía de procedencia.",
    "https://patent.example/doc": "Patente oficial registrada CH-78923 describe el mecanismo de micro-rotor integrado con masa oscilante de platino 22K.",
    "https://critics.example/review": "Varios coleccionistas reportan que el calibre de micro-rotor requiere mantenimiento riguroso cada 3 años.",
}


def fake_search(query, count):
    return [
        {"title": "Doc", "url": u, "snippet": PAGES.get(u, "")[:40]} for u in PAGES
    ][:count]


def fake_fetch(url):
    if url not in PAGES:
        raise OSError("no abre")
    return PAGES[url] * 2


class FakeUltraModel:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt[:40])
        if (
            "Eres un director de investigación" in prompt
            or "Eres un investigador" in prompt
        ):
            return json.dumps(
                {
                    "subpreguntas": [
                        f"[{p[0]}] ¿Detalles de {p[1]}?" for p in ULTRA_PERSPECTIVES
                    ],
                    "busquedas": [f"query {p[0]}" for p in ULTRA_PERSPECTIVES],
                }
            )
        if prompt.startswith("Lee la fuente"):
            if "micro-rotor calibre 240" in prompt:
                return json.dumps(
                    [
                        {
                            "afirmacion": "Calibre 240 con 27 rubíes y 48h de marcha",
                            "cita": "calibre 240 tiene 27 rubíes y una reserva de marcha de 48 horas",
                            "subpregunta": "Técnico",
                        }
                    ]
                )
            if "85.000 dólares" in prompt:
                return json.dumps(
                    [
                        {
                            "afirmacion": "Valor de subasta de 85.000 USD",
                            "cita": "reloj de micro-rotor alcanzó un valor histórico de 85.000 dólares",
                            "subpregunta": "Precios",
                        }
                    ]
                )
            if "Patente oficial registrada" in prompt:
                return json.dumps(
                    [
                        {
                            "afirmacion": "Patente oficial CH-78923 con platino 22K",
                            "cita": "Patente oficial registrada CH-78923 describe el mecanismo",
                            "subpregunta": "Patentes",
                        }
                    ]
                )
            return "[]"
        if prompt.startswith("Agrupa"):
            lines = [line for line in prompt.splitlines() if line[:1].isdigit()]
            groups = []
            for line in lines:
                idx = int(line.split(".", 1)[0])
                txt = line.split("] ", 1)[1]
                groups.append({"afirmacion": txt, "ids": [idx], "contra": []})
            return json.dumps(groups)
        if prompt.startswith("Compara las subpreguntas"):
            return json.dumps({"sin_respuesta": [], "busquedas": []})
        if prompt.startswith("Escribe un informe"):
            return "El calibre micro-rotor presenta alta precisión técnica [1], valoración de 85.000 USD [2] y patente verificada [3]."
        return "{}"


def test_ultra_deep_research_runs_10_perspectives_and_computes_confidence_score():
    events = []
    model = FakeUltraModel()
    udr = UltraDeepResearch(
        model,
        fake_search,
        fake_fetch,
        rounds=2,
        workers=10,
        on_event=lambda k, d: events.append(k),
    )
    report = udr.run("Reloj Patek Philippe micro-rotor calibre 240 edición limitada")

    assert isinstance(report, Report)
    assert len(udr.perspectives) == 10
    assert report.confidence_score > 0.0
    assert "ultra_plan" in events
    assert "ultra_listo" in events
    md = report.markdown()
    assert "Informe Ejecutivo de Ultra Deep Research" in md
    assert "Score de Certeza y Rigor:" in md
    assert "Fuentes" in md


def test_deep_research_web_tool_supports_ultra_mode():
    tool = DeepResearchWebTool()
    assert tool.spec.name == "investigacion_profunda"
    assert "workers" in tool.spec.parameters["properties"]
    assert "mode" in tool.spec.parameters["properties"]

    # When asked for ultra deep research
    res = tool.execute(
        question="investiga ultra deep a fondo con 10 humanos el mercado de litio",
        mode="ultra",
    )
    assert res.tool_name == "investigacion_profunda"

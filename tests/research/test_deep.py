# ruff: noqa: E501
"""Deep research: plan, wide search, reading, quotes checked by code, sites
cross-checked, a second round for gaps, and a report with only real citations."""

from __future__ import annotations

import json

from openjarvis.research.deep import DeepResearch, parse_results, quote_in, site_of

PAGES = {
    "https://a.example/fold": "El teléfono plegable pesa 215 gramos y su pantalla interior mide 8 pulgadas según las pruebas del laboratorio independiente.",
    "https://b.example/review": "En nuestra revisión confirmamos que el teléfono plegable pesa 215 gramos, más ligero que la generación anterior.",
    "https://a.example/otro": "La batería dura un día completo de uso intenso con la pantalla interior encendida la mayor parte del tiempo.",
    "https://c.example/rumor": "Un filtrador asegura que el teléfono plegable pesa 240 gramos y llegará en marzo con un precio mayor.",
    "https://d.example/precio": "El precio de lanzamiento del teléfono plegable es de 1.999 dólares en Estados Unidos y Europa.",
}


def fake_search(query, count):
    if "precio" in query:
        return [
            {"title": "Precio", "url": "https://d.example/precio", "snippet": "precio"}
        ]
    return [
        {"title": t, "url": u, "snippet": PAGES.get(u, "")[:40]}
        for t, u in [
            ("A", "https://a.example/fold"),
            ("B", "https://b.example/review"),
            ("A2", "https://a.example/otro"),
            ("A3", "https://a.example/tercera"),  # third page of a.example: left out
            ("C", "https://c.example/rumor"),
        ]
    ][:count]


def fake_fetch(url):
    if url not in PAGES:
        raise OSError("no abre")
    return PAGES[url] * 3


class FakeModel:
    """Answers each step like a careful model would, plus one invented quote."""

    def __init__(self):
        self.calls = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt[:40])
        if prompt.startswith("Eres un investigador"):
            return json.dumps(
                {
                    "subpreguntas": ["¿Cuánto pesa?", "¿Cuánto cuesta?"],
                    "busquedas": ["peso plegable", "review plegable"],
                }
            )
        if prompt.startswith("Lee la fuente"):
            src = prompt.split("Fuente [", 1)[1]
            sid = int(src.split("]", 1)[0])
            if "215 gramos y su pantalla" in src:
                return json.dumps(
                    [
                        {
                            "afirmacion": "Pesa 215 g",
                            "cita": "el teléfono plegable pesa 215 gramos y su pantalla interior mide 8 pulgadas",
                            "subpregunta": "peso",
                        },
                        {
                            "afirmacion": "Es resistente al agua",
                            "cita": "certificado IP68 contra el agua",
                            "subpregunta": "peso",
                        },  # invented
                    ]
                )
            if "revisión" in src:
                return json.dumps(
                    [
                        {
                            "afirmacion": "Pesa 215 g",
                            "cita": "confirmamos que el teléfono plegable pesa 215 gramos",
                            "subpregunta": "peso",
                        }
                    ]
                )
            if "filtrador" in src:
                return json.dumps(
                    [
                        {
                            "afirmacion": "Pesa 240 g",
                            "cita": "asegura que el teléfono plegable pesa 240 gramos",
                            "subpregunta": "peso",
                        }
                    ]
                )
            if "1.999" in src:
                return json.dumps(
                    [
                        {
                            "afirmacion": "Cuesta 1.999 dólares",
                            "cita": "El precio de lanzamiento del teléfono plegable es de 1.999 dólares",
                            "subpregunta": "precio",
                        }
                    ]
                )
            return f"[] fuente {sid}"
        if prompt.startswith("Agrupa"):
            lines = [line for line in prompt.splitlines() if line[:1].isdigit()]
            ids = {
                text: int(line.split(".", 1)[0])
                for line in lines
                for text in [line.split("] ", 1)[1]]
            }
            groups = []
            same = [
                int(line.split(".", 1)[0])
                for line in lines
                if line.endswith("Pesa 215 g")
            ]
            against = [
                int(line.split(".", 1)[0])
                for line in lines
                if line.endswith("Pesa 240 g")
            ]
            if same:
                groups.append(
                    {"afirmacion": "Pesa 215 g", "ids": same, "contra": against}
                )
            if "Cuesta 1.999 dólares" in ids:
                groups.append(
                    {
                        "afirmacion": "Cuesta 1.999 dólares",
                        "ids": [ids["Cuesta 1.999 dólares"]],
                        "contra": [],
                    }
                )
            return json.dumps(groups)
        if prompt.startswith("Compara las subpreguntas"):
            if "1.999" in prompt:
                return json.dumps({"sin_respuesta": [], "busquedas": []})
            return json.dumps(
                {"sin_respuesta": ["¿Cuánto cuesta?"], "busquedas": ["precio plegable"]}
            )
        if prompt.startswith("Escribe un informe"):
            return "Pesa 215 g [1][2], aunque un rumor dice 240 g [4]. Cuesta 1.999 dólares [5]. Dato suelto [9]."
        return "{}"


def run():
    model = FakeModel()
    events = []
    report = DeepResearch(
        model, fake_search, fake_fetch, rounds=2, on_event=lambda k, d: events.append(k)
    ).run("¿Cuánto pesa y cuesta el plegable?")
    return report, events, model


def test_it_reads_pages_and_keeps_one_voice_per_site():
    report, events, _ = run()
    urls = [s.url for s in report.sources]
    assert "https://a.example/tercera" not in urls  # a third page of the same site
    assert all(s.read for s in report.sources)  # pages, not snippets
    assert events[0] == "plan" and events[-1] == "listo" and "lectura" in events


def test_an_invented_quote_is_thrown_away():
    report, _, _ = run()
    assert report.stats["descartadas"] >= 1
    assert not any("agua" in f.text for f in report.findings)


def test_two_sites_confirm_and_a_contradiction_is_marked():
    report, _, _ = run()
    by_text = {f.text: f for f in report.findings}
    assert by_text["Pesa 215 g"].status == "en disputa"  # the rumour contradicts it
    assert by_text["Pesa 215 g"].against
    assert by_text["Cuesta 1.999 dólares"].status == "una fuente"


def test_a_second_round_looks_for_what_was_missing():
    report, events, _ = run()
    assert events.count("ronda") == 2
    assert any(s.site == "d.example" for s in report.sources)


def test_the_report_never_cites_a_source_that_does_not_exist():
    report, _, _ = run()
    assert "[9]" not in report.text and "[5]" in report.text
    md = report.markdown()
    assert "## Fuentes" in md and "https://d.example/precio" in md


def test_without_sources_it_says_so_instead_of_inventing():
    report = DeepResearch(lambda p: "{}", lambda q, n: [], fake_fetch, rounds=1).run(
        "¿Algo?"
    )
    assert not report.findings and "No encontré" in report.text


def test_helpers():
    assert site_of("https://www.ejemplo.com/a") == "ejemplo.com"
    assert quote_in(
        "PESA 215 gramos, y su", "el telefono plegable pesa 215 gramos y su pantalla"
    )
    assert not quote_in("corto", "corto")  # too short to prove anything
    text = "### Título\nSource: https://x.example/a\nSummary: algo\n\n---\n\n### Otro\nSource: https://y.example\nSummary: más"
    assert [r["url"] for r in parse_results(text)] == [
        "https://x.example/a",
        "https://y.example",
    ]


def test_the_live_route_streams_the_steps_and_the_report(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from openjarvis.research import deep
    from openjarvis.server import deep_research_routes

    def fake_research(question, rounds=2, on_event=None):
        return DeepResearch(
            FakeModel(), fake_search, fake_fetch, rounds=rounds, on_event=on_event
        ).run(question)

    monkeypatch.setattr(deep, "research", fake_research)
    app = FastAPI()
    app.include_router(deep_research_routes.router)
    with TestClient(app).stream(
        "POST", "/v1/investigar", json={"pregunta": "¿Cuánto pesa?"}
    ) as r:
        body = "".join(r.iter_text())
    kinds = [line[7:] for line in body.splitlines() if line.startswith("event: ")]
    assert kinds[0] == "plan" and kinds[-1] == "informe" and "contraste" in kinds
    last = json.loads(body.strip().splitlines()[-1][6:])
    assert last["fuentes"] and "## Fuentes" in last["markdown"]


def test_the_tool_and_the_command_are_wired():
    from pathlib import Path

    from click.testing import CliRunner

    import openjarvis.tools as tools
    from openjarvis.cli.investigar_cmd import investigar
    from openjarvis.tools.deep_research_web import DeepResearchWebTool

    # Loaded with the other tools. (The registry is global state that other
    # tests reset, so this checks the wiring, not the registry's contents.)
    assert "openjarvis.tools.deep_research_web" in Path(tools.__file__).read_text()
    tool = DeepResearchWebTool()
    assert tool.spec.name == "investigacion_profunda"
    assert not tool.execute(question="").success
    out = CliRunner().invoke(investigar, ["--help"])
    assert out.exit_code == 0 and "--rondas" in out.output

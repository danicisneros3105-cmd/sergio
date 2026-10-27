"""``sergio cerebro`` — the fly core.

sergio cerebro descargar   # the measured connectome (FlyWire) and the meaning model
sergio cerebro dormir      # a night now: every brain consolidates what it learned
sergio cerebro prueba      # the measured proof that it learns
sergio cerebro estado      # what is plugged in
"""

from __future__ import annotations

import click
from rich.console import Console
from rich.markup import escape

console = Console()


@click.group("cerebro")
def cerebro() -> None:
    """El núcleo: el cerebro de la mosca que aprende."""


@cerebro.command("descargar")
def descargar() -> None:
    """Descarga y verifica el conectoma real y el modelo de significado."""
    from openjarvis.connectome.proof import download

    out = download(progress=lambda line: console.print(escape(line)))
    fw, mean = out["flywire"], out["significado"]
    if fw["ok"]:
        console.print(
            f"Conectoma real: {fw['kenyon']} células de Kenyon, {fw['salida']} de salida (huellas comprobadas)."
        )
    else:
        console.print(
            f"[yellow]Conectoma real: no se pudo ({escape(fw['error'])}). Sigue el sustituto.[/yellow]"
        )
    if mean["ok"]:
        console.print("Significado en este equipo: listo.")
    else:
        console.print(
            f"[yellow]Significado: no se pudo ({escape(mean['error'])}).[/yellow]"
        )


@cerebro.command("dormir")
def dormir() -> None:
    """Consolida ahora lo aprendido (la noche)."""
    from openjarvis.connectome.core import get_core

    core = get_core()
    report = core.sleep()
    if not report:
        console.print("Nada que consolidar todavía.")
    if core.human_night:
        console.print(
            f"Decisiones (mosca): {core.human_night['conceptos']} conceptos "
            f"({core.human_night['cambiados']} nuevos o cambiados), sinapsis podadas."
        )
    for name, r in report.items():
        console.print(
            f"{escape(name)}: {r['episodes']} episodios, acierto {r['accuracy_before']:.0%} → "
            f"{r['accuracy_after']:.0%}, {r['pruned']} sinapsis podadas"
        )


@cerebro.command("prueba")
def prueba() -> None:
    """La prueba medida de que aprende."""
    from openjarvis.connectome.proof import proof

    p = proof(fresh=True)
    w = p["wiring"]
    n = w["neuronas"]
    console.print(
        f"Cableado: {'REAL (FlyWire)' if w['real'] else 'sustituto'} · {n['kenyon']} Kenyon · "
        f"{n['salida']} de salida · {w['sinapsis_medidas']} sinapsis medidas · sentidos: {p['sentidos']}"
    )
    rounds = p["live"]["rondas"]
    console.print(
        "En vivo, frases nunca vistas: "
        + " → ".join(f"{r['acierto']:.0%}" for r in rounds)
        + f" (azar {p['live']['azar']:.0%}); sinapsis cambiadas {rounds[-1]['cambiadas']}, "
        f"nuevas {rounds[-1]['nuevas']}"
    )
    for kind, s in p["specialists"].items():
        last = s["curva"][-1]
        console.print(
            f"Especialista {kind}: acierta {last['top3']:.0%} en su top 3 (azar {last['chance_top3']:.0%})"
        )
    h = p["mosca"]
    console.print(
        "Cerebro de la mosca, pedidos nunca vistos: "
        + " → ".join(f"{r['acierto']:.0%}" for r in h["rondas"])
        + f" (azar {h['azar']:.0%}); dopamina +{h['dopamina']['recompensas']} "
        f"/ −{h['dopamina']['castigos']}; conceptos al dormir: {', '.join(h['conceptos']) or '—'}"
    )
    for key, moves in p["nodes"]["instintos"].items():
        console.print(
            f"{key}: «{escape(p['nodes']['pedido'])}» → {', '.join(m['movida'] for m in moves)}"
        )


@cerebro.command("estado")
def estado() -> None:
    """Qué cableado y qué sentidos están conectados."""
    from openjarvis.connectome.core import get_core

    info = get_core().info()
    console.print(escape(str(info.get("source"))))
    console.print(f"Sentidos: {escape(str(info.get('receptors')))}")
    console.print(
        f"Cerebros: {escape(', '.join(info.get('brains') or []) or 'ninguno')}"
    )


__all__ = ["cerebro"]

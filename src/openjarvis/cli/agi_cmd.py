"""``sergio agi`` — Universal AGI Command Line Nexus & Merkle Verification.

Enables the owner to dispatch extreme autonomous logistical missions,
inspect real-time cryptographic Merkle ledgers, and mathematically verify
RFC-6962 inclusion proofs directly from the terminal.
"""

from __future__ import annotations

import json
import time

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
def agi(ctx: click.Context) -> None:
    """Sergio AGI — Motor de razonamiento universal y auditoría criptográfica Merkle."""
    if ctx.invoked_subcommand is None:
        console.print(Panel(
            "[bold cyan]Sergio AGI Nexus — Copiloto Omnisciente[/bold cyan]\n\n"
            "[dim]Comandos operativos:[/dim]\n"
            "  • [green]sergio agi solve \"<misión>\"[/green]   Ejecutar resolución táctica AGI\n"
            "  • [green]sergio agi evidence[/green]            Inspeccionar libro mayor Merkle en vivo\n"
            "  • [green]sergio agi verify[/green]              Verificar pruebas matemáticas de inclusión O(log N)\n"
            "  • [green]sergio agi receipt <id>[/green]           Exportar recibo criptográfico de misión",
            title="[bold gold1]⚡ J.A.R.V.I.S. Core[/bold gold1]",
            border_style="cyan"
        ))


def _run_solve(mission_prompt: str, stealth: bool = True, require_confirm: bool = True) -> None:
    from openjarvis.core.agi_engine import get_universal_agi_engine

    console.print(f"[bold cyan]► Iniciando misión AGI:[/bold cyan] [italic]{mission_prompt}[/italic]")
    t0 = time.perf_counter()
    engine = get_universal_agi_engine()
    dossier = engine.solve(mission_prompt, stealth=stealth, require_confirmation=require_confirm)
    elapsed = round(time.perf_counter() - t0, 3)

    table = Table(title="Despliegue Táctico de Fases AGI", show_header=True, header_style="bold magenta")
    table.add_column("Fase", style="dim")
    table.add_column("Operación", style="cyan")
    table.add_column("Estado", style="green")
    table.add_column("Latencia", justify="right")

    for step in dossier.phases:
        table.add_row(
            step.phase.value if hasattr(step.phase, "value") else str(step.phase),
            step.name,
            f"[bold green]{step.status}[/bold green]",
            f"{step.latency_seconds * 1000:.1f} ms",
        )

    console.print(table)

    benefit = dossier.final_outcome.get("beneficio_clave", "Operación resuelta con éxito rotundo.")
    console.print()
    console.print(Panel(
        f"[bold white]{dossier.proactive_jarvis_brief}[/bold white]\n\n"
        f"[bold gold1]★ Beneficio Clave:[/bold gold1] {benefit}\n"
        f"[bold blue]🔒 Sello Criptográfico Vertu:[/bold blue] [dim]{dossier.vertu_seal_token[:32]}...[/dim]\n"
        f"[bold magenta]📁 Expediente Guardado:[/bold magenta] [dim]{dossier.dossier_path}[/dim]\n"
        f"[bold green]⏱ Tiempo Total:[/bold green] {elapsed:.3f} s",
        title=f"[bold green]✔ Misión Cumplida ({dossier.mission_id})[/bold green]",
        border_style="green"
    ))


@agi.command("solve")
@click.argument("mision", nargs=-1, required=True)
@click.option("--no-stealth", is_flag=True, default=False, help="Desactivar evasión antibot.")
@click.option("--skip-confirm", is_flag=True, default=False, help="Omitir confirmación Vertu.")
def solve_cmd(mision: tuple[str, ...], no_stealth: bool, skip_confirm: bool) -> None:
    """Ejecuta una misión logística o de negociación compleja de forma autónoma."""
    prompt = " ".join(mision).strip()
    _run_solve(prompt, stealth=not no_stealth, require_confirm=not skip_confirm)


@agi.command("evidence")
@click.option("--limit", default=10, help="Número de entradas recientes a mostrar.")
def evidence_cmd(limit: int) -> None:
    """Muestra el estado del libro mayor criptográfico Merkle y sus raíces."""
    from openjarvis.telemetry.evidence_nexus import get_evidence_nexus_ledger

    ledger = get_evidence_nexus_ledger()
    with ledger._lock:
        total = len(ledger.entries)
        integrity = ledger.verify_ledger_integrity()
        root = integrity.get("merkle_root", "N/A")

        table = Table(title=f"Libro Mayor de Evidencias Merkle ({total} entradas registradas)", show_header=True)
        table.add_column("ID", style="dim")
        table.add_column("Acción", style="cyan")
        table.add_column("Dominio", style="magenta")
        table.add_column("Latencia", justify="right")
        table.add_column("SHA-256 Hoja", style="dim")
        table.add_column("Estado", style="green")

        for e in ledger.entries[-limit:]:
            table.add_row(
                e.entry_id,
                e.action_name,
                e.domain,
                f"{e.latency_ms:.1f} ms",
                e.merkle_leaf_hash[:16] + "...",
                e.status,
            )

        valid_count = integrity.get("pruebas_inclusion_validadas", 0)
        console.print(table)
        console.print(Panel(
            f"[bold cyan]Raíz Merkle Actual (SHA-256):[/bold cyan] [bold green]{root}[/bold green]\n"
            f"[bold magenta]Estándar Criptográfico:[/bold magenta] RFC-6962 Domain Separated (0x00 / 0x01)\n"
            f"[bold white]Pruebas de Inclusión Validadas:[/bold white] {valid_count}/{total}",
            title="[bold gold1]🔒 Integridad Criptográfica del Ledger[/bold gold1]",
            border_style="cyan"
        ))


@agi.command("verify")
def verify_cmd() -> None:
    """Verifica matemáticamente todas las pruebas de inclusión Merkle O(log N)."""
    from openjarvis.telemetry.evidence_nexus import get_evidence_nexus_ledger

    console.print("[dim]Computando pruebas de inclusión Merkle contra la raíz inmutable...[/dim]")
    ledger = get_evidence_nexus_ledger()
    res = ledger.verify_ledger_integrity()

    if res.get("integridad_verificada"):
        valid_cnt = res["pruebas_inclusion_validadas"]
        total_cnt = res["total_hojas"]
        console.print(Panel(
            f"[bold green]✔ INTEGRIDAD MATEMÁTICA 100% CONFIRMADA[/bold green]\n\n"
            f"Raíz Merkle SHA-256: [bold cyan]{res['merkle_root']}[/bold cyan]\n"
            f"Hojas totales verificadas: [bold white]{total_cnt}[/bold white]\n"
            f"Inclusiones O(log N) conformes: [bold green]{valid_cnt}/{total_cnt}[/bold green]\n"
            f"Estándar: {res['estandar_criptografico']}",
            title="[bold green]Escudo Criptográfico Merkle[/bold green]",
            border_style="green"
        ))
    else:
        console.print(Panel(
            "[bold red]❌ FALLO EN LA VERIFICACIÓN CRIPTOGRÁFICA[/bold red]\n"
            "Se detectaron inconsistencias en las pruebas de inclusión de hojas.",
            title="[bold red]Alerta de Seguridad[/bold red]",
            border_style="red"
        ))


@agi.command("receipt")
@click.argument("mission_id", required=True)
def receipt_cmd(mission_id: str) -> None:
    """Exporta o muestra el recibo de auditoría con prueba de inclusión para una misión."""
    from openjarvis.telemetry.evidence_nexus import get_evidence_nexus_ledger

    ledger = get_evidence_nexus_ledger()
    receipt = ledger.generate_audit_receipt(mission_id)
    console.print_json(json.dumps(receipt, indent=2))


__all__ = ["agi"]

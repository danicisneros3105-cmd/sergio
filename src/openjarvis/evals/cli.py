"""CLI for the OpenJarvis evaluation framework."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

# cli_runs looks these up on this module, so they can be patched here.
from openjarvis.evals.core.display import (  # noqa: F401
    print_banner,
    print_completion,
    print_full_results,
    print_run_header,
    print_section,
    print_subject_table,
    print_suite_summary,
)

LOGGER = logging.getLogger(__name__)

# Registry of available benchmarks and their metadata
BENCHMARKS = {
    "supergpqa": {"category": "reasoning", "description": "SuperGPQA multiple-choice"},
    "gpqa": {"category": "reasoning", "description": "GPQA graduate-level MCQ"},
    "mmlu-pro": {"category": "reasoning", "description": "MMLU-Pro multiple-choice"},
    "math500": {"category": "reasoning", "description": "MATH-500 math problems"},
    "natural-reasoning": {"category": "reasoning", "description": "Natural Reasoning"},
    "hle": {"category": "reasoning", "description": "HLE hard challenges"},
    "simpleqa": {"category": "chat", "description": "SimpleQA factual QA"},
    "wildchat": {"category": "chat", "description": "WildChat conversation quality"},
    "ipw": {"category": "chat", "description": "IPW mixed benchmark"},
    "gaia": {"category": "agentic", "description": "GAIA agentic benchmark"},
    "frames": {"category": "rag", "description": "FRAMES multi-hop RAG"},
    "swebench": {"category": "agentic", "description": "SWE-bench code patches"},
    "swefficiency": {"category": "agentic", "description": "SWEfficiency optimization"},
    "terminalbench": {
        "category": "agentic",
        "description": "TerminalBench terminal tasks",
    },
    "terminalbench-native": {
        "category": "agentic",
        "description": "TerminalBench Native (Docker)",
    },
    "terminalbench-v2.1": {
        "category": "agentic",
        "description": "TerminalBench V2.1 (Harbor-style Docker tasks)",
    },
    "email_triage": {
        "category": "use-case",
        "description": "Email triage classification + draft",
    },
    "morning_brief": {
        "category": "use-case",
        "description": "Morning briefing generation",
    },
    "research_mining": {
        "category": "use-case",
        "description": "Research synthesis + accuracy",
    },
    "knowledge_base": {
        "category": "use-case",
        "description": "Document-grounded retrieval QA",
    },
    "coding_task": {
        "category": "use-case",
        "description": "Function-level code generation",
    },
    "loghub": {
        "category": "agentic",
        "description": "LogHub log anomaly detection",
    },
    "ama-bench": {
        "category": "agentic",
        "description": "AMA-Bench agent memory assessment",
    },
    "lifelong-agent": {
        "category": "agentic",
        "description": "LifelongAgentBench sequential task learning",
    },
    "deepplanning": {
        "category": "agentic",
        "description": "DeepPlanning shopping constraints",
    },
    "paperarena": {
        "category": "agentic",
        "description": "PaperArena paper analysis",
    },
    "webchorearena": {
        "category": "agentic",
        "description": "WebChoreArena web chore tasks",
    },
    "workarena": {
        "category": "agentic",
        "description": "WorkArena++ enterprise workflows",
    },
    "coding_assistant": {
        "category": "use-case",
        "description": "Bug-fix coding assistant (test-based)",
    },
    "security_scanner": {
        "category": "use-case",
        "description": "Security vulnerability scanner",
    },
    "daily_digest": {
        "category": "use-case",
        "description": "Daily briefing generation",
    },
    "doc_qa": {
        "category": "use-case",
        "description": "Document-grounded QA with citations",
    },
    "browser_assistant": {
        "category": "use-case",
        "description": "Web research with fact verification",
    },
    "pinchbench": {
        "category": "agentic",
        "description": "PinchBench real-world agent tasks",
    },
    "taubench": {
        "category": "agentic",
        "description": "TauBench multi-turn customer service",
    },
    "livecodebench": {
        "category": "coding",
        "description": "LiveCodeBench competitive programming",
    },
    "liveresearch": {
        "category": "agentic",
        "description": "DeepResearchBench report generation (alias: deepresearch)",
    },
    "deepresearch": {
        "category": "agentic",
        "description": "DeepResearchBench deep research report generation",
    },
    "liveresearchbench": {
        "category": "reasoning",
        "description": "LiveResearchBench recent research comprehension (Salesforce)",
    },
    "toolcall15": {
        "category": "agentic",
        "description": "ToolCall-15 tool calling benchmark",
    },
}

BACKENDS = {
    "jarvis-direct": "Engine-level inference (local or cloud)",
    "jarvis-agent": "Agent-level inference with tool calling",
    "hermes": "Real Hermes Agent (Nous Research) via subprocess",
    "openclaw": "Real OpenClaw via Node subprocess",
}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
def main():
    """OpenJarvis Evaluation Framework."""


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default=None,
    type=click.Path(),
    help="TOML config file for suite runs",
)
@click.option(
    "-b",
    "--benchmark",
    default=None,
    type=click.Choice(list(BENCHMARKS.keys())),
    help="Benchmark to run",
)
@click.option(
    "--backend",
    default="jarvis-direct",
    type=click.Choice(list(BACKENDS.keys())),
    help="Inference backend",
)
@click.option(
    "--base-url",
    default=None,
    help=(
        "OpenAI-compatible endpoint for the model under eval. Required for "
        "hermes/openclaw; for jarvis-direct/jarvis-agent/terminalbench-native "
        "it bypasses engine discovery and targets this URL directly "
        "(env: JARVIS_BACKEND_BASE_URL)."
    ),
)
@click.option(
    "--api-key",
    default=None,
    help=(
        "API key for the --base-url endpoint, sent as a Bearer token. "
        "Required for hermes/openclaw; optional for first-party backends "
        "(env: JARVIS_BACKEND_API_KEY)."
    ),
)
@click.option("-m", "--model", default=None, help="Model identifier")
@click.option(
    "-e",
    "--engine",
    "engine_key",
    default=None,
    help="Engine key (ollama, vllm, cloud, ...)",
)
@click.option(
    "--agent",
    "agent_name",
    default="orchestrator",
    help="Agent name for jarvis-agent backend",
)
@click.option("--tools", default="", help="Comma-separated tool names")
@click.option(
    "-n", "--max-samples", type=int, default=None, help="Maximum samples to evaluate"
)
@click.option("-w", "--max-workers", type=int, default=4, help="Parallel workers")
@click.option("--judge-model", default="gpt-5-mini-2025-08-07", help="LLM judge model")
@click.option("-o", "--output", "output_path", default=None, help="Output JSONL path")
@click.option("--seed", type=int, default=42, help="Random seed")
@click.option("--split", "dataset_split", default=None, help="Dataset split override")
@click.option("--temperature", type=float, default=0.0, help="Generation temperature")
@click.option("--max-tokens", type=int, default=2048, help="Max output tokens")
@click.option(
    "--telemetry/--no-telemetry",
    default=False,
    help="Enable telemetry collection during eval",
)
@click.option(
    "--gpu-metrics/--no-gpu-metrics",
    default=False,
    help="Enable GPU metrics collection",
)
@click.option(
    "--compact",
    is_flag=True,
    default=False,
    help="Dense single-table output",
)
@click.option(
    "--trace-detail",
    is_flag=True,
    default=False,
    help="Full per-step trace listing",
)
@click.option("--wandb-project", default="", help="W&B project name (enables tracking)")
@click.option("--wandb-entity", default="", help="W&B entity (team or user)")
@click.option("--wandb-tags", default="", help="Comma-separated W&B tags")
@click.option("--wandb-group", default="", help="W&B run group")
@click.option(
    "--sheets-id",
    "sheets_spreadsheet_id",
    default="",
    help="Google Sheets spreadsheet ID",
)
@click.option(
    "--sheets-worksheet", default="Results", help="Google Sheets worksheet name"
)
@click.option(
    "--sheets-creds",
    "sheets_credentials_path",
    default="",
    help="Service account JSON path",
)
@click.option(
    "--model-filter",
    default=None,
    help="Filter models by name substring (for multi-model configs)",
)
@click.option(
    "--judge-engine",
    default="cloud",
    help="Engine key for LLM judge (default: cloud). Use 'vllm' to judge locally.",
)
@click.option(
    "--agentic",
    is_flag=True,
    default=False,
    help="Use AgenticRunner for multi-turn agent execution",
)
@click.option(
    "--episode-mode",
    is_flag=True,
    default=False,
    help="Sequential episode processing with lifelong learning "
    "(required for lifelong-agent and similar benchmarks)",
)
@click.option(
    "--concurrency",
    type=int,
    default=1,
    help="Parallel query execution (AgenticRunner only)",
)
@click.option(
    "--query-timeout",
    type=float,
    default=None,
    help="Per-query wall-clock timeout in seconds (AgenticRunner only)",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
@click.pass_context
def run(
    ctx,
    config_path,
    benchmark,
    backend,
    base_url,
    api_key,
    model,
    engine_key,
    agent_name,
    tools,
    max_samples,
    max_workers,
    judge_model,
    output_path,
    seed,
    dataset_split,
    temperature,
    max_tokens,
    telemetry,
    gpu_metrics,
    compact,
    trace_detail,
    wandb_project,
    wandb_entity,
    wandb_tags,
    wandb_group,
    sheets_spreadsheet_id,
    sheets_worksheet,
    sheets_credentials_path,
    model_filter,
    judge_engine,
    agentic,
    episode_mode,
    concurrency,
    query_timeout,
    verbose,
):
    """Run a single benchmark evaluation, or a full suite from a TOML config."""
    _setup_logging(verbose)

    console = Console()

    # Config-driven mode
    if config_path is not None:
        _run_from_config(config_path, verbose, model_filter=model_filter)
        return

    # CLI-driven mode: validate required args
    if benchmark is None:
        raise click.UsageError(
            "Missing option '-b' / '--benchmark' "
            "(required when --config is not provided)"
        )
    if model is None:
        raise click.UsageError(
            "Missing option '-m' / '--model' (required when --config is not provided)"
        )

    from openjarvis.evals.core.types import RunConfig

    tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []

    # --episode-mode takes precedence over --agentic.
    # Note: EvalRunner also auto-detects episode_mode from the dataset
    # (via iter_episodes), so passing --episode-mode here is optional for
    # benchmarks like lifelong-agent that always require it.
    if episode_mode and agentic:
        LOGGER.warning(
            "--episode-mode and --agentic both set; using --episode-mode "
            "(provides proper multi-turn interaction via EvalRunner)"
        )
        agentic = False

    config = RunConfig(
        benchmark=benchmark,
        backend=backend,
        model=model,
        max_samples=max_samples,
        max_workers=max_workers,
        temperature=temperature,
        max_tokens=max_tokens,
        judge_model=judge_model,
        judge_engine=judge_engine,
        engine_key=engine_key,
        agent_name=agent_name,
        tools=tool_list,
        output_path=output_path,
        seed=seed,
        dataset_split=dataset_split,
        telemetry=telemetry,
        gpu_metrics=gpu_metrics,
        wandb_project=wandb_project,
        wandb_entity=wandb_entity,
        wandb_tags=wandb_tags,
        wandb_group=wandb_group,
        sheets_spreadsheet_id=sheets_spreadsheet_id,
        sheets_worksheet=sheets_worksheet,
        sheets_credentials_path=sheets_credentials_path,
        episode_mode=episode_mode,
        base_url=base_url or os.environ.get("JARVIS_BACKEND_BASE_URL"),
        api_key=api_key or os.environ.get("JARVIS_BACKEND_API_KEY"),
        metadata={
            "base_url": base_url or os.environ.get("JARVIS_BACKEND_BASE_URL"),
            "api_key": api_key or os.environ.get("JARVIS_BACKEND_API_KEY"),
        },
    )

    # Banner + config
    print_banner(console)
    print_section(console, "Configuration")
    print_run_header(
        console,
        benchmark=benchmark,
        model=model,
        backend=backend,
        samples=max_samples,
        workers=max_workers,
    )
    if episode_mode:
        console.print(
            "  [cyan]Mode:[/cyan]       episode (sequential + lifelong learning)"
        )

    if agentic:
        # --- Agentic runner path ---
        print_section(console, "Agentic Evaluation")
        console.print(f"  [cyan]Concurrency:[/cyan] {concurrency}")
        if query_timeout:
            console.print(f"  [cyan]Timeout:[/cyan]     {query_timeout}s per query")
        _run_agentic(
            config,
            console=console,
            concurrency=concurrency,
            query_timeout=query_timeout,
        )
        return

    # Evaluation
    print_section(console, "Evaluation")
    summary = _run_single(config, console=console)

    # Results
    _output_path = getattr(summary, "_output_path", None)
    _traces_dir = getattr(summary, "_traces_dir", None)
    _print_summary(
        summary,
        console=console,
        output_path=_output_path,
        traces_dir=_traces_dir,
        compact=compact,
        trace_detail=trace_detail,
    )


@main.command("run-all")
@click.option("-m", "--model", required=True, help="Model identifier")
@click.option("-e", "--engine", "engine_key", default=None, help="Engine key")
@click.option(
    "-n", "--max-samples", type=int, default=None, help="Max samples per benchmark"
)
@click.option("-w", "--max-workers", type=int, default=4, help="Parallel workers")
@click.option("--judge-model", default="gpt-5-mini-2025-08-07", help="LLM judge model")
@click.option("--output-dir", default="results/", help="Output directory for results")
@click.option("--seed", type=int, default=42, help="Random seed")
@click.option("-v", "--verbose", is_flag=True, help="Verbose logging")
def run_all(
    model, engine_key, max_samples, max_workers, judge_model, output_dir, seed, verbose
):
    """Run all benchmarks."""
    _setup_logging(verbose)

    from openjarvis.evals.core.runner import EvalRunner
    from openjarvis.evals.core.types import RunConfig

    console = Console()

    print_banner(console)
    print_section(console, "Suite Configuration")
    console.print(
        f"  [cyan]Model:[/cyan]      {model}\n"
        f"  [cyan]Benchmarks:[/cyan] {', '.join(BENCHMARKS.keys())}\n"
        f"  [cyan]Samples:[/cyan]    {max_samples if max_samples else 'all'}"
    )

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    model_slug = model.replace("/", "-").replace(":", "-")
    summaries = []

    for i, bench_name in enumerate(BENCHMARKS, 1):
        print_section(console, f"Run {i}/{len(BENCHMARKS)}: {bench_name}")
        output_path = output_dir_path / f"{bench_name}_{model_slug}.jsonl"

        config = RunConfig(
            benchmark=bench_name,
            backend="jarvis-direct",
            model=model,
            max_samples=max_samples,
            max_workers=max_workers,
            judge_model=judge_model,
            engine_key=engine_key,
            output_path=str(output_path),
            seed=seed,
        )

        eval_backend = _build_backend("jarvis-direct", engine_key, "orchestrator", [])
        dataset = _build_dataset(bench_name)
        judge_backend = _build_judge_backend(judge_model, engine_key="cloud")
        scorer = _build_scorer(bench_name, judge_backend, judge_model)

        trackers = _build_trackers(config)
        runner = EvalRunner(config, dataset, eval_backend, scorer, trackers=trackers)
        try:
            if max_samples and max_samples > 0:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(
                        f"Evaluating {bench_name}...",
                        total=max_samples,
                    )
                    summary = runner.run(
                        progress_callback=lambda done, total: progress.update(
                            task,
                            completed=done,
                        ),
                    )
            else:
                with console.status(f"Evaluating {bench_name}..."):
                    summary = runner.run()
            summaries.append(summary)
            console.print(
                f"  [green]{summary.accuracy:.4f}[/green] "
                f"({summary.correct}/{summary.scored_samples})"
            )
        except Exception as exc:
            console.print(f"  [red bold]FAILED:[/red bold] {exc}")
        finally:
            eval_backend.close()
            if judge_backend is not None:
                judge_backend.close()

    # Print overall summary
    if summaries:
        print_section(console, "Suite Results")
        print_suite_summary(console, summaries, f"All Benchmarks / {model}")


@main.command()
@click.argument("jsonl_path", type=click.Path(exists=True))
def summarize(jsonl_path):
    """Summarize results from a JSONL output file."""
    records = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        click.echo("No records found.")
        return

    console = Console()
    total = len(records)
    scored = [r for r in records if r.get("is_correct") is not None]
    correct = [r for r in scored if r["is_correct"]]
    errors = [r for r in records if r.get("error")]
    accuracy = len(correct) / len(scored) if scored else 0.0

    console.print(f"[cyan]File:[/cyan]      {jsonl_path}")
    console.print(f"[cyan]Benchmark:[/cyan] {records[0].get('benchmark', '?')}")
    console.print(f"[cyan]Model:[/cyan]     {records[0].get('model', '?')}")
    console.print(f"[cyan]Total:[/cyan]     {total}")
    console.print(f"[cyan]Scored:[/cyan]    {len(scored)}")
    console.print(f"[cyan]Correct:[/cyan]   {len(correct)}")
    console.print(f"[cyan]Accuracy:[/cyan]  [bold]{accuracy:.4f}[/bold]")
    console.print(f"[cyan]Errors:[/cyan]    {len(errors)}")


@main.command("reparse-judge")
@click.option(
    "--jsonl",
    "jsonl_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to a results JSONL produced by an LLM-judge benchmark.",
)
@click.option(
    "--out",
    "out_path",
    default=None,
    type=click.Path(),
    help=(
        "Output JSONL path. Defaults to <jsonl>.reparsed when --in-place is not set."
    ),
)
@click.option(
    "--in-place",
    is_flag=True,
    default=False,
    help="Overwrite the input JSONL (creates <jsonl>.bak first).",
)
@click.option(
    "--summary-out",
    default=None,
    type=click.Path(),
    help="Output summary JSON path. Defaults to <out>.summary.json.",
)
def reparse_judge(jsonl_path, out_path, in_place, summary_out):
    """Re-parse stored judge output and recover records that failed.

    Reads each record raw_judge_output, runs it through the (fixed) parser,
    and updates records whose old score was 0/None when a new score is
    recoverable. Writes a summary.json with the recomputed accuracy + the
    continuous-score fields, and prints a diff.
    """
    import json as _json
    import shutil
    import statistics
    from pathlib import Path as _Path

    from openjarvis.evals.scorers.liveresearch import rescore_from_metadata

    in_path = _Path(jsonl_path)
    if in_place:
        backup = in_path.with_suffix(in_path.suffix + ".bak")
        if not backup.exists():
            shutil.copy2(in_path, backup)
        target = in_path
    else:
        if out_path is None:
            target = in_path.with_suffix(in_path.suffix + ".reparsed")
        else:
            target = _Path(out_path)

    records = []
    with open(in_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(_json.loads(line))

    n_rescored = 0
    old_scores = []
    new_scores = []
    for rec in records:
        sm = rec.get("scoring_metadata") or {}
        old_score = rec.get("score")
        old_scores.append(old_score)
        attempt = old_score is None or (
            isinstance(old_score, (int, float)) and float(old_score) <= 0.0
        )
        new_score = old_score
        if attempt:
            res = rescore_from_metadata(sm)
            if res is not None:
                new_correct, new_meta = res
                if new_meta.get("score", 0.0) > 0:
                    rec["scoring_metadata"] = new_meta
                    rec["is_correct"] = bool(new_correct)
                    rec["score"] = float(new_meta["score"])
                    new_score = rec["score"]
                    n_rescored += 1
        new_scores.append(new_score)

    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w") as f:
        for rec in records:
            f.write(_json.dumps(rec, default=str) + chr(10))

    cont = [float(s) for s in new_scores if s is not None]
    scored = [r for r in records if r.get("is_correct") is not None]
    correct = [r for r in scored if r.get("is_correct")]
    accuracy = len(correct) / len(scored) if scored else 0.0
    summary = {
        "benchmark": records[0].get("benchmark", "?") if records else "?",
        "model": records[0].get("model", "?") if records else "?",
        "total_samples": len(records),
        "scored_samples": len(scored),
        "correct": len(correct),
        "accuracy": round(accuracy, 4),
        "mean_continuous_score": (round(sum(cont) / len(cont), 6) if cont else None),
        "median_continuous_score": (
            round(statistics.median(cont), 6) if cont else None
        ),
        "pct_above_0.5": (
            round(sum(1 for v in cont if v > 0.5) / len(cont), 6) if cont else None
        ),
        "pct_above_0.7": (
            round(sum(1 for v in cont if v > 0.7) / len(cont), 6) if cont else None
        ),
        "pct_above_0.8": (
            round(sum(1 for v in cont if v > 0.8) / len(cont), 6) if cont else None
        ),
        "pct_above_0.9": (
            round(sum(1 for v in cont if v > 0.9) / len(cont), 6) if cont else None
        ),
        "reparse_records_recovered": n_rescored,
    }
    if summary_out is None:
        summary_path = target.with_suffix(target.suffix + ".summary.json")
    else:
        summary_path = _Path(summary_out)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        _json.dump(summary, f, indent=2)

    old_cont = [float(s) for s in old_scores if s is not None]
    old_acc = sum(1 for s in old_cont if s >= 0.5) / len(old_cont) if old_cont else 0.0
    old_mean = sum(old_cont) / len(old_cont) if old_cont else 0.0
    new_mean = sum(cont) / len(cont) if cont else 0.0
    mean_shift = new_mean - old_mean
    acc_shift = accuracy - old_acc

    console = Console()
    console.print(f"[cyan]Input:[/cyan]    {in_path}")
    console.print(f"[cyan]Output:[/cyan]   {target}")
    console.print(f"[cyan]Summary:[/cyan]  {summary_path}")
    console.print(
        f"[bold green]{n_rescored}[/bold green] records re-scored, "
        f"mean shift {mean_shift:+.4f}, accuracy shift {acc_shift:+.2%}"
    )


@main.command("list")
def list_cmd():
    """List available benchmarks and backends."""
    console = Console()
    print_banner(console)

    from rich.table import Table

    bench_table = Table(
        title="[bold]Available Benchmarks[/bold]",
        border_style="bright_blue",
        title_style="bold cyan",
    )
    bench_table.add_column("Name", style="cyan", no_wrap=True)
    bench_table.add_column("Category", style="white")
    bench_table.add_column("Description")
    for name, info in BENCHMARKS.items():
        bench_table.add_row(name, info["category"], info["description"])
    console.print(bench_table)

    backend_table = Table(
        title="[bold]Available Backends[/bold]",
        border_style="bright_blue",
        title_style="bold cyan",
    )
    backend_table.add_column("Name", style="cyan", no_wrap=True)
    backend_table.add_column("Description")
    for name, desc in BACKENDS.items():
        backend_table.add_row(name, desc)
    console.print(backend_table)


if __name__ == "__main__":
    main()


# Moved to their own module; they look their helpers up here.
from openjarvis.evals.cli_builders import _build_backend as _build_backend  # noqa: E402,I001
from openjarvis.evals.cli_builders import _build_dataset as _build_dataset  # noqa: E402,I001
from openjarvis.evals.cli_builders import _build_judge_backend as _build_judge_backend  # noqa: E402,I001
from openjarvis.evals.cli_builders import _build_scorer as _build_scorer  # noqa: E402,I001

# Moved to their own module (it looks its helpers up here).
from openjarvis.evals import cli_runs as _cli_runs  # noqa: E402,I001

_print_summary = _cli_runs._print_summary
_build_trackers = _cli_runs._build_trackers
_run_terminalbench_native = _cli_runs._run_terminalbench_native
_run_single = _cli_runs._run_single
_run_agentic = _cli_runs._run_agentic
_nullctx = _cli_runs._nullctx
_print_agentic_summary = _cli_runs._print_agentic_summary
_run_from_config = _cli_runs._run_from_config


__all__ = [
    "BACKENDS",
    "BENCHMARKS",
    "list_cmd",
    "LOGGER",
    "main",
    "reparse_judge",
    "run",
    "run_all",
    "summarize",
]

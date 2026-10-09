"""How ``jarvis eval`` runs a benchmark: single-turn runs, agentic
(episode/interactive) runs, the native Terminal-Bench path, runs from a TOML
suite, result trackers and the printed summaries.

Split out of ``cli.py``; its names are looked up on that module at call
time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console

import openjarvis.evals.cli as _cli


def _print_summary(
    summary,
    console: Optional[Console] = None,
    output_path: Optional[Path] = None,
    traces_dir: Optional[Path] = None,
    *,
    compact: bool = False,
    trace_detail: bool = False,
) -> None:
    """Print a single run summary using Rich display primitives."""
    if console is None:
        console = _cli.Console()
    _cli.print_section(console, "Results")
    _cli.print_full_results(
        console, summary, compact=compact, trace_detail=trace_detail
    )
    if not compact and summary.per_subject and len(summary.per_subject) > 1:
        _cli.print_subject_table(console, summary.per_subject)
    _cli.print_completion(console, summary, output_path, traces_dir)


def _build_trackers(config) -> list:
    """Build tracker instances from RunConfig fields."""
    trackers = []
    if getattr(config, "wandb_project", ""):
        try:
            from openjarvis.evals.trackers.wandb_tracker import WandbTracker

            trackers.append(
                WandbTracker(
                    project=config.wandb_project,
                    entity=getattr(config, "wandb_entity", ""),
                    tags=getattr(config, "wandb_tags", ""),
                    group=getattr(config, "wandb_group", ""),
                )
            )
        except ImportError as exc:
            raise _cli.click.ClickException(
                f"wandb not installed: {exc}\nInstall with: uv sync --extra eval-wandb"
            ) from exc
    if getattr(config, "sheets_spreadsheet_id", ""):
        try:
            from openjarvis.evals.trackers.sheets_tracker import SheetsTracker

            trackers.append(
                SheetsTracker(
                    spreadsheet_id=config.sheets_spreadsheet_id,
                    worksheet=getattr(config, "sheets_worksheet", "Results"),
                    credentials_path=getattr(config, "sheets_credentials_path", ""),
                )
            )
        except ImportError as exc:
            raise _cli.click.ClickException(
                f"gspread not installed: {exc}\n"
                "Install with: uv sync --extra eval-sheets"
            ) from exc
    return trackers


def _run_terminalbench_native(
    config,
    console: Console,
    *,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> object:
    """Run TerminalBench V2.1 natively via terminal-bench Harness.

    ``base_url`` (from ``--base-url`` / JARVIS_BACKEND_BASE_URL) targets an
    already-running OpenAI-compatible endpoint; when unset, the legacy local
    vLLM default (http://localhost:8000/v1) is used.
    """
    from openjarvis.engine.openai_compat_engines import normalize_openai_base_url
    from openjarvis.evals.backends.terminalbench_native import (
        TerminalBenchNativeBackend,
        summarize_benchmark_results,
    )

    model = config.model
    # LiteLLM expects "openai/<model>" for OpenAI-compatible servers
    litellm_model = f"openai/{model}"
    output_dir = getattr(config, "output_path", None) or "results/terminalbench-native/"

    # Harness budgets: only forward explicit config values so the backend
    # defaults (global_agent_timeout_sec=1800) apply otherwise.
    timeout_kwargs = {}
    if getattr(config, "global_agent_timeout_sec", None) is not None:
        timeout_kwargs["global_agent_timeout_sec"] = config.global_agent_timeout_sec
    if getattr(config, "global_timeout_multiplier", None) is not None:
        timeout_kwargs["global_timeout_multiplier"] = config.global_timeout_multiplier

    # Normalize to exactly one trailing "/v1" — LiteLLM's api_base wants the
    # full OpenAI-compatible prefix, and users pass both forms of the URL.
    if base_url:
        api_base = normalize_openai_base_url(base_url) + "/v1"
    else:
        api_base = "http://localhost:8000/v1"

    backend = TerminalBenchNativeBackend(
        model=litellm_model,
        api_base=api_base,
        temperature=config.temperature,
        max_samples=config.max_samples,
        output_dir=output_dir,
        n_concurrent=config.max_workers or 4,
        **timeout_kwargs,
    )

    import re

    # Docker compose project names must be lowercase alphanumeric + hyphens/underscores
    model_slug = re.sub(r"[^a-z0-9_-]", "-", model.lower().replace("/", "-"))
    run_id = f"tb21-{model_slug}"
    console.print(f"  Running TerminalBench V2.1 natively: {model}")
    console.print(f"  API base: {api_base}")
    console.print(f"  Harness run_id: {run_id}")

    if api_key:
        # terminus-2 routes model calls through LiteLLM with the "openai/"
        # prefix, which reads OPENAI_API_KEY from the environment. The
        # harness runs in-process, so set the var for the duration of the
        # run and restore the previous value afterwards.
        prev_key = _cli.os.environ.get("OPENAI_API_KEY")
        _cli.os.environ["OPENAI_API_KEY"] = api_key
        try:
            results = backend.run_harness(run_id)
        finally:
            if prev_key is None:
                _cli.os.environ.pop("OPENAI_API_KEY", None)
            else:
                _cli.os.environ["OPENAI_API_KEY"] = prev_key
    else:
        results = backend.run_harness(run_id)

    # Convert BenchmarkResults to RunSummary, classifying harness/infra
    # failures (e.g. zero-model-contact setup hangs) out of the resolve-rate.
    summary, harness_failures = summarize_benchmark_results(results, model=model)
    if harness_failures:
        console.print(
            f"  [red bold]{len(harness_failures)} harness/infra failure(s) "
            "excluded from resolve-rate:[/red bold]"
        )
        for failure in harness_failures:
            console.print(
                f"  [red]- {failure['task_id']}: {failure['reason']} "
                f"(failure_mode={failure['failure_mode']})[/red]"
            )
    return summary


def _run_single(
    config,
    console: Optional[Console] = None,
    *,
    suite_mode: bool = False,
) -> object:
    """Run a single eval from a RunConfig and return the summary.

    ``suite_mode=True`` (TOML-suite drivers) scopes ``config.base_url`` /
    ``config.api_key`` — stamped from the suite's ``[backend.external]``
    section onto every RunConfig — to the hermes/openclaw backends only;
    extending suite-level endpoint targeting to first-party backends is
    explicitly deferred. The CLI single-run path (``suite_mode=False``)
    honors ``--base-url``/``--api-key`` for every backend.
    """
    from openjarvis.evals.core.runner import EvalRunner

    if console is None:
        console = _cli.Console()

    _metadata = getattr(config, "metadata", None) or {}
    base_url = (
        getattr(config, "base_url", None)
        or _metadata.get("base_url")
        or _cli.os.environ.get("JARVIS_BACKEND_BASE_URL")
    )
    api_key = (
        getattr(config, "api_key", None)
        or _metadata.get("api_key")
        or _cli.os.environ.get("JARVIS_BACKEND_API_KEY")
    )

    # TerminalBench V2.1 native: use terminal-bench Harness directly
    if config.benchmark == "terminalbench-native":
        return _cli._run_terminalbench_native(
            config,
            console,
            base_url=None if suite_mode else base_url,
            api_key=None if suite_mode else api_key,
        )

    eval_backend = _cli._build_backend(
        config.backend,
        config.engine_key,
        config.agent_name or "orchestrator",
        config.tools,
        telemetry=getattr(config, "telemetry", False),
        gpu_metrics=getattr(config, "gpu_metrics", False),
        model=config.model,
        max_turns=getattr(config, "max_turns", None),
        base_url=base_url,
        api_key=api_key,
        first_party_endpoint=not suite_mode,
    )
    dataset = _cli._build_dataset(config.benchmark)
    # Inject engine config for benchmarks that run their own simulation
    if hasattr(dataset, "set_engine_config"):
        dataset.set_engine_config(
            engine_key=config.engine_key,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            telemetry=getattr(config, "telemetry", False),
            gpu_metrics=getattr(config, "gpu_metrics", False),
        )
    judge_engine = getattr(config, "judge_engine", "cloud") or "cloud"
    judge_backend = _cli._build_judge_backend(
        config.judge_model, engine_key=judge_engine
    )
    scorer = _cli._build_scorer(config.benchmark, judge_backend, config.judge_model)

    trackers = _cli._build_trackers(config)
    runner = EvalRunner(config, dataset, eval_backend, scorer, trackers=trackers)
    try:
        num_samples = config.max_samples or 0
        # Use progress bar if we know the sample count
        if num_samples > 0:
            with _cli.Progress(
                _cli.SpinnerColumn(),
                _cli.TextColumn("[progress.description]{task.description}"),
                _cli.BarColumn(),
                _cli.TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                _cli.TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Evaluating samples...", total=num_samples)
                summary = runner.run(
                    progress_callback=lambda done, total: progress.update(
                        task,
                        completed=done,
                    ),
                )
        else:
            with console.status("Evaluating samples..."):
                summary = runner.run()
        return summary
    finally:
        eval_backend.close()
        if judge_backend is not None:
            judge_backend.close()


def _run_agentic(
    config,
    console: Optional[Console] = None,
    *,
    concurrency: int = 1,
    query_timeout: Optional[float] = None,
) -> None:
    """Run an agentic evaluation using AgenticRunner with trace + energy capture."""
    import asyncio
    from pathlib import Path as _Path

    from openjarvis.evals.core.agentic_runner import AgenticRunner
    from openjarvis.evals.core.event_recorder import EventRecorder
    from openjarvis.evals.core.export import (
        export_artifacts_manifest,
        export_jsonl,
        export_summary_json,
    )

    if console is None:
        console = _cli.Console()

    # Build dataset
    dataset = _cli._build_dataset(
        config.benchmark, getattr(config, "dataset_subset", None)
    )
    dataset.load(
        max_samples=config.max_samples,
        split=config.dataset_split,
        seed=config.seed,
    )

    # Wire judge for PinchBench LLM-judge and hybrid grading
    if config.benchmark == "pinchbench" and hasattr(dataset, "set_judge"):
        judge_engine = getattr(config, "judge_engine", "cloud") or "cloud"
        judge_model = (
            getattr(config, "judge_model", None) or "anthropic/claude-opus-4-5"
        )
        judge_backend = _cli._build_judge_backend(judge_model, engine_key=judge_engine)
        dataset.set_judge(judge_backend, judge_model)

    # Verify backend requirements before doing any work
    if hasattr(dataset, "verify_requirements"):
        issues = dataset.verify_requirements()
        if issues:
            console.print(
                "\n[bold red]Cannot start evaluation — requirements not met:[/bold red]"
            )
            for issue in issues:
                console.print(f"[red]  • {issue}[/red]")
            raise _cli.click.ClickException(
                f"{config.benchmark} requirements not satisfied. "
                "Fix the issues above and retry."
            )

    # Build agent via SystemBuilder
    from openjarvis.system import SystemBuilder

    builder = SystemBuilder()
    if config.engine_key:
        builder.engine(config.engine_key)
    builder.model(config.model)
    agent_name = config.agent_name or "orchestrator"
    builder.agent(agent_name)
    tool_list = config.tools or []
    if tool_list:
        builder.tools(tool_list)
    system = builder.telemetry(config.telemetry).traces(config.telemetry).build()

    # Build TelemetrySession (optional — only if energy monitoring available)
    telemetry_session = None
    try:
        from openjarvis.core.config import load_config
        from openjarvis.telemetry.energy_monitor import create_energy_monitor
        from openjarvis.telemetry.session import TelemetrySession

        # The eval config carries only a telemetry on/off flag, so the
        # estimate opt-in has to come from the user's JarvisConfig.
        allow_estimates = load_config().telemetry.allow_energy_estimates
        monitor = create_energy_monitor(allow_estimates=allow_estimates)
        if monitor is not None:
            telemetry_session = TelemetrySession(
                monitor=monitor,
                interval_ms=100,
            )
    except ImportError:
        pass

    # Set up run directory
    model_slug = config.model.replace("/", "-").replace(":", "-")
    if config.output_path:
        run_dir = _Path(config.output_path).parent
    else:
        run_dir = _Path("results")
    run_dir = run_dir / f"agentic_{config.benchmark}_{model_slug}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Build runner
    event_recorder = EventRecorder()
    runner = AgenticRunner(
        agent=system,
        dataset=dataset,
        telemetry_session=telemetry_session,
        config={
            "model": config.model,
            "benchmark": config.benchmark,
            "agent": agent_name,
            "tools": tool_list,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        },
        event_recorder=event_recorder,
        run_dir=run_dir,
        concurrency=concurrency,
        query_timeout=query_timeout,
    )

    # Execute with telemetry session context
    try:
        ctx = telemetry_session if telemetry_session is not None else _cli._nullctx()
        with ctx:
            with console.status("Running agentic evaluation..."):
                traces = asyncio.run(runner.run(max_queries=config.max_samples))
    finally:
        system.close()
        if telemetry_session is not None and hasattr(telemetry_session, "stop"):
            try:
                telemetry_session.stop()
            except Exception:
                pass

    # Export results
    jsonl_path = run_dir / "traces.jsonl"
    export_jsonl(traces, jsonl_path)
    console.print(f"  [green]Traces:[/green]    {jsonl_path}")

    summary_path = run_dir / "summary.json"
    export_summary_json(
        traces,
        config={
            "model": config.model,
            "benchmark": config.benchmark,
            "agent": agent_name,
            "concurrency": concurrency,
            "query_timeout": query_timeout,
        },
        path=summary_path,
    )
    console.print(f"  [green]Summary:[/green]   {summary_path}")

    manifest = export_artifacts_manifest(run_dir)
    if manifest:
        console.print(f"  [green]Manifest:[/green]  {manifest}")

    # Try HF dataset export (optional)
    try:
        from openjarvis.evals.core.export import export_hf_dataset

        hf_path = run_dir / "hf_dataset"
        export_hf_dataset(traces, hf_path)
        console.print(f"  [green]HF Arrow:[/green]  {hf_path}")
    except ImportError:
        pass

    # Print summary table
    _cli.print_section(console, "Agentic Results")
    _cli._print_agentic_summary(console, traces, config)


def _nullctx():
    """Return a no-op context manager."""
    from contextlib import nullcontext

    return nullcontext()


def _print_agentic_summary(console: Console, traces, config) -> None:
    """Print a rich summary of agentic run results."""
    from rich.table import Table

    completed = sum(1 for t in traces if t.completed)
    harness_errors = [t for t in traces if t.error_kind == "harness_error"]
    model_traces = [t for t in traces if t.error_kind != "harness_error"]
    resolved = sum(1 for t in model_traces if t.is_resolved is True)
    timed_out = sum(1 for t in traces if t.timed_out)
    total_turns = sum(t.num_turns for t in traces)
    total_tool_calls = sum(t.total_tool_calls for t in traces)
    total_in_tok = sum(t.total_input_tokens for t in traces)
    total_out_tok = sum(t.total_output_tokens for t in traces)
    total_wall = sum(t.total_wall_clock_s for t in traces)

    gpu_energies = [
        t.total_gpu_energy_joules
        for t in traces
        if t.total_gpu_energy_joules is not None
    ]
    total_gpu_energy = sum(gpu_energies) if gpu_energies else None

    costs = [t.total_cost_usd for t in traces if t.total_cost_usd is not None]
    total_cost = sum(costs) if costs else None

    table = Table(
        title=f"[bold]{config.benchmark} / {config.model}[/bold]",
        border_style="bright_blue",
    )
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Queries", str(len(traces)))
    table.add_row("Completed", f"{completed}/{len(traces)}")
    if any(t.is_resolved is not None for t in traces):
        # Harness errors are excluded from the resolve-rate denominator:
        # they are infra failures, not model misses.
        table.add_row("Resolved", f"{resolved}/{len(model_traces)}")
    table.add_row("Timed out", str(timed_out))
    table.add_row("Harness errors", str(len(harness_errors)))
    table.add_row("Total turns", str(total_turns))
    avg_t = f"{total_turns / len(traces):.1f}" if traces else "0"
    table.add_row("Avg turns/query", avg_t)
    table.add_row("Total tool calls", str(total_tool_calls))
    table.add_row("Input tokens", f"{total_in_tok:,}")
    table.add_row("Output tokens", f"{total_out_tok:,}")
    table.add_row("Wall clock", f"{total_wall:.1f}s")
    table.add_row(
        "Avg query time",
        f"{total_wall / len(traces):.1f}s" if traces else "0s",
    )

    if total_gpu_energy is not None:
        table.add_row("GPU energy", f"{total_gpu_energy:.2f} J")
    if total_cost is not None:
        table.add_row("Total cost", f"${total_cost:.4f}")

    # Throughput
    if total_out_tok > 0 and total_wall > 0:
        table.add_row(
            "Throughput",
            f"{total_out_tok / total_wall:.1f} tok/s",
        )

    console.print(table)

    if harness_errors:
        console.print(
            f"[red bold]{len(harness_errors)} harness/infra failure(s) "
            "excluded from resolve-rate:[/red bold]"
        )
        for t in harness_errors[:5]:
            console.print(f"[red]  {t.query_id}: {(t.error or '')[:300]}[/red]")
        if len(harness_errors) > 5:
            console.print(
                f"[red]  ... and {len(harness_errors) - 5} more "
                "(see traces.jsonl)[/red]"
            )


def _run_from_config(
    config_path: str,
    verbose: bool,
    *,
    model_filter: str | None = None,
) -> None:
    """Load a TOML config and run the full models x benchmarks matrix."""
    from openjarvis.evals.core.config import expand_suite, load_eval_config

    console = _cli.Console()

    suite = load_eval_config(config_path)
    run_configs = expand_suite(suite)

    # Filter by model name substring if requested
    if model_filter:
        run_configs = [rc for rc in run_configs if model_filter in rc.model]
        if not run_configs:
            raise _cli.click.ClickException(f"No models match filter '{model_filter}'")

    suite_name = suite.meta.name or _cli.Path(config_path).stem

    # Banner + configuration
    _cli.print_banner(console)
    _cli.print_section(console, "Suite Configuration")
    console.print(f"  [cyan]Suite:[/cyan]       {suite_name}")
    if suite.meta.description:
        console.print(f"  [cyan]Description:[/cyan] {suite.meta.description}")
    console.print(
        f"  [cyan]Matrix:[/cyan]     {len(suite.models)} model(s) x "
        f"{len(suite.benchmarks)} benchmark(s) = {len(run_configs)} run(s)"
    )

    # Ensure output directory exists
    output_dir = _cli.Path(suite.run.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Auto-set wandb_group to suite name if W&B enabled and no explicit group
    for rc in run_configs:
        if rc.wandb_project and not rc.wandb_group:
            rc.wandb_group = suite_name

    summaries = []
    for i, rc in enumerate(run_configs, 1):
        _cli.print_section(
            console,
            f"Run {i}/{len(run_configs)}: {rc.benchmark} / {rc.model}",
        )
        try:
            summary = _cli._run_single(rc, console=console, suite_mode=True)
            summaries.append(summary)
            console.print(
                f"  [green]{summary.accuracy:.4f}[/green] "
                f"({summary.correct}/{summary.scored_samples})"
            )
        except Exception as exc:
            console.print(f"  [red bold]FAILED:[/red bold] {exc}")

    # Print overall summary table
    if summaries:
        _cli.print_section(console, "Suite Results")
        _cli.print_suite_summary(console, summaries, suite_name)


__all__ = [
    "_print_summary",
    "_build_trackers",
    "_run_terminalbench_native",
    "_run_single",
    "_run_agentic",
    "_nullctx",
    "_print_agentic_summary",
    "_run_from_config",
]

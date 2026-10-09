"""Statistics helpers for eval runs: normalised per-metric stats,
percentiles, and the dict forms of a summary and of a result trace.

Split out of ``runner.py``; its names are looked up on that module at call
time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import openjarvis.evals.core.runner as _runner
from openjarvis.evals.core.types import EvalResult, MetricStats, RunSummary


def _compute_normalized_stats(
    results: List[EvalResult],
    accuracy: float,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Compute stats after trimming top/bottom 5% outliers by latency.

    Returns (normalized_statistics, normalized_efficiency) or (None, None)
    if fewer than 4 results.
    """
    n = len(results)
    if n < 4:
        return None, None

    trim_count = max(1, _runner.math.floor(n * 0.05))
    sorted_results = sorted(results, key=lambda r: r.latency_seconds)
    trimmed = sorted_results[trim_count : n - trim_count]

    if not trimmed:
        return None, None

    # Recompute key metric stats on trimmed set
    t_scored = [r for r in trimmed if r.is_correct is not None]
    t_correct = [r for r in t_scored if r.is_correct]
    t_accuracy = len(t_correct) / len(t_scored) if t_scored else 0.0
    t_latency_vals = [r.latency_seconds for r in trimmed if r.latency_seconds > 0]
    t_energy_vals = [r.energy_joules for r in trimmed if r.energy_joules > 0]
    t_power_vals = [r.power_watts for r in trimmed if r.power_watts > 0]
    t_throughput_vals = [
        r.throughput_tok_per_sec for r in trimmed if r.throughput_tok_per_sec > 0
    ]
    t_mbu_vals = [r.mbu_pct for r in trimmed if r.mbu_pct > 0]

    norm_stats: Dict[str, Any] = {
        "_description": (
            f"Statistics recomputed after trimming {trim_count} outlier(s) "
            f"from each end by latency ({len(trimmed)}/{n} results kept)"
        ),
        "_outliers_removed": trim_count * 2,
        "accuracy": round(t_accuracy, 4),
        "latency_stats": _runner._metric_stats_to_dict(
            _runner._metric_stats(t_latency_vals)
        ),
        "energy_stats": _runner._metric_stats_to_dict(
            _runner._metric_stats(t_energy_vals)
        ),
        "power_stats": _runner._metric_stats_to_dict(
            _runner._metric_stats(t_power_vals)
        ),
        "throughput_stats": _runner._metric_stats_to_dict(
            _runner._metric_stats(t_throughput_vals),
        ),
        "mbu_stats": _runner._metric_stats_to_dict(_runner._metric_stats(t_mbu_vals)),
    }

    t_total_energy = sum(r.energy_joules for r in trimmed)
    t_avg_power = _runner.statistics.mean(t_power_vals) if t_power_vals else 0.0
    norm_eff: Dict[str, Any] = {
        "accuracy": round(t_accuracy, 4),
        "total_energy_joules": round(t_total_energy, 6),
        "avg_power_watts": round(t_avg_power, 4),
        "ipj": (round(t_accuracy / t_total_energy, 6) if t_total_energy > 0 else None),
        "ipw": (round(t_accuracy / t_avg_power, 6) if t_avg_power > 0 else None),
    }

    return norm_stats, norm_eff


def _eval_percentile(data: list[float], p: float) -> float:
    """Compute the p-th percentile using linear interpolation."""
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def _metric_stats(values: List[float]) -> Optional[MetricStats]:
    """Compute MetricStats from a list of float values."""
    if not values:
        return None
    return _runner.MetricStats(
        mean=_runner.statistics.mean(values),
        median=_runner.statistics.median(values),
        min=min(values),
        max=max(values),
        std=_runner.statistics.stdev(values) if len(values) > 1 else 0.0,
        p90=_runner._eval_percentile(values, 0.90),
        p95=_runner._eval_percentile(values, 0.95),
        p99=_runner._eval_percentile(values, 0.99),
    )


def _metric_stats_to_dict(ms: Optional[MetricStats]) -> Optional[Dict[str, float]]:
    """Convert MetricStats to a JSON-serializable dict."""
    if ms is None:
        return None
    return {
        "mean": ms.mean,
        "median": ms.median,
        "min": ms.min,
        "max": ms.max,
        "std": ms.std,
        "p90": ms.p90,
        "p95": ms.p95,
        "p99": ms.p99,
    }


def _summary_to_dict(
    s: RunSummary,
    results: Optional[List[EvalResult]] = None,
) -> Dict[str, Any]:
    """Convert a RunSummary to a JSON-serializable dict.

    When ``results`` is provided, the dict ALSO carries the spec §6.3
    ``framework`` / ``framework_commit`` / ``n_tasks`` / ``metrics`` block
    expected by the framework-comparison ``table_gen`` loader. Existing
    top-level keys are preserved (this is purely additive).
    """
    d = {
        "hardware_info": _runner._hardware_info_dict(),
        "benchmark": s.benchmark,
        "category": s.category,
        "backend": s.backend,
        "model": s.model,
        "total_samples": s.total_samples,
        "scored_samples": s.scored_samples,
        "correct": s.correct,
        "accuracy": s.accuracy,
        "errors": s.errors,
        "mean_latency_seconds": s.mean_latency_seconds,
        "total_cost_usd": s.total_cost_usd,
        "per_subject": s.per_subject,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
        "accuracy_stats": _runner._metric_stats_to_dict(s.accuracy_stats),
        "latency_stats": _runner._metric_stats_to_dict(s.latency_stats),
        "ttft_stats": _runner._metric_stats_to_dict(s.ttft_stats),
        "energy_stats": _runner._metric_stats_to_dict(s.energy_stats),
        "power_stats": _runner._metric_stats_to_dict(s.power_stats),
        "gpu_utilization_stats": _runner._metric_stats_to_dict(s.gpu_utilization_stats),
        "throughput_stats": _runner._metric_stats_to_dict(s.throughput_stats),
        "mfu_stats": _runner._metric_stats_to_dict(s.mfu_stats),
        "mbu_stats": _runner._metric_stats_to_dict(s.mbu_stats),
        "ipw_stats": _runner._metric_stats_to_dict(s.ipw_stats),
        "ipj_stats": _runner._metric_stats_to_dict(s.ipj_stats),
        "energy_per_output_token_stats": _runner._metric_stats_to_dict(
            s.energy_per_output_token_stats,
        ),
        "throughput_per_watt_stats": _runner._metric_stats_to_dict(
            s.throughput_per_watt_stats,
        ),
        "itl_stats": _runner._metric_stats_to_dict(s.itl_stats),
        "input_token_stats": _runner._metric_stats_to_dict(s.input_token_stats),
        "output_token_stats": _runner._metric_stats_to_dict(s.output_token_stats),
        "total_energy_joules": s.total_energy_joules,
        "total_estimated_flops": s.total_estimated_flops,
        "flops_stats": _runner._metric_stats_to_dict(s.flops_stats),
        "warmup_samples_excluded": s.warmup_samples_excluded,
        "steady_state_reached": s.steady_state_reached,
        "energy_method": s.energy_method,
        "avg_power_watts": s.avg_power_watts,
        "total_input_tokens": s.total_input_tokens,
        "total_output_tokens": s.total_output_tokens,
        "efficiency": s.efficiency,
        "normalized_statistics": s.normalized_statistics,
        "normalized_efficiency": s.normalized_efficiency,
        "mean_continuous_score": s.mean_continuous_score,
        "median_continuous_score": s.median_continuous_score,
        "pct_above_0.5": s.pct_above_0_5,
        "pct_above_0.7": s.pct_above_0_7,
        "pct_above_0.8": s.pct_above_0_8,
        "pct_above_0.9": s.pct_above_0_9,
        "telemetry_summary": {
            "total_energy_joules": s.total_energy_joules,
            "avg_power_watts": s.avg_power_watts,
            "total_input_tokens": s.total_input_tokens,
            "total_output_tokens": s.total_output_tokens,
            "total_tokens": s.total_input_tokens + s.total_output_tokens,
            "total_estimated_flops": s.total_estimated_flops,
            "throughput_stats": _runner._metric_stats_to_dict(s.throughput_stats),
            "gpu_utilization_stats": _runner._metric_stats_to_dict(
                s.gpu_utilization_stats,
            ),
            "energy_stats": _runner._metric_stats_to_dict(s.energy_stats),
            "power_stats": _runner._metric_stats_to_dict(s.power_stats),
            "flops_stats": _runner._metric_stats_to_dict(s.flops_stats),
            "ipw": (s.efficiency.get("ipw") if s.efficiency else None),
            "ipj": (s.efficiency.get("ipj") if s.efficiency else None),
        },
    }

    # ---- Spec §6.3: table_gen-compatible flat schema ----
    # In addition to the existing rich schema, emit framework / commit /
    # per-metric stats so framework-comparison `table_gen.load_results`
    # can parse this file as a `_SummarySchema` row.
    fwk = "openjarvis"
    fwk_commit = ""
    if results:
        for r in results:
            if getattr(r, "framework", None):
                fwk = r.framework
                fwk_commit = r.framework_commit or ""
                break

    def _stats_block(vals: List[float]) -> Dict[str, Any]:
        if not vals:
            return {"mean": 0.0, "std": 0.0, "n": 0}
        return {
            "mean": float(_runner.statistics.fmean(vals)),
            "std": (float(_runner.statistics.stdev(vals)) if len(vals) > 1 else 0.0),
            "n": len(vals),
        }

    if results is not None:
        scored = [r for r in results if r.is_correct is not None]
        accuracy_vals = [1.0 if r.is_correct else 0.0 for r in scored]
        latency_vals = [r.latency_seconds for r in results if r.latency_seconds > 0]
        energy_vals = [r.energy_joules for r in results if r.energy_joules > 0]
        in_tok_vals = [float(r.prompt_tokens) for r in results if r.prompt_tokens > 0]
        out_tok_vals = [
            float(r.completion_tokens) for r in results if r.completion_tokens > 0
        ]
        cost_vals = [r.cost_usd for r in results if r.cost_usd > 0]
        power_vals = [r.power_watts for r in results if r.power_watts > 0]
        n_tasks = len(results)
    else:
        accuracy_vals = []
        latency_vals = []
        energy_vals = []
        in_tok_vals = []
        out_tok_vals = []
        cost_vals = []
        power_vals = []
        n_tasks = 0

    d["framework"] = fwk
    d["framework_commit"] = fwk_commit
    # `model` and `benchmark` are already top-level above; keep them.
    d["n_tasks"] = n_tasks
    d["metrics"] = {
        "accuracy": _stats_block(accuracy_vals),
        "latency_seconds": _stats_block(latency_vals),
        "energy_joules_per_query": _stats_block(energy_vals),
        "input_tokens_per_query": _stats_block(in_tok_vals),
        "output_tokens_per_query": _stats_block(out_tok_vals),
        "cost_usd_per_query": _stats_block(cost_vals),
        "peak_power_w": _stats_block(power_vals),
    }

    return d


def _result_to_trace_dict(result: EvalResult) -> Dict[str, Any]:
    """Convert an EvalResult to a full trace dict for per-sample export."""
    d = {
        "record_id": result.record_id,
        "model_answer": result.model_answer,
        "is_correct": result.is_correct,
        "score": result.score,
        "latency_seconds": result.latency_seconds,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "cost_usd": result.cost_usd,
        "error": result.error,
        "scoring_metadata": result.scoring_metadata,
        "ttft": result.ttft,
        "energy_joules": result.energy_joules,
        "power_watts": result.power_watts,
        "gpu_utilization_pct": result.gpu_utilization_pct,
        "throughput_tok_per_sec": result.throughput_tok_per_sec,
        "mfu_pct": result.mfu_pct,
        "mbu_pct": result.mbu_pct,
        "ipw": result.ipw,
        "ipj": result.ipj,
        "energy_per_output_token_joules": result.energy_per_output_token_joules,
        "throughput_per_watt": result.throughput_per_watt,
        "mean_itl_ms": result.mean_itl_ms,
        "estimated_flops": result.estimated_flops,
        # Spec §6.2 cross-framework fields
        "framework": result.framework,
        "framework_commit": result.framework_commit,
        "tool_calls": result.tool_calls,
        "turn_count": result.turn_count,
    }
    if result.trace_data is not None:
        d["trace_data"] = result.trace_data
    return d


__all__ = [
    "_compute_normalized_stats",
    "_eval_percentile",
    "_metric_stats",
    "_metric_stats_to_dict",
    "_summary_to_dict",
    "_result_to_trace_dict",
]

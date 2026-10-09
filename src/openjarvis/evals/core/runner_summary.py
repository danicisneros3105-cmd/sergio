"""EvalRunner's run summary: accuracy, scores, latency, tokens, cost and
energy aggregated over the results.

Split out of ``runner.py``; its names are looked up on that module at call
time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List

import openjarvis.evals.core.runner as _runner
from openjarvis.evals.core.types import EvalRecord, EvalResult, RunSummary


class _RunnerSummaryMixin:
    def _compute_summary(
        self,
        records: List[EvalRecord],
        started_at: float,
        ended_at: float,
    ) -> RunSummary:
        """Compute aggregate statistics from results."""
        cfg = self._config
        results = self._results

        scored = [r for r in results if r.is_correct is not None]
        correct = [r for r in scored if r.is_correct]
        errors = [r for r in results if r.error]

        latencies = [r.latency_seconds for r in results if r.latency_seconds > 0]
        mean_latency = sum(latencies) / len(latencies) if latencies else 0.0
        total_cost = sum(r.cost_usd for r in results)

        # Per-subject breakdown
        record_map = {r.record_id: r for r in records}
        subject_groups: Dict[str, List[EvalResult]] = _runner.defaultdict(list)
        for r in results:
            rec = record_map.get(r.record_id)
            subj = rec.subject if rec and rec.subject else "general"
            subject_groups[subj].append(r)

        per_subject: Dict[str, Dict[str, float]] = {}
        for subj, subj_results in sorted(subject_groups.items()):
            subj_scored = [r for r in subj_results if r.is_correct is not None]
            subj_correct = [r for r in subj_scored if r.is_correct]
            subj_acc = len(subj_correct) / len(subj_scored) if subj_scored else 0.0
            per_subject[subj] = {
                "accuracy": round(subj_acc, 4),
                "total": float(len(subj_results)),
                "scored": float(len(subj_scored)),
                "correct": float(len(subj_correct)),
            }

        # Determine category from records
        categories = {r.category for r in records}
        category = categories.pop() if len(categories) == 1 else cfg.benchmark

        accuracy = len(correct) / len(scored) if scored else 0.0

        # Continuous-score reporting: skip None (errored) entries; clamp values
        # outside [0,1] are already handled in _extract_continuous_score.
        cont_scores = [float(r.score) for r in results if r.score is not None]
        if cont_scores:
            mean_cont = sum(cont_scores) / len(cont_scores)
            median_cont = _runner.statistics.median(cont_scores)
            pct_above_05 = sum(1 for v in cont_scores if v > 0.5) / len(cont_scores)
            pct_above_07 = sum(1 for v in cont_scores if v > 0.7) / len(cont_scores)
            pct_above_08 = sum(1 for v in cont_scores if v > 0.8) / len(cont_scores)
            pct_above_09 = sum(1 for v in cont_scores if v > 0.9) / len(cont_scores)
        else:
            mean_cont = None
            median_cont = None
            pct_above_05 = None
            pct_above_07 = None
            pct_above_08 = None
            pct_above_09 = None

        # Compute MetricStats for each metric
        accuracy_vals = [1.0 if r.is_correct else 0.0 for r in scored]
        latency_vals = [r.latency_seconds for r in results if r.latency_seconds > 0]
        ttft_vals = [r.ttft for r in results if r.ttft > 0]
        energy_vals = [r.energy_joules for r in results if r.energy_joules > 0]
        power_vals = [r.power_watts for r in results if r.power_watts > 0]
        gpu_util_vals = [
            r.gpu_utilization_pct for r in results if r.gpu_utilization_pct > 0
        ]
        throughput_vals = [
            r.throughput_tok_per_sec for r in results if r.throughput_tok_per_sec > 0
        ]
        mfu_vals = [r.mfu_pct for r in results if r.mfu_pct > 0]
        mbu_vals = [r.mbu_pct for r in results if r.mbu_pct > 0]
        ipw_vals = [r.ipw for r in results if r.ipw > 0]
        ipj_vals = [r.ipj for r in results if r.ipj > 0]
        epot_vals = [
            r.energy_per_output_token_joules
            for r in results
            if r.energy_per_output_token_joules > 0
        ]
        tpw_vals = [r.throughput_per_watt for r in results if r.throughput_per_watt > 0]
        itl_vals = [r.mean_itl_ms for r in results if r.mean_itl_ms > 0]
        flops_vals = [r.estimated_flops for r in results if r.estimated_flops > 0]
        input_tok_vals = [r.prompt_tokens for r in results if r.prompt_tokens > 0]
        output_tok_vals = [
            r.completion_tokens for r in results if r.completion_tokens > 0
        ]

        total_energy = sum(r.energy_joules for r in results)
        # Per-rail totals, so a summary says which hardware did the work
        # rather than only how much it cost in aggregate.
        rail_totals = {
            rail: round(
                sum(getattr(r, f"{rail}_energy_joules", 0.0) for r in results), 6
            )
            for rail in ("cpu", "gpu", "dram", "ane", "soc")
        }
        rail_totals = {k: v for k, v in rail_totals.items() if v > 0}

        # How the energy was obtained, and from which rail set. Both are
        # per-record, but a run uses one monitor throughout; report the value
        # when it is unambiguous and flag genuine mixtures rather than
        # silently picking one.
        def _consensus(attr: str) -> str:
            seen = {getattr(r, attr, "") for r in results if getattr(r, attr, "")}
            if not seen:
                return ""
            return seen.pop() if len(seen) == 1 else "mixed"

        energy_method_value = _consensus("energy_method")
        energy_basis_value = _consensus("energy_basis")
        total_estimated_flops = sum(r.estimated_flops for r in results)
        total_input_tokens = sum(r.prompt_tokens for r in results)
        total_output_tokens = sum(r.completion_tokens for r in results)
        avg_power = _runner.statistics.mean(power_vals) if power_vals else 0.0

        # Compute efficiency section
        efficiency_dict: Dict[str, Any] = {
            "accuracy": round(accuracy, 4),
            "total_energy_joules": round(total_energy, 6),
            "avg_power_watts": round(avg_power, 4),
            "total_estimated_flops": total_estimated_flops,
            "energy_method": energy_method_value,
            "energy_basis": energy_basis_value,
            "energy_joules_by_rail": rail_totals or None,
            "ipj": (round(accuracy / total_energy, 6) if total_energy > 0 else None),
            "ipw": (round(accuracy / avg_power, 6) if avg_power > 0 else None),
        }

        # Compute normalized statistics (trim 5% outliers by latency)
        normalized_stats, normalized_eff = _runner._compute_normalized_stats(
            results,
            accuracy,
        )

        return _runner.RunSummary(
            benchmark=cfg.benchmark,
            category=category,
            backend=cfg.backend,
            model=cfg.model,
            total_samples=len(results),
            scored_samples=len(scored),
            correct=len(correct),
            accuracy=round(accuracy, 4),
            errors=len(errors),
            mean_latency_seconds=round(mean_latency, 4),
            total_cost_usd=round(total_cost, 6),
            per_subject=per_subject,
            started_at=started_at,
            ended_at=ended_at,
            accuracy_stats=_runner._metric_stats(accuracy_vals),
            latency_stats=_runner._metric_stats(latency_vals),
            ttft_stats=_runner._metric_stats(ttft_vals),
            energy_stats=_runner._metric_stats(energy_vals),
            power_stats=_runner._metric_stats(power_vals),
            gpu_utilization_stats=_runner._metric_stats(gpu_util_vals),
            throughput_stats=_runner._metric_stats(throughput_vals),
            mfu_stats=_runner._metric_stats(mfu_vals),
            mbu_stats=_runner._metric_stats(mbu_vals),
            ipw_stats=_runner._metric_stats(ipw_vals),
            ipj_stats=_runner._metric_stats(ipj_vals),
            energy_per_output_token_stats=_runner._metric_stats(epot_vals),
            throughput_per_watt_stats=_runner._metric_stats(tpw_vals),
            itl_stats=_runner._metric_stats(itl_vals),
            input_token_stats=_runner._metric_stats([float(v) for v in input_tok_vals]),
            output_token_stats=_runner._metric_stats(
                [float(v) for v in output_tok_vals]
            ),
            total_energy_joules=round(total_energy, 6),
            energy_method=energy_method_value,
            total_estimated_flops=total_estimated_flops,
            flops_stats=_runner._metric_stats(flops_vals),
            warmup_samples_excluded=cfg.warmup_samples,
            avg_power_watts=round(avg_power, 4),
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            efficiency=efficiency_dict,
            normalized_statistics=normalized_stats,
            normalized_efficiency=normalized_eff,
            mean_continuous_score=(
                round(mean_cont, 6) if mean_cont is not None else None
            ),
            median_continuous_score=(
                round(median_cont, 6) if median_cont is not None else None
            ),
            pct_above_0_5=(
                round(pct_above_05, 6) if pct_above_05 is not None else None
            ),
            pct_above_0_7=(
                round(pct_above_07, 6) if pct_above_07 is not None else None
            ),
            pct_above_0_8=(
                round(pct_above_08, 6) if pct_above_08 is not None else None
            ),
            pct_above_0_9=(
                round(pct_above_09, 6) if pct_above_09 is not None else None
            ),
        )


__all__ = ["_RunnerSummaryMixin"]

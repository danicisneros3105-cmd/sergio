"""EvalRunner — parallel execution of evaluation samples.

Supports two modes:
- **Parallel mode** (default): Samples processed concurrently via ThreadPoolExecutor.
- **Episode mode** (``episode_mode=True``): Samples processed sequentially within
  episodes, with in-context example injection from prior successful completions.
  Required for lifelong-learning benchmarks like LifelongAgentBench.

When a dataset provides ``create_task_env()`` returning a ``TaskEnvironment``,
samples are evaluated via multi-turn interactive loops instead of single-shot
generation — matching benchmarks that require agent-environment interaction.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math  # noqa: F401 - looked up here by runner_* modules
import re
import statistics  # noqa: F401 - looked up here by runner_* modules
import time
from collections import defaultdict  # noqa: F401 - used via runner_*
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, List, Optional

from openjarvis.evals.core.backend import InferenceBackend
from openjarvis.evals.core.dataset import DatasetProvider
from openjarvis.evals.core.export import _hardware_info_dict  # noqa: F401
from openjarvis.evals.core.scorer import Scorer
from openjarvis.evals.core.tracker import ResultTracker
from openjarvis.evals.core.types import (
    EvalRecord,
    EvalResult,
    MetricStats,  # noqa: F401 - used via runner_*
    RunConfig,
    RunSummary,
)

try:
    from openjarvis.telemetry.efficiency import compute_efficiency
except ImportError:  # pragma: no cover
    compute_efficiency = None  # type: ignore[assignment]

try:
    from openjarvis.telemetry.efficiency import estimate_model_flops_per_token
except ImportError:  # pragma: no cover
    estimate_model_flops_per_token = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _extract_continuous_score(scoring_meta, is_correct):
    """Pull continuous score (0.0-1.0) from scoring_meta, falling back to binary.

    Many scorers (LLM-judge, rubric, coverage) write a continuous ``score``
    into ``scoring_meta``; we surface that instead of binarising. Any value
    outside [0.0, 1.0] is clamped or rejected. When no continuous score is
    available we fall back to 1.0/0.0 from ``is_correct``.
    """
    if isinstance(scoring_meta, dict):
        cand = scoring_meta.get("score")
        if isinstance(cand, (int, float)) and not isinstance(cand, bool):
            v = float(cand)
            if v != v or v == float("inf") or v == float("-inf"):
                pass
            else:
                return max(0.0, min(1.0, v))
    if is_correct is None:
        return None
    return 1.0 if is_correct else 0.0


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from model output."""
    return _THINK_TAG_RE.sub("", text).strip()


# Method groups live in their own modules; they look helpers up here.
from openjarvis.evals.core.runner_modes import _RunnerModesMixin  # noqa: E402
from openjarvis.evals.core.runner_summary import _RunnerSummaryMixin  # noqa: E402


class EvalRunner(_RunnerModesMixin, _RunnerSummaryMixin):
    """Runs an evaluation benchmark with parallel sample execution."""

    def __init__(
        self,
        config: RunConfig,
        dataset: DatasetProvider,
        backend: InferenceBackend,
        scorer: Scorer,
        trackers: Optional[List[ResultTracker]] = None,
    ) -> None:
        self._config = config
        self._dataset = dataset
        self._backend = backend
        self._scorer = scorer
        self._trackers: List[ResultTracker] = trackers or []
        self._results: List[EvalResult] = []
        self._output_file: Optional[Any] = None

    @property
    def results(self) -> List[EvalResult]:
        """Return a copy of collected evaluation results."""
        return list(self._results)

    def run(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> RunSummary:
        """Execute the evaluation and return a summary.

        Args:
            progress_callback: Optional ``(completed, total)`` callback invoked
                after each sample completes, useful for driving progress bars.
        """
        cfg = self._config
        started_at = time.time()

        self._dataset.load(
            max_samples=cfg.max_samples,
            split=cfg.dataset_split,
            seed=cfg.seed,
        )

        # Auto-enable episode_mode when the dataset *overrides*
        # iter_episodes() (i.e. it is a lifelong/sequential benchmark like
        # LifelongAgentBench).  The base DatasetProvider always defines a
        # default iter_episodes() that wraps each record in its own episode,
        # so hasattr() is always True — we must check for a real override.
        from openjarvis.evals.core.dataset import DatasetProvider as _DP

        try:
            _overrides_episodes = (
                type(self._dataset).iter_episodes is not _DP.iter_episodes
            )
        except AttributeError:
            _overrides_episodes = False
        if not cfg.episode_mode and _overrides_episodes:
            LOGGER.info(
                "%s requires sequential episode processing — "
                "auto-enabling episode_mode.",
                cfg.benchmark,
            )
            cfg = dataclasses.replace(cfg, episode_mode=True)
            self._config = cfg

        # Detect if dataset provides task environments (e.g. PinchBench)
        try:
            self._has_task_env = (
                type(self._dataset).create_task_env is not _DP.create_task_env
            )
        except AttributeError:
            self._has_task_env = False

        # Probe whether this task env is thread-safe (no CWD changes, no
        # shared mutable globals). Datasets opt in by setting THREAD_SAFE = True
        # on the env class returned by create_task_env. Default: False (safe).
        self._task_env_thread_safe = False
        if self._has_task_env:
            try:
                # Cheap probe: instantiate-free attribute lookup via a sample record
                sample_records = list(self._dataset.iter_records())
                if sample_records:
                    probe_env = self._dataset.create_task_env(sample_records[0])
                    if probe_env is not None and getattr(
                        type(probe_env), "THREAD_SAFE", False
                    ):
                        self._task_env_thread_safe = True
            except Exception as exc:  # pragma: no cover - probe is best-effort
                LOGGER.debug("Task env thread-safety probe failed: %s", exc)

        records = list(self._dataset.iter_records())
        if cfg.record_ids:
            wanted = set(cfg.record_ids)
            before = len(records)
            records = [r for r in records if r.record_id in wanted]
            LOGGER.info(
                "Filtering %s to %d/%d records via record_ids (first 3: %s)",
                cfg.benchmark,
                len(records),
                before,
                ", ".join(sorted(wanted)[:3]),
            )
        LOGGER.info(
            "Running %s: %d samples, backend=%s, model=%s, workers=%d, episode_mode=%s",
            cfg.benchmark,
            len(records),
            cfg.backend,
            cfg.model,
            cfg.max_workers,
            cfg.episode_mode,
        )

        # --- Warmup phase (discard results) ---
        warmup_count = cfg.warmup_samples
        if warmup_count > 0 and records:
            warmup_records = records[:warmup_count]
            for rec in warmup_records:
                self._process_one(rec)
            LOGGER.info("Warmup complete: %d samples discarded", len(warmup_records))

        # Open output file for incremental JSONL writing
        output_path = self._resolve_output_path()
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._output_file = open(output_path, "w")

        # Notify trackers of run start
        for tracker in self._trackers:
            try:
                tracker.on_run_start(cfg)
            except Exception as exc:
                LOGGER.warning(
                    "Tracker %s.on_run_start failed: %s",
                    type(tracker).__name__,
                    exc,
                )

        total = len(records)
        try:
            if cfg.episode_mode:
                self._run_episode_mode(records, progress_callback, total)
            elif self._has_task_env and not self._task_env_thread_safe:
                # Task environments (PinchBench etc.) change CWD —
                # must process sequentially for thread safety.
                # Envs that opt in via THREAD_SAFE=True fall through to the
                # parallel ThreadPoolExecutor branch below.
                for record in records:
                    result = self._process_one(record)
                    self._results.append(result)
                    self._flush_result(result)
                    if progress_callback is not None:
                        progress_callback(len(self._results), total)
            else:
                with ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
                    futures = {pool.submit(self._process_one, r): r for r in records}
                    for future in as_completed(futures):
                        result = future.result()
                        self._results.append(result)
                        self._flush_result(result)
                        if progress_callback is not None:
                            progress_callback(len(self._results), total)
        finally:
            if self._output_file:
                self._output_file.close()
                self._output_file = None

        ended_at = time.time()
        summary = self._compute_summary(records, started_at, ended_at)

        # Notify trackers of summary and run end
        for tracker in self._trackers:
            try:
                tracker.on_summary(summary)
            except Exception as exc:
                LOGGER.warning(
                    "Tracker %s.on_summary failed: %s",
                    type(tracker).__name__,
                    exc,
                )
            try:
                tracker.on_run_end()
            except Exception as exc:
                LOGGER.warning(
                    "Tracker %s.on_run_end failed: %s",
                    type(tracker).__name__,
                    exc,
                )

        # Write summary JSON alongside JSONL
        traces_dir: Optional[Path] = None
        if output_path:
            summary_path = output_path.with_suffix(".summary.json")
            with open(summary_path, "w") as f:
                json.dump(
                    _summary_to_dict(summary, results=self._results),
                    f,
                    indent=2,
                )
            LOGGER.info("Results written to %s", output_path)
            LOGGER.info("Summary written to %s", summary_path)

            # Write per-trace data
            traces_dir = self._write_traces(output_path)

        # Attach paths to summary for callers (e.g. CLI display)
        summary._output_path = output_path  # type: ignore[attr-defined]
        summary._traces_dir = traces_dir  # type: ignore[attr-defined]

        return summary

    def _write_traces(self, output_path: Path) -> Optional[Path]:
        """Write per-sample trace data to a traces subdirectory."""
        if not self._results:
            return None
        cfg = self._config
        model_slug = cfg.model.replace("/", "-").replace(":", "-")
        traces_dir = output_path.parent / "traces" / f"{cfg.benchmark}_{model_slug}"
        traces_dir.mkdir(parents=True, exist_ok=True)
        with open(traces_dir / "traces.jsonl", "w") as f:
            for result in self._results:
                f.write(json.dumps(_result_to_trace_dict(result), default=str) + "\n")
        LOGGER.info("Traces written to %s", traces_dir)
        return traces_dir

    def _process_one(self, record: EvalRecord) -> EvalResult:
        """Process a single evaluation sample."""
        cfg = self._config

        def _backend_error_result(full: dict, message: str) -> EvalResult:
            usage = full.get("usage", {}) or {}
            energy_j = full.get("energy_joules", 0.0) or 0.0
            power_w = full.get("power_watts") or full.get("peak_power_w") or 0.0
            return EvalResult(
                record_id=record.record_id,
                model_answer=full.get("content", "") or "",
                error=message,
                latency_seconds=full.get("latency_seconds", 0.0) or 0.0,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                cost_usd=full.get("cost_usd", 0.0) or 0.0,
                ttft=full.get("ttft", 0.0) or 0.0,
                energy_joules=energy_j,
                power_watts=power_w,
                cpu_energy_joules=full.get("cpu_energy_joules", 0.0) or 0.0,
                gpu_energy_joules=full.get("gpu_energy_joules", 0.0) or 0.0,
                dram_energy_joules=full.get("dram_energy_joules", 0.0) or 0.0,
                ane_energy_joules=full.get("ane_energy_joules", 0.0) or 0.0,
                soc_energy_joules=full.get("soc_energy_joules", 0.0) or 0.0,
                energy_basis=full.get("energy_basis", "") or "",
                energy_method=full.get("energy_method", "") or "",
                gpu_utilization_pct=full.get("gpu_utilization_pct", 0.0) or 0.0,
                throughput_tok_per_sec=full.get("throughput_tok_per_sec", 0.0) or 0.0,
                trace_data=full.get("trace_data"),
                framework=full.get(
                    "framework",
                    getattr(self._backend, "framework_name", "openjarvis"),
                ),
                framework_commit=full.get(
                    "framework_commit",
                    getattr(self._backend, "framework_commit_value", "") or "",
                ),
                tool_calls=int(full.get("tool_calls", 0) or 0),
                turn_count=int(full.get("turn_count", 0) or 0),
            )

        try:
            gen_kwargs: dict = dict(
                model=cfg.model,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )
            if cfg.system_prompt:
                gen_kwargs["system"] = cfg.system_prompt

            if getattr(self, "_has_task_env", False):
                from contextlib import nullcontext

                task_env = self._dataset.create_task_env(record)
                ctx = task_env if task_env is not None else nullcontext()
                with ctx:
                    full = self._backend.generate_full(
                        record.problem,
                        **gen_kwargs,
                    )
                    full = full or {}
                    if full.get("error"):
                        return _backend_error_result(full, str(full["error"]))
                    all_tool_results = list(
                        full.get(
                            "tool_results",
                            [],
                        )
                    )

                    # Multi-session: execute remaining sessions
                    sessions = record.metadata.get("sessions", [])
                    if record.metadata.get("multi_session") and len(sessions) > 1:
                        for session in sessions[1:]:
                            prompt = session.get("prompt", "")
                            if not prompt:
                                continue
                            sfull = self._backend.generate_full(
                                prompt,
                                **gen_kwargs,
                            )
                            sfull = sfull or {}
                            if sfull.get("error"):
                                return _backend_error_result(sfull, str(sfull["error"]))
                            all_tool_results.extend(
                                sfull.get("tool_results", []),
                            )

                    record.metadata["tool_results"] = all_tool_results
                    # Score INSIDE context so workspace files still exist
                    content = full.get("content", "")
                    is_correct, scoring_meta = self._scorer.score(
                        record,
                        content,
                    )
            else:
                full = self._backend.generate_full(
                    record.problem,
                    **gen_kwargs,
                )
                full = full or {}
                if full.get("error"):
                    return _backend_error_result(full, str(full["error"]))
                content = full.get("content", "")
                is_correct, scoring_meta = self._scorer.score(
                    record,
                    content,
                )

            usage = full.get("usage", {})
            latency = full.get("latency_seconds", 0.0)
            cost = full.get("cost_usd", 0.0)

            # Coerce None -> 0.0: backends may emit None when telemetry is
            # unavailable (e.g., HermesBackend when no GPU sampler). The
            # 'or 0.0' handles the case where the key is present but the
            # value is None -- .get(default) only kicks in when missing.
            energy_j = full.get("energy_joules", 0.0) or 0.0
            power_w = full.get("power_watts") or full.get("peak_power_w") or 0.0
            throughput = full.get("throughput_tok_per_sec", 0.0) or 0.0
            accuracy_score = 1.0 if is_correct else 0.0

            # Compute IPW and IPJ
            ipw = (accuracy_score / power_w) if power_w > 0 else 0.0
            ipj = (accuracy_score / energy_j) if energy_j > 0 else 0.0

            # Compute MFU/MBU if efficiency module available and we have
            # model params from config metadata
            mfu = 0.0
            mbu = 0.0
            if compute_efficiency is not None and throughput > 0:
                model_meta = cfg.metadata or {}
                param_b = model_meta.get("param_count_b", 0.0)
                active_b = model_meta.get("active_params_b")
                gpu_tflops = model_meta.get("gpu_peak_tflops", 0.0)
                gpu_bw = model_meta.get("gpu_peak_bandwidth_gb_s", 0.0)
                num_gpus = model_meta.get("num_gpus", 1)
                if param_b > 0 and gpu_tflops > 0:
                    eff = compute_efficiency(
                        param_count_b=param_b,
                        active_params_b=active_b,
                        gpu_peak_tflops=gpu_tflops,
                        gpu_peak_bandwidth_gb_s=gpu_bw,
                        tokens_per_sec=throughput,
                        num_gpus=num_gpus,
                        energy_joules=energy_j,
                        accuracy=accuracy_score,
                    )
                    mfu = eff.mfu_pct
                    mbu = eff.mbu_pct

            # Estimate FLOPs: 2 * active_params * total_tokens
            estimated_flops = 0.0
            if estimate_model_flops_per_token is not None:
                model_meta = cfg.metadata or {}
                param_b = model_meta.get("param_count_b", 0.0)
                active_b = model_meta.get("active_params_b")
                total_tokens = usage.get("prompt_tokens", 0) + usage.get(
                    "completion_tokens", 0
                )
                if param_b > 0 and total_tokens > 0:
                    flops_per_tok = estimate_model_flops_per_token(param_b, active_b)
                    estimated_flops = flops_per_tok * total_tokens

            # Extract derived and ITL metrics from _telemetry dict
            _telem = full.get("_telemetry", {})
            energy_per_out_tok = (
                _telem.get("energy_per_output_token_joules", 0.0) or 0.0
            )
            throughput_per_w = _telem.get("throughput_per_watt", 0.0) or 0.0
            mean_itl = _telem.get("mean_itl_ms", 0.0) or 0.0

            # Prefer continuous score from scoring_meta when scorer provides it.
            score_val = _extract_continuous_score(scoring_meta, is_correct)
            return EvalResult(
                record_id=record.record_id,
                model_answer=content,
                is_correct=is_correct,
                score=score_val,
                latency_seconds=latency,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                cost_usd=cost,
                scoring_metadata=scoring_meta,
                ttft=full.get("ttft", 0.0) or 0.0,
                energy_joules=energy_j,
                power_watts=power_w,
                cpu_energy_joules=full.get("cpu_energy_joules", 0.0) or 0.0,
                gpu_energy_joules=full.get("gpu_energy_joules", 0.0) or 0.0,
                dram_energy_joules=full.get("dram_energy_joules", 0.0) or 0.0,
                ane_energy_joules=full.get("ane_energy_joules", 0.0) or 0.0,
                soc_energy_joules=full.get("soc_energy_joules", 0.0) or 0.0,
                energy_basis=full.get("energy_basis", "") or "",
                energy_method=full.get("energy_method", "") or "",
                gpu_utilization_pct=full.get("gpu_utilization_pct", 0.0) or 0.0,
                throughput_tok_per_sec=throughput,
                mfu_pct=mfu,
                mbu_pct=mbu,
                ipw=ipw,
                ipj=ipj,
                energy_per_output_token_joules=energy_per_out_tok,
                throughput_per_watt=throughput_per_w,
                mean_itl_ms=mean_itl,
                estimated_flops=estimated_flops,
                trace_data=full.get("trace_data"),
                # Spec §6.2 extended fields for cross-framework comparison
                framework=full.get("framework", "openjarvis"),
                framework_commit=full.get("framework_commit", ""),
                tool_calls=int(full.get("tool_calls", 0)),
                turn_count=int(full.get("turn_count", 0)),
            )
        except Exception as exc:
            LOGGER.error("Error processing %s: %s", record.record_id, exc)
            return EvalResult(
                record_id=record.record_id,
                model_answer="",
                error=str(exc),
                framework=getattr(self._backend, "framework_name", "openjarvis"),
                framework_commit=getattr(self._backend, "framework_commit_value", "")
                or "",
                tool_calls=0,
                turn_count=0,
            )

    # ------------------------------------------------------------------
    # Episode mode: sequential processing with lifelong learning
    # ------------------------------------------------------------------

    # Max prior examples to inject (FIFO eviction), matching original default
    _MAX_PRIOR_EXAMPLES = 3

    # ------------------------------------------------------------------
    # Interactive multi-turn processing
    # ------------------------------------------------------------------

    _MAX_INTERACTIVE_TURNS_DEFAULT = 15

    def _flush_result(self, result: EvalResult) -> None:
        """Append a single result to the output JSONL file."""
        if not self._output_file:
            return
        record_dict = {
            "record_id": result.record_id,
            "benchmark": self._config.benchmark,
            "model": self._config.model,
            "backend": self._config.backend,
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
            "cpu_energy_joules": result.cpu_energy_joules,
            "gpu_energy_joules": result.gpu_energy_joules,
            "dram_energy_joules": result.dram_energy_joules,
            "ane_energy_joules": result.ane_energy_joules,
            "soc_energy_joules": result.soc_energy_joules,
            "energy_basis": result.energy_basis,
            "energy_method": result.energy_method,
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
        }
        try:
            line = json.dumps(record_dict, default=str)
        except Exception as exc:
            LOGGER.error(
                "Failed to serialize result %s to JSON: %s — writing error record",
                result.record_id,
                exc,
            )
            line = json.dumps(
                {
                    "record_id": result.record_id,
                    "benchmark": self._config.benchmark,
                    "model": self._config.model,
                    "is_correct": result.is_correct,
                    "error": f"serialization_error: {exc}",
                }
            )
        self._output_file.write(line + "\n")
        self._output_file.flush()

        # Notify trackers of each result
        for tracker in self._trackers:
            try:
                tracker.on_result(result, self._config)
            except Exception as exc:
                LOGGER.warning(
                    "Tracker %s.on_result failed: %s",
                    type(tracker).__name__,
                    exc,
                )

    def _resolve_output_path(self) -> Optional[Path]:
        """Determine the output file path."""
        if self._config.output_path:
            return Path(self._config.output_path)
        # Auto-generate under results/ based on benchmark + model
        model_slug = self._config.model.replace("/", "-").replace(":", "-")
        name = f"{self._config.benchmark}_{model_slug}.jsonl"
        return Path("results") / name


__all__ = ["EvalRunner"]

# Moved to their own module (it looks its helpers up here).
from openjarvis.evals.core import runner_stats as _runner_stats  # noqa: E402,I001

_compute_normalized_stats = _runner_stats._compute_normalized_stats
_eval_percentile = _runner_stats._eval_percentile
_metric_stats = _runner_stats._metric_stats
_metric_stats_to_dict = _runner_stats._metric_stats_to_dict
_summary_to_dict = _runner_stats._summary_to_dict
_result_to_trace_dict = _runner_stats._result_to_trace_dict

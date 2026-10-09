"""Builders used by the eval CLI: dataset, scorer, inference backend and
judge backend for a benchmark name.

Split out of ``evals/cli.py``; its names are looked up on that module at
call time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Optional

import openjarvis.evals.cli as _ecli


def _build_dataset(benchmark: str, subset: str | None = None):
    """Construct the dataset provider for a benchmark."""
    if benchmark == "supergpqa":
        from openjarvis.evals.datasets.supergpqa import SuperGPQADataset

        return SuperGPQADataset()
    elif benchmark == "gpqa":
        from openjarvis.evals.datasets.gpqa import GPQADataset

        return GPQADataset()
    elif benchmark == "mmlu-pro":
        from openjarvis.evals.datasets.mmlu_pro import MMLUProDataset

        return MMLUProDataset()
    elif benchmark == "math500":
        from openjarvis.evals.datasets.math500 import MATH500Dataset

        return MATH500Dataset()
    elif benchmark == "natural-reasoning":
        from openjarvis.evals.datasets.natural_reasoning import NaturalReasoningDataset

        return NaturalReasoningDataset()
    elif benchmark == "hle":
        from openjarvis.evals.datasets.hle import HLEDataset

        return HLEDataset()
    elif benchmark == "simpleqa":
        from openjarvis.evals.datasets.simpleqa import SimpleQADataset

        return SimpleQADataset()
    elif benchmark == "wildchat":
        from openjarvis.evals.datasets.wildchat import WildChatDataset

        return WildChatDataset()
    elif benchmark == "ipw":
        from openjarvis.evals.datasets.ipw_mixed import IPWDataset

        return IPWDataset()
    elif benchmark == "gaia":
        from openjarvis.evals.datasets.gaia import GAIADataset

        return GAIADataset()
    elif benchmark == "frames":
        from openjarvis.evals.datasets.frames import FRAMESDataset

        return FRAMESDataset()
    elif benchmark == "swebench":
        from openjarvis.evals.datasets.swebench import SWEBenchDataset

        return SWEBenchDataset()
    elif benchmark == "swefficiency":
        from openjarvis.evals.datasets.swefficiency import SWEfficiencyDataset

        return SWEfficiencyDataset()
    elif benchmark == "terminalbench":
        from openjarvis.evals.datasets.terminalbench import TerminalBenchDataset

        return TerminalBenchDataset()
    elif benchmark == "terminalbench-native":
        from openjarvis.evals.datasets.terminalbench_native import (
            TerminalBenchNativeDataset,
        )

        return TerminalBenchNativeDataset()
    elif benchmark == "terminalbench-v2.1":
        from openjarvis.evals.datasets.terminalbench_v2_1 import (
            TerminalBenchV21Dataset,
        )

        return TerminalBenchV21Dataset()
    elif benchmark == "email_triage":
        from openjarvis.evals.datasets.email_triage import EmailTriageDataset

        return EmailTriageDataset()
    elif benchmark == "morning_brief":
        from openjarvis.evals.datasets.morning_brief import MorningBriefDataset

        return MorningBriefDataset()
    elif benchmark == "research_mining":
        from openjarvis.evals.datasets.research_mining import ResearchMiningDataset

        return ResearchMiningDataset()
    elif benchmark == "knowledge_base":
        from openjarvis.evals.datasets.knowledge_base import KnowledgeBaseDataset

        return KnowledgeBaseDataset()
    elif benchmark == "coding_task":
        from openjarvis.evals.datasets.coding_task import CodingTaskDataset

        return CodingTaskDataset()
    elif benchmark == "loghub":
        from openjarvis.evals.datasets.loghub import LogHubDataset

        return LogHubDataset()
    elif benchmark == "ama-bench":
        from openjarvis.evals.datasets.ama_bench import AMABenchDataset

        return AMABenchDataset()
    elif benchmark == "lifelong-agent":
        from openjarvis.evals.datasets.lifelong_agent import LifelongAgentDataset

        return LifelongAgentDataset(subset=subset or "db_bench")
    elif benchmark == "deepplanning":
        from openjarvis.evals.datasets.deepplanning import DeepPlanningDataset

        return DeepPlanningDataset()
    elif benchmark == "paperarena":
        from openjarvis.evals.datasets.paperarena import PaperArenaDataset

        return PaperArenaDataset()
    elif benchmark == "webchorearena":
        from openjarvis.evals.datasets.webchorearena import WebChoreArenaDataset

        return WebChoreArenaDataset()
    elif benchmark == "workarena":
        from openjarvis.evals.datasets.workarena import WorkArenaDataset

        return WorkArenaDataset()
    elif benchmark == "coding_assistant":
        from openjarvis.evals.datasets.coding_assistant import CodingAssistantDataset

        return CodingAssistantDataset()
    elif benchmark == "security_scanner":
        from openjarvis.evals.datasets.security_scanner import SecurityScannerDataset

        return SecurityScannerDataset()
    elif benchmark == "daily_digest":
        from openjarvis.evals.datasets.daily_digest import DailyDigestDataset

        return DailyDigestDataset()
    elif benchmark == "doc_qa":
        from openjarvis.evals.datasets.doc_qa import DocQADataset

        return DocQADataset()
    elif benchmark == "browser_assistant":
        from openjarvis.evals.datasets.browser_assistant import BrowserAssistantDataset

        return BrowserAssistantDataset()
    elif benchmark == "pinchbench":
        from openjarvis.evals.datasets.pinchbench import PinchBenchDataset

        return PinchBenchDataset(path=subset)
    elif benchmark == "taubench":
        from openjarvis.evals.datasets.taubench import TauBenchDataset

        domains = subset.split(",") if subset else None
        return TauBenchDataset(domains=domains)
    elif benchmark == "livecodebench":
        from openjarvis.evals.datasets.livecodebench import LiveCodeBenchDataset

        return LiveCodeBenchDataset()
    elif benchmark in ("liveresearch", "deepresearch"):
        from openjarvis.evals.datasets.liveresearch import LiveResearchBenchDataset

        return LiveResearchBenchDataset(path=subset)
    elif benchmark == "liveresearchbench":
        from openjarvis.evals.datasets.liveresearchbench import (
            LiveResearchBenchDataset as LRBDataset,
        )

        return LRBDataset()
    elif benchmark == "toolcall15":
        from openjarvis.evals.datasets.toolcall15 import ToolCall15Dataset

        return ToolCall15Dataset()
    else:
        raise _ecli.click.ClickException(f"Unknown benchmark: {benchmark}")


def _build_scorer(benchmark: str, judge_backend, judge_model: str):
    """Construct the scorer for a benchmark."""
    if benchmark == "supergpqa":
        from openjarvis.evals.scorers.supergpqa_mcq import SuperGPQAScorer

        return SuperGPQAScorer(judge_backend, judge_model)
    elif benchmark == "gpqa":
        from openjarvis.evals.scorers.gpqa_mcq import GPQAScorer

        return GPQAScorer(judge_backend, judge_model)
    elif benchmark == "mmlu-pro":
        from openjarvis.evals.scorers.mmlu_pro_mcq import MMLUProScorer

        return MMLUProScorer(judge_backend, judge_model)
    elif benchmark == "math500" or benchmark == "natural-reasoning":
        from openjarvis.evals.scorers.reasoning_judge import ReasoningJudgeScorer

        return ReasoningJudgeScorer(judge_backend, judge_model)
    elif benchmark == "hle":
        from openjarvis.evals.scorers.hle_judge import HLEScorer

        return HLEScorer(judge_backend, judge_model)
    elif benchmark == "simpleqa":
        from openjarvis.evals.scorers.simpleqa_judge import SimpleQAScorer

        return SimpleQAScorer(judge_backend, judge_model)
    elif benchmark == "wildchat":
        from openjarvis.evals.scorers.wildchat_judge import WildChatScorer

        return WildChatScorer(judge_backend, judge_model)
    elif benchmark == "ipw":
        from openjarvis.evals.scorers.ipw_mixed import IPWMixedScorer

        return IPWMixedScorer(judge_backend, judge_model)
    elif benchmark == "gaia":
        from openjarvis.evals.scorers.gaia_exact import GAIAScorer

        return GAIAScorer(judge_backend, judge_model)
    elif benchmark == "frames":
        from openjarvis.evals.scorers.frames_judge import FRAMESScorer

        return FRAMESScorer(judge_backend, judge_model)
    elif benchmark == "swebench":
        from openjarvis.evals.scorers.swebench_structural import SWEBenchScorer

        return SWEBenchScorer(judge_backend, judge_model)
    elif benchmark == "swefficiency":
        from openjarvis.evals.scorers.swefficiency_structural import SWEfficiencyScorer

        return SWEfficiencyScorer(judge_backend, judge_model)
    elif benchmark == "terminalbench":
        from openjarvis.evals.scorers.terminalbench_judge import TerminalBenchScorer

        return TerminalBenchScorer(judge_backend, judge_model)
    elif benchmark == "terminalbench-native":
        from openjarvis.evals.scorers.terminalbench_native_structural import (
            TerminalBenchNativeScorer,
        )

        return TerminalBenchNativeScorer(judge_backend, judge_model)
    elif benchmark == "terminalbench-v2.1":
        from openjarvis.evals.scorers.terminalbench_v2_1 import (
            TerminalBenchV21Scorer,
        )

        return TerminalBenchV21Scorer(judge_backend, judge_model)
    elif benchmark == "email_triage":
        from openjarvis.evals.scorers.email_triage import EmailTriageScorer

        return EmailTriageScorer(judge_backend, judge_model)
    elif benchmark == "morning_brief":
        from openjarvis.evals.scorers.morning_brief import MorningBriefScorer

        return MorningBriefScorer(judge_backend, judge_model)
    elif benchmark == "research_mining":
        from openjarvis.evals.scorers.research_mining import ResearchMiningScorer

        return ResearchMiningScorer(judge_backend, judge_model)
    elif benchmark == "knowledge_base":
        from openjarvis.evals.scorers.knowledge_base import KnowledgeBaseScorer

        return KnowledgeBaseScorer(judge_backend, judge_model)
    elif benchmark == "coding_task":
        from openjarvis.evals.scorers.coding_task import CodingTaskScorer

        return CodingTaskScorer(judge_backend, judge_model)
    elif benchmark == "loghub":
        from openjarvis.evals.scorers.loghub_scorer import LogHubScorer

        return LogHubScorer(judge_backend, judge_model)
    elif benchmark == "ama-bench":
        from openjarvis.evals.scorers.ama_bench_judge import AMABenchScorer

        return AMABenchScorer(judge_backend, judge_model)
    elif benchmark == "lifelong-agent":
        from openjarvis.evals.scorers.lifelong_agent_scorer import LifelongAgentScorer

        return LifelongAgentScorer(judge_backend, judge_model)
    elif benchmark == "deepplanning":
        from openjarvis.evals.scorers.deepplanning_scorer import DeepPlanningScorer

        return DeepPlanningScorer(judge_backend, judge_model)
    elif benchmark == "paperarena":
        from openjarvis.evals.scorers.paperarena_judge import PaperArenaScorer

        return PaperArenaScorer(judge_backend, judge_model)
    elif benchmark == "webchorearena":
        from openjarvis.evals.scorers.webchorearena_scorer import WebChoreArenaScorer

        return WebChoreArenaScorer(judge_backend, judge_model)
    elif benchmark == "workarena":
        from openjarvis.evals.scorers.workarena_scorer import WorkArenaScorer

        return WorkArenaScorer(judge_backend, judge_model)
    elif benchmark == "coding_assistant":
        from openjarvis.evals.scorers.coding_assistant import CodingAssistantScorer

        return CodingAssistantScorer(judge_backend, judge_model)
    elif benchmark == "security_scanner":
        from openjarvis.evals.scorers.security_scanner import SecurityScannerScorer

        return SecurityScannerScorer(judge_backend, judge_model)
    elif benchmark == "daily_digest":
        from openjarvis.evals.scorers.daily_digest import DailyDigestScorer

        return DailyDigestScorer(judge_backend, judge_model)
    elif benchmark == "doc_qa":
        from openjarvis.evals.scorers.doc_qa import DocQAScorer

        return DocQAScorer(judge_backend, judge_model)
    elif benchmark == "browser_assistant":
        from openjarvis.evals.scorers.browser_assistant import BrowserAssistantScorer

        return BrowserAssistantScorer(judge_backend, judge_model)
    elif benchmark == "pinchbench":
        from openjarvis.evals.scorers.pinchbench import PinchBenchScorer

        return PinchBenchScorer(judge_backend, judge_model)
    elif benchmark == "taubench":
        from openjarvis.evals.scorers.taubench import TauBenchScorer

        return TauBenchScorer(judge_backend, judge_model)
    elif benchmark == "livecodebench":
        from openjarvis.evals.scorers.livecodebench import LiveCodeBenchScorer

        return LiveCodeBenchScorer(judge_backend, judge_model)
    elif benchmark in ("liveresearch", "deepresearch"):
        from openjarvis.evals.scorers.liveresearch import LiveResearchBenchScorer

        return LiveResearchBenchScorer(judge_backend, judge_model)
    elif benchmark == "liveresearchbench":
        from openjarvis.evals.scorers.liveresearchbench import (
            LiveResearchBenchScorer as LRBScorer,
        )

        return LRBScorer(judge_backend, judge_model)
    elif benchmark == "toolcall15":
        from openjarvis.evals.scorers.toolcall15 import ToolCall15Scorer

        return ToolCall15Scorer(judge_backend, judge_model)
    else:
        raise _ecli.click.ClickException(f"Unknown benchmark: {benchmark}")


def _build_backend(
    backend_name: str,
    engine_key: Optional[str],
    agent_name: str,
    tools: list[str],
    telemetry: bool = False,
    gpu_metrics: bool = False,
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    first_party_endpoint: bool = True,
):
    """Construct the appropriate backend.

    ``base_url``/``api_key`` point at the OpenAI-compatible endpoint serving
    the model under eval:

    - For "hermes" and "openclaw" they are REQUIRED — these foreign
      frameworks always call out to an external endpoint.
    - "jarvis-direct" and "jarvis-agent" honor them when
      ``first_party_endpoint`` is True (the CLI ``--base-url`` path): the
      eval targets exactly that endpoint — no engine-discovery fallback —
      and fails fast if it is unreachable. Suite mode passes
      ``first_party_endpoint=False`` so the suite TOML's
      ``[backend.external]`` section stays scoped to hermes/openclaw
      (extending it to first-party backends is explicitly deferred).
    """
    if not first_party_endpoint:
        fp_base_url = fp_api_key = None
    else:
        fp_base_url, fp_api_key = base_url, api_key

    if backend_name == "jarvis-agent":
        from openjarvis.evals.backends.jarvis_agent import JarvisAgentBackend

        return JarvisAgentBackend(
            engine_key=engine_key,
            agent_name=agent_name,
            tools=tools,
            telemetry=telemetry,
            gpu_metrics=gpu_metrics,
            model=model,
            max_turns=max_turns,
            base_url=fp_base_url,
            api_key=fp_api_key,
        )
    elif backend_name == "jarvis-direct":
        from openjarvis.evals.backends.jarvis_direct import JarvisDirectBackend

        return JarvisDirectBackend(
            engine_key=engine_key,
            telemetry=telemetry,
            gpu_metrics=gpu_metrics,
            base_url=fp_base_url,
            api_key=fp_api_key,
        )
    elif backend_name == "hermes":
        from openjarvis.evals.backends.external import HermesBackend

        if not base_url or not api_key:
            raise _ecli.click.UsageError(
                "hermes backend requires --base-url and --api-key (or "
                "the equivalent env vars / config entries) — Hermes needs "
                "an OpenAI-compatible endpoint to call the model."
            )
        return HermesBackend(
            base_url=base_url,
            api_key=api_key,
        )
    elif backend_name == "openclaw":
        from openjarvis.evals.backends.external import OpenClawBackend

        if not base_url or not api_key:
            raise _ecli.click.UsageError(
                "openclaw backend requires --base-url and --api-key (or "
                "the equivalent env vars / config entries) — OpenClaw needs "
                "an OpenAI-compatible endpoint to call the model."
            )
        return OpenClawBackend(
            base_url=base_url,
            api_key=api_key,
        )
    else:
        raise _ecli.click.UsageError(
            f"unknown backend {backend_name!r}; valid: {list(_ecli.BACKENDS)}"
        )


def _build_judge_backend(judge_model: str, engine_key: str = "cloud"):
    """Build the judge backend for LLM-as-judge scoring.

    Returns None if no engine is reachable — deterministic scorers
    (e.g. LifelongAgentScorer, GAIAScorer) accept None and ignore it.
    LLM-judge scorers will raise a clear error when they actually try
    to use the backend rather than failing at startup.
    """
    from openjarvis.evals.backends.jarvis_direct import JarvisDirectBackend

    try:
        return JarvisDirectBackend(engine_key=engine_key)
    except RuntimeError as exc:
        _ecli.LOGGER.warning(
            "Judge backend (%s) unavailable: %s — "
            "deterministic scorers will still work; "
            "LLM-judge scorers will fail when scoring.",
            engine_key,
            exc,
        )
        return None


__all__ = ["_build_dataset", "_build_scorer", "_build_backend", "_build_judge_backend"]

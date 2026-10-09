"""Intelligence and learning configuration: routing, SFT/GRPO, DSPy/GEPA/ACE
optimizers, metrics and spec search. Split out of ``config.py``, which
re-exports every name.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from openjarvis.core.paths import (
    get_config_dir,
)


@dataclass(slots=True)
class IntelligenceConfig:
    """The model — identity, paths, quantization, and generation defaults."""

    default_model: str = ""
    # Optional per-CLI preset (used when ``-m`` omitted or ``-m smart``).
    model_chat: str = ""
    model_short: str = ""
    model_long: str = ""
    model_code: str = ""
    fallback_model: str = ""
    model_path: str = ""  # Local weights (HF repo, GGUF file, etc.)
    checkpoint_path: str = ""  # Checkpoint/adapter path
    quantization: str = "none"  # none, fp8, int8, int4, gguf_q4, gguf_q8
    preferred_engine: str = ""  # Override engine for this model (e.g., "vllm")
    provider: str = ""  # local, openai, anthropic, google
    # Generation defaults (overridable per-call)
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.9
    top_k: int = 40
    repetition_penalty: float = 1.0
    stop_sequences: str = ""  # Comma-separated stop strings


@dataclass(slots=True)
class DeepResearchConfig:
    """Planner settings for the web Deep Research endpoint."""

    engine: str = ""  # Empty means use the active chat engine.
    model: str = ""  # Empty means use the active chat model.


@dataclass(slots=True)
class RoutingLearningConfig:
    """Routing sub-policy config within Learning."""

    policy: str = "heuristic"  # heuristic | learned
    min_samples: int = 5  # Min traces before trusting learned routing


@dataclass(slots=True)
class SFTConfig:
    """General-purpose SFT training config. Maps to [learning.intelligence.sft]."""

    model_name: str = "Qwen/Qwen3-1.7B"
    max_seq_length: int = 4096
    num_epochs: int = 3
    batch_size: int = 8
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    max_grad_norm: float = 1.0
    gradient_checkpointing: bool = True
    use_lora: bool = True
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: str = "q_proj,v_proj"  # comma-separated for TOML compat
    use_4bit: bool = False
    checkpoint_dir: str = "checkpoints/sft"
    min_pairs: int = 10
    agent_filter: str = ""


@dataclass(slots=True)
class GRPOConfig:
    """General-purpose GRPO training config. Maps to [learning.intelligence.grpo]."""

    model_name: str = "Qwen/Qwen3-1.7B"
    max_seq_length: int = 4096
    max_response_length: int = 2048
    num_epochs: int = 10
    batch_size: int = 16
    learning_rate: float = 1e-6
    max_grad_norm: float = 1.0
    gradient_checkpointing: bool = True
    num_samples_per_prompt: int = 8
    temperature: float = 1.0
    kl_coef: float = 0.0001
    clip_ratio: float = 0.2
    use_8bit_ref: bool = True
    checkpoint_dir: str = "checkpoints/grpo"
    save_every_n_epochs: int = 1
    keep_last_n: int = 3
    min_prompts: int = 10
    agent_filter: str = ""


@dataclass(slots=True)
class DSPyOptimizerConfig:
    """DSPy agent optimizer config. Maps to [learning.agent.dspy]."""

    optimizer: str = "BootstrapFewShotWithRandomSearch"
    task_lm: str = ""
    teacher_lm: str = ""
    max_bootstrapped_demos: int = 4
    max_labeled_demos: int = 4
    num_candidate_programs: int = 10
    max_rounds: int = 1
    optimize_system_prompt: bool = True
    optimize_few_shot: bool = True
    optimize_tool_descriptions: bool = True
    min_traces: int = 20
    metric_threshold: float = 0.7
    agent_filter: str = ""
    config_dir: str = ""


@dataclass(slots=True)
class GEPAOptimizerConfig:
    """GEPA agent optimizer config. Maps to [learning.agent.gepa]."""

    reflection_lm: str = ""
    max_metric_calls: int = 150
    population_size: int = 10
    optimize_system_prompt: bool = True
    optimize_tools: bool = True
    optimize_max_turns: bool = True
    optimize_temperature: bool = True
    min_traces: int = 20
    assessment_batch_size: int = 10
    agent_filter: str = ""
    config_dir: str = ""


@dataclass(slots=True)
class ACEOptimizerConfig:
    """ACE agent optimizer config. Maps to ``[learning.agent.ace]``.

    ACE (Agentic Context Engineering) evolves a *playbook* — annotated
    natural-language strategies that get prepended to the agent's
    context — using a Generator / Reflector / Curator triad. Unlike
    DSPy (few-shot bootstrapping) or GEPA (Pareto-evolutionary prompt
    mutation), ACE writes a textual playbook that the agent reads at
    inference time.

    See https://github.com/ace-agent/ace for the upstream reference.
    Install via ``pip install -e openjarvis[learning-ace]`` once the
    optional dep is available (ACE is not on PyPI as of v1.0.1; the
    extra installs from the upstream git repo).
    """

    # Models for ACE's three roles. Empty string = inherit from the
    # intelligence primitive's default cloud model.
    generator_model: str = ""
    reflector_model: str = ""
    curator_model: str = ""

    # Provider passed to ACE (``sambanova`` | ``together`` | ``openai``
    # | ``commonstack``). We default to ``openai`` since that's what
    # most OpenJarvis users have credentials for.
    api_provider: str = "openai"

    # Run parameters. Defaults mirror ACE's offline-mode quickstart.
    num_epochs: int = 1
    max_num_rounds: int = 3
    eval_steps: int = 100
    playbook_token_budget: int = 80_000
    max_tokens: int = 4_096

    # Where ACE writes intermediate playbooks + final_results.json.
    # Empty string defaults to ``~/.openjarvis/learning/ace/<task>/``.
    save_dir: str = ""
    task_name: str = "openjarvis"

    # Standard filter / threshold knobs shared with DSPy / GEPA.
    min_traces: int = 20
    agent_filter: str = ""
    config_dir: str = ""


@dataclass(slots=True)
class IntelligenceLearningConfig:
    """Intelligence sub-policy config within Learning."""

    policy: str = "none"  # none | sft | grpo
    sft: SFTConfig = field(default_factory=SFTConfig)
    grpo: GRPOConfig = field(default_factory=GRPOConfig)


@dataclass(slots=True)
class AgentLearningConfig:
    """Agent sub-policy config within Learning."""

    policy: str = "none"  # none | dspy | gepa | ace
    dspy: DSPyOptimizerConfig = field(default_factory=DSPyOptimizerConfig)
    gepa: GEPAOptimizerConfig = field(default_factory=GEPAOptimizerConfig)
    ace: ACEOptimizerConfig = field(default_factory=ACEOptimizerConfig)


@dataclass(slots=True)
class SkillsLearningConfig:
    """Configuration for the skills learning loop (Plan 2A)."""

    auto_optimize: bool = False  # opt in via config
    optimizer: str = "dspy"  # "dspy" or "gepa"
    min_traces_per_skill: int = 20
    optimization_interval_seconds: int = 86400
    overlay_dir: str = field(
        default_factory=lambda: str(get_config_dir() / "learning" / "skills")
    )


@dataclass(slots=True)
class MetricsConfig:
    """Reward / optimization metric weights."""

    accuracy_weight: float = 0.6
    latency_weight: float = 0.2
    cost_weight: float = 0.1
    efficiency_weight: float = 0.1


@dataclass(slots=True)
class SpecSearchCompositeRewardConfig:
    """Composite reward weights for Intelligence-edit training (paper Eq. 1).

    R(q, y) = alpha * R_acc - beta * E_hat - gamma * L_hat - delta * C_hat
    """

    alpha: float = 0.5
    beta: float = 0.1
    gamma: float = 0.1
    delta: float = 0.3


@dataclass(slots=True)
class SpecSearchLearningConfig:
    """LLM-guided spec search config (paper §3.3, Algorithm 1).

    Maps to ``[learning.spec_search]`` and is consumed by
    ``SpecSearchOrchestrator.from_config`` and ``SpecSearchLoop``.
    """

    enabled: bool = False
    teacher_model: str = "claude-opus-4-6"
    teacher_engine: str = "cloud"  # registry key for the cloud engine
    autonomy_mode: str = "tiered"  # auto | tiered | manual

    # Per-session bounds (one diagnose/plan/execute pass)
    min_traces: int = 20
    max_cost_per_session_usd: float = 5.0
    max_tool_calls_per_diagnosis: int = 30

    # Multi-session loop (paper Algorithm 1)
    stagnation_k: int = 5
    max_total_cost_usd: float = 50.0
    stagnation_eps: float = 0.001  # gate-score delta below this counts as no progress

    # Gate (GateOK predicate)
    max_regression: float = 0.01  # paper default: epsilon = 1%
    min_improvement: float = 0.0
    benchmark_subsample_size: int = 50
    benchmark_version: str = "personal_v1"

    # Composite reward (only used when an Intelligence edit triggers training)
    composite_reward: SpecSearchCompositeRewardConfig = field(
        default_factory=SpecSearchCompositeRewardConfig,
    )


@dataclass
class LearningConfig:
    """Learning system settings with per-primitive sub-policies."""

    enabled: bool = False
    update_interval: int = 100
    auto_update: bool = False
    routing: RoutingLearningConfig = field(default_factory=RoutingLearningConfig)
    intelligence: IntelligenceLearningConfig = field(
        default_factory=IntelligenceLearningConfig,
    )
    agent: AgentLearningConfig = field(default_factory=AgentLearningConfig)
    skills: SkillsLearningConfig = field(default_factory=SkillsLearningConfig)
    spec_search: SpecSearchLearningConfig = field(
        default_factory=SpecSearchLearningConfig,
    )
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    # Training pipeline
    training_enabled: bool = False
    training_schedule: str = ""
    min_improvement: float = 0.02

    # Backward-compat properties for old flat field names
    @property
    def default_policy(self) -> str:
        """Deprecated: use ``learning.routing.policy``."""
        return self.routing.policy

    @default_policy.setter
    def default_policy(self, value: str) -> None:
        self.routing.policy = value

    @property
    def intelligence_policy(self) -> str:
        """Deprecated: use ``learning.intelligence.policy``."""
        return self.intelligence.policy

    @intelligence_policy.setter
    def intelligence_policy(self, value: str) -> None:
        self.intelligence.policy = value

    @property
    def agent_policy(self) -> str:
        """Deprecated: use ``learning.agent.policy``."""
        return self.agent.policy

    @agent_policy.setter
    def agent_policy(self, value: str) -> None:
        self.agent.policy = value

    @property
    def reward_weights(self) -> str:
        """Deprecated: use ``learning.metrics.*``."""
        parts = []
        m = self.metrics
        if m.latency_weight:
            parts.append(f"latency={m.latency_weight}")
        if m.cost_weight:
            parts.append(f"cost={m.cost_weight}")
        if m.efficiency_weight:
            parts.append(f"efficiency={m.efficiency_weight}")
        if m.accuracy_weight:
            parts.append(f"accuracy={m.accuracy_weight}")
        return ",".join(parts)

    @reward_weights.setter
    def reward_weights(self, value: str) -> None:
        if not value:
            return
        for part in value.split(","):
            if "=" not in part:
                continue
            key, val = part.strip().split("=", 1)
            key = key.strip()
            fval = float(val.strip())
            if key == "accuracy":
                self.metrics.accuracy_weight = fval
            elif key == "latency":
                self.metrics.latency_weight = fval
            elif key == "cost":
                self.metrics.cost_weight = fval
            elif key == "efficiency":
                self.metrics.efficiency_weight = fval

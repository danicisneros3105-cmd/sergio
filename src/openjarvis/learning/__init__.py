"""Learning primitive -- router policies, reward functions, learning."""

from __future__ import annotations

import logging as _logging

from openjarvis.learning._stubs import (
    QueryAnalyzer,
    RewardFunction,
    RouterPolicy,
    RoutingContext,
)
from openjarvis.learning.agents.agent_evolver import AgentConfigEvolver
from openjarvis.learning.learning_orchestrator import LearningOrchestrator
from openjarvis.learning.optimize.llm_optimizer import LLMOptimizer
from openjarvis.learning.optimize.optimizer import OptimizationEngine
from openjarvis.learning.optimize.store import OptimizationStore
from openjarvis.learning.routing.complexity import (
    ComplexityQueryAnalyzer,
    score_complexity,
)
from openjarvis.learning.routing.heuristic_reward import HeuristicRewardFunction
from openjarvis.learning.routing.router import (
    HeuristicRouter,
    build_routing_context,
)
from openjarvis.learning.training.data import TrainingDataMiner
from openjarvis.learning.training.lora import HAS_TORCH, LoRATrainer, LoRATrainingConfig


def ensure_registered() -> None:
    """Ensure all learning policies are registered in RouterPolicyRegistry."""
    from openjarvis.learning.routing.heuristic_policy import (
        ensure_registered as _reg_heuristic,
    )

    _reg_heuristic()

    from openjarvis.learning.routing.learned_router import (
        ensure_registered as _reg_learned,
    )

    _reg_learned()

    # Intelligence training (optional deps)
    try:
        import openjarvis.learning.intelligence  # noqa: F401
    except ImportError as _exc:
        _logging.getLogger(__name__).debug(
            "Optional import skipped (openjarvis.learning.intelligence): %s", _exc
        )

    # Orchestrator-specific training (optional deps)
    try:
        import openjarvis.learning.intelligence.orchestrator  # noqa: F401
    except ImportError as _exc:
        _logging.getLogger(__name__).debug(
            "Optional import skipped (openjarvis.learning.intelligence.orchestrator): %s",
            _exc,
        )

    # Agent optimizers (optional deps)
    try:
        import openjarvis.learning.agents.dspy_optimizer  # noqa: F401
    except ImportError as _exc:
        _logging.getLogger(__name__).debug(
            "Optional import skipped (openjarvis.learning.agents.dspy_optimizer): %s",
            _exc,
        )
    try:
        import openjarvis.learning.agents.gepa_optimizer  # noqa: F401
    except ImportError as _exc:
        _logging.getLogger(__name__).debug(
            "Optional import skipped (openjarvis.learning.agents.gepa_optimizer): %s",
            _exc,
        )
    try:
        import openjarvis.learning.agents.ace_optimizer  # noqa: F401
    except ImportError as _exc:
        _logging.getLogger(__name__).debug(
            "Optional import skipped (openjarvis.learning.agents.ace_optimizer): %s",
            _exc,
        )


__all__ = [
    "AgentConfigEvolver",
    "ComplexityQueryAnalyzer",
    "HAS_TORCH",
    "HeuristicRewardFunction",
    "HeuristicRouter",
    "LLMOptimizer",
    "LearningOrchestrator",
    "LoRATrainer",
    "LoRATrainingConfig",
    "OptimizationEngine",
    "OptimizationStore",
    "QueryAnalyzer",
    "RewardFunction",
    "RouterPolicy",
    "RoutingContext",
    "TrainingDataMiner",
    "build_routing_context",
    "ensure_registered",
    "score_complexity",
]

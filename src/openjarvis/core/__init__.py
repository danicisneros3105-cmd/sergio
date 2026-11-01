"""Core module — registries, types, configuration, event bus, and AGI reasoning engine."""

from __future__ import annotations

from openjarvis.core.agi_engine import (
    MetacognitiveMemory,
    MissionDossier,
    MissionPhase,
    TacticalStep,
    UniversalAGIEngine,
    get_universal_agi_engine,
)
from openjarvis.core.agi_reasoning import (
    AutonomousExecutionOrchestrator,
    HierarchicalTaskNetwork,
    MonteCarloTreeSearch,
    ReasoningGraph,
    ReasoningNode,
    SubsecondReasoningPlanner,
    TacticalAction,
    TacticalDomain,
    get_agi_reasoning_orchestrator,
)
from openjarvis.core.dynamic_api_synthesis import (
    DynamicAPISynthesizer,
    ResilientDeepScraper,
    StealthAntiBotEvasion,
    StealthBrowserFingerprint,
    get_dynamic_api_synthesizer,
)
from openjarvis.core.registry import (
    AgentRegistry,
    EngineRegistry,
    MemoryRegistry,
    ModelRegistry,
    ToolRegistry,
)
from openjarvis.core.types import (
    Conversation,
    Message,
    ModelSpec,
    Quantization,
    Role,
    TelemetryRecord,
    ToolCall,
    ToolResult,
)
from openjarvis.core.utils import (
    get_python_executable,
    open_browser,
    process_alive,
    terminate_process,
)

__all__ = [
    "MetacognitiveMemory",
    "MissionDossier",
    "MissionPhase",
    "TacticalStep",
    "UniversalAGIEngine",
    "get_universal_agi_engine",
    "AutonomousExecutionOrchestrator",
    "HierarchicalTaskNetwork",
    "MonteCarloTreeSearch",
    "ReasoningGraph",
    "ReasoningNode",
    "SubsecondReasoningPlanner",
    "TacticalAction",
    "TacticalDomain",
    "get_agi_reasoning_orchestrator",
    "DynamicAPISynthesizer",
    "ResilientDeepScraper",
    "StealthAntiBotEvasion",
    "StealthBrowserFingerprint",
    "get_dynamic_api_synthesizer",
    "AgentRegistry",
    "Conversation",
    "EngineRegistry",
    "MemoryRegistry",
    "Message",
    "ModelRegistry",
    "ModelSpec",
    "Quantization",
    "Role",
    "TelemetryRecord",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
    "get_python_executable",
    "open_browser",
    "process_alive",
    "terminate_process",
]

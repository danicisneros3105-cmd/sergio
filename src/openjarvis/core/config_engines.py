"""Per-engine configuration dataclasses (Ollama, vLLM, llama.cpp, MLX, cloud
…) and the ``[engine]`` section that holds them. Split out of ``config.py``,
which re-exports every name.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OllamaEngineConfig:
    """Per-engine config for Ollama."""

    host: str = ""


@dataclass(slots=True)
class VLLMEngineConfig:
    """Per-engine config for vLLM."""

    host: str = "http://localhost:8000"


@dataclass(slots=True)
class SGLangEngineConfig:
    """Per-engine config for SGLang."""

    host: str = "http://localhost:30000"


@dataclass(slots=True)
class LlamaCppEngineConfig:
    """Per-engine config for llama.cpp."""

    host: str = "http://localhost:8080"
    binary_path: str = ""


@dataclass(slots=True)
class MLXEngineConfig:
    """Per-engine config for MLX."""

    host: str = "http://localhost:8080"


@dataclass(slots=True)
class LMStudioEngineConfig:
    """Per-engine config for LM Studio."""

    host: str = "http://localhost:1234"


@dataclass(slots=True)
class ExoEngineConfig:
    """Per-engine config for Exo."""

    host: str = "http://localhost:52415"


@dataclass(slots=True)
class NexaEngineConfig:
    """Per-engine config for Nexa."""

    host: str = "http://localhost:18181"
    device: str = ""


@dataclass(slots=True)
class UzuEngineConfig:
    """Per-engine config for Uzu."""

    host: str = "http://localhost:8000"


@dataclass(slots=True)
class AppleFmEngineConfig:
    """Per-engine config for Apple Foundation Models."""

    host: str = "http://localhost:8079"


@dataclass(slots=True)
class GemmaCppEngineConfig:
    """Per-engine config for gemma.cpp."""

    model_path: str = ""
    tokenizer_path: str = ""
    model_type: str = ""
    num_threads: int = 0


@dataclass(slots=True)
class AfmEngineConfig:
    """Per-engine config for in-process Apple Foundation Models.

    No ``host``: this engine runs the SDK in-process rather than talking to a
    server. (The separate ``apple_fm`` engine does have a host — it speaks to
    the FastAPI shim.)
    """

    # Standing instructions applied to every session, on top of any system
    # message in the request.
    instructions: str = ""
    # "general" or "content_tagging".
    use_case: str = "general"
    # "default" or "permissive_content_transformations".
    guardrails: str = "default"
    # "greedy" (reproducible, the default here) or "random" (the SDK default).
    sampling: str = "greedy"


@dataclass(slots=True)
class LemonadeEngineConfig:
    """Per-engine config for Lemonade."""

    host: str = "http://localhost:13305"


@dataclass
class EngineConfig:
    """Inference engine settings with nested per-engine configs."""

    default: str = "ollama"
    ollama: OllamaEngineConfig = field(default_factory=OllamaEngineConfig)
    vllm: VLLMEngineConfig = field(default_factory=VLLMEngineConfig)
    sglang: SGLangEngineConfig = field(default_factory=SGLangEngineConfig)
    llamacpp: LlamaCppEngineConfig = field(default_factory=LlamaCppEngineConfig)
    mlx: MLXEngineConfig = field(default_factory=MLXEngineConfig)
    lmstudio: LMStudioEngineConfig = field(default_factory=LMStudioEngineConfig)
    exo: ExoEngineConfig = field(default_factory=ExoEngineConfig)
    nexa: NexaEngineConfig = field(default_factory=NexaEngineConfig)
    uzu: UzuEngineConfig = field(default_factory=UzuEngineConfig)
    apple_fm: AppleFmEngineConfig = field(default_factory=AppleFmEngineConfig)
    afm: AfmEngineConfig = field(default_factory=AfmEngineConfig)
    gemma_cpp: GemmaCppEngineConfig = field(default_factory=GemmaCppEngineConfig)
    lemonade: LemonadeEngineConfig = field(default_factory=LemonadeEngineConfig)

    # Backward-compat properties for old flat attribute names
    @property
    def ollama_host(self) -> str:
        """Deprecated: use ``engine.ollama.host``."""
        return self.ollama.host

    @ollama_host.setter
    def ollama_host(self, value: str) -> None:
        self.ollama.host = value

    @property
    def vllm_host(self) -> str:
        """Deprecated: use ``engine.vllm.host``."""
        return self.vllm.host

    @vllm_host.setter
    def vllm_host(self, value: str) -> None:
        self.vllm.host = value

    @property
    def llamacpp_host(self) -> str:
        """Deprecated: use ``engine.llamacpp.host``."""
        return self.llamacpp.host

    @llamacpp_host.setter
    def llamacpp_host(self, value: str) -> None:
        self.llamacpp.host = value

    @property
    def llamacpp_path(self) -> str:
        """Deprecated: use ``engine.llamacpp.binary_path``."""
        return self.llamacpp.binary_path

    @llamacpp_path.setter
    def llamacpp_path(self, value: str) -> None:
        self.llamacpp.binary_path = value

    @property
    def sglang_host(self) -> str:
        """Deprecated: use ``engine.sglang.host``."""
        return self.sglang.host

    @sglang_host.setter
    def sglang_host(self, value: str) -> None:
        self.sglang.host = value

    @property
    def mlx_host(self) -> str:
        """Deprecated: use ``engine.mlx.host``."""
        return self.mlx.host

    @mlx_host.setter
    def mlx_host(self, value: str) -> None:
        self.mlx.host = value

    @property
    def lmstudio_host(self) -> str:
        """Deprecated: use ``engine.lmstudio.host``."""
        return self.lmstudio.host

    @lmstudio_host.setter
    def lmstudio_host(self, value: str) -> None:
        self.lmstudio.host = value

    @property
    def exo_host(self) -> str:
        """Deprecated: use ``engine.exo.host``."""
        return self.exo.host

    @exo_host.setter
    def exo_host(self, value: str) -> None:
        self.exo.host = value

    @property
    def nexa_host(self) -> str:
        """Deprecated: use ``engine.nexa.host``."""
        return self.nexa.host

    @nexa_host.setter
    def nexa_host(self, value: str) -> None:
        self.nexa.host = value

    @property
    def uzu_host(self) -> str:
        """Deprecated: use ``engine.uzu.host``."""
        return self.uzu.host

    @uzu_host.setter
    def uzu_host(self, value: str) -> None:
        self.uzu.host = value

    @property
    def apple_fm_host(self) -> str:
        """Deprecated: use ``engine.apple_fm.host``."""
        return self.apple_fm.host

    @apple_fm_host.setter
    def apple_fm_host(self, value: str) -> None:
        self.apple_fm.host = value

    @property
    def lemonade_host(self) -> str:
        """Deprecated: use ``engine.lemonade.host``."""
        return self.lemonade.host

    @lemonade_host.setter
    def lemonade_host(self, value: str) -> None:
        self.lemonade.host = value


__all__ = [
    "AfmEngineConfig",
    "AppleFmEngineConfig",
    "EngineConfig",
    "ExoEngineConfig",
    "GemmaCppEngineConfig",
    "LemonadeEngineConfig",
    "LlamaCppEngineConfig",
    "LMStudioEngineConfig",
    "MLXEngineConfig",
    "NexaEngineConfig",
    "OllamaEngineConfig",
    "SGLangEngineConfig",
    "UzuEngineConfig",
    "VLLMEngineConfig",
]

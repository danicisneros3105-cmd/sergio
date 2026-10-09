"""Hardware detection (GPU, CPU, RAM) and the engine/model recommendation
built on it.

Split out of ``config.py``; its names are looked up on that module at call
time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Optional

import openjarvis.core.config as _cfg


def _run_cmd(cmd: list[str]) -> str:
    """Run a command and return stripped stdout, or empty string on failure."""
    try:
        result = _cfg.subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,  # noqa: S603
        )
        return result.stdout.strip()
    except (FileNotFoundError, _cfg.subprocess.TimeoutExpired, OSError):
        return ""


def _detect_nvidia_gpu() -> Optional[_cfg.GpuInfo]:
    if not _cfg.shutil.which("nvidia-smi"):
        return None
    raw = _cfg._run_cmd(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,count,compute_cap",
            "--format=csv,noheader,nounits",
        ]
    )
    if not raw:
        return None
    try:
        first_line = raw.splitlines()[0]
        parts = [p.strip() for p in first_line.split(",")]
        name = parts[0]
        vram_mb = float(parts[1])
        count = int(parts[2])
        compute_capability = parts[3] if len(parts) > 3 else ""
        return _cfg.GpuInfo(
            vendor="nvidia",
            name=name,
            vram_gb=round(vram_mb / 1024, 1),
            compute_capability=compute_capability,
            count=count,
        )
    except (IndexError, ValueError):
        return None


def _detect_amd_gpu() -> Optional[_cfg.GpuInfo]:
    if not _cfg.shutil.which("rocm-smi"):
        return None
    raw = _cfg._run_cmd(["rocm-smi", "--showproductname"])
    if not raw:
        return None
    name = raw.splitlines()[0] if raw else "AMD GPU"

    # Parse VRAM from rocm-smi --showmeminfo vram
    vram_gb = 0.0
    try:
        vram_raw = _cfg._run_cmd(["rocm-smi", "--showmeminfo", "vram"])
        for line in vram_raw.splitlines():
            if "Total Memory (B):" in line:
                vram_bytes = int(line.split(":")[-1].strip())
                vram_gb = round(vram_bytes / (1024**3), 1)
                break
    except (ValueError, IndexError):
        vram_gb = 0.0

    # Parse GPU count from rocm-smi --showallinfo
    count = 1
    try:
        allinfo_raw = _cfg._run_cmd(["rocm-smi", "--showallinfo"])
        import re

        gpu_ids = set(re.findall(r"GPU\[(\d+)\]", allinfo_raw))
        if gpu_ids:
            count = len(gpu_ids)
    except (ValueError, IndexError):
        count = 1

    return _cfg.GpuInfo(vendor="amd", name=name, vram_gb=vram_gb, count=count)


def _detect_apple_gpu() -> Optional[_cfg.GpuInfo]:
    if _cfg.platform.system() != "Darwin":
        return None
    raw = _cfg._run_cmd(["system_profiler", "SPDisplaysDataType"])
    if "Apple" not in raw:
        return None
    # Rough extraction — "Apple M2 Max" etc.
    ram_gb = _cfg._total_ram_gb()
    for line in raw.splitlines():
        line = line.strip()
        if "Chipset Model" in line:
            name = line.split(":")[-1].strip()
            return _cfg.GpuInfo(vendor="apple", name=name, vram_gb=ram_gb, count=1)
    return _cfg.GpuInfo(vendor="apple", name="Apple Silicon", vram_gb=ram_gb, count=1)


def _detect_cpu_brand() -> str:
    """Best-effort CPU brand string."""
    if _cfg.platform.system() == "Darwin":
        brand = _cfg._run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"])
        if brand:
            return brand
    cpuinfo = _cfg.Path("/proc/cpuinfo")
    if cpuinfo.exists():
        try:
            for line in cpuinfo.read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return _cfg.platform.processor() or "unknown"


def _total_ram_gb() -> float:
    try:
        if _cfg.platform.system() == "Darwin":
            raw = _cfg._run_cmd(["sysctl", "-n", "hw.memsize"])
            return round(int(raw) / (1024**3), 1) if raw else 0.0
        if _cfg.platform.system() == "Windows":
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024**3), 1)
            return 0.0
        meminfo = _cfg.Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text().splitlines():
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    return round(kb / (1024**2), 1)
    except (OSError, ValueError, AttributeError):
        pass
    return 0.0


def detect_hardware() -> _cfg.HardwareInfo:
    """Auto-detect hardware capabilities with graceful fallbacks."""
    gpu = (
        _cfg._detect_nvidia_gpu() or _cfg._detect_amd_gpu() or _cfg._detect_apple_gpu()
    )
    return _cfg.HardwareInfo(
        platform=_cfg.platform.system().lower(),
        cpu_brand=_cfg._detect_cpu_brand(),
        cpu_count=_cfg.os.cpu_count() or 1,
        ram_gb=_cfg._total_ram_gb(),
        gpu=gpu,
    )


def recommend_engine(hw: _cfg.HardwareInfo) -> str:
    """Suggest the best inference engine for the detected hardware."""
    gpu = hw.gpu
    if gpu is None:
        return "llamacpp"
    if gpu.vendor == "apple":
        return "mlx"
    if gpu.vendor == "nvidia":
        # Datacenter cards (A100, H100, L40, etc.) → vllm; consumer → ollama
        datacenter_keywords = ("A100", "H100", "H200", "L40", "A10", "A30")
        if any(kw in gpu.name for kw in datacenter_keywords):
            return "vllm"
        return "ollama"
    if gpu.vendor == "amd":
        # Datacenter cards (MI300, MI325, MI350, MI355) → vllm; consumer → lemonade
        amd_datacenter_keywords = ("MI300", "MI325", "MI350", "MI355")
        if any(kw in gpu.name for kw in amd_datacenter_keywords):
            return "vllm"
        return "lemonade"
    return "llamacpp"


def _available_memory_gb(hw: _cfg.HardwareInfo) -> float:
    """Return usable memory in GB for model loading."""
    gpu = hw.gpu
    if gpu and gpu.vram_gb > 0:
        return gpu.vram_gb * max(gpu.count, 1) * 0.9
    if hw.ram_gb > 0:
        return (hw.ram_gb - 4) * 0.8
    return 0.0


def recommend_model(hw: _cfg.HardwareInfo, engine: str) -> str:
    """Suggest a default model for the selected engine and hardware.

    For Lemonade, prefer the validated Qwen3.6 35B A3B GGUF default.
    For other local engines, use the generic Qwen3.5 tier mapping.
    """
    from openjarvis.intelligence.model_catalog import BUILTIN_MODELS

    available_gb = _cfg._available_memory_gb(hw)
    if available_gb <= 0:
        return ""

    if engine == "lemonade":
        return _cfg._LEMONADE_DEFAULT_MODEL

    # Build a lookup for quick engine-compatibility checks
    catalog = {spec.model_id: spec for spec in BUILTIN_MODELS}

    # Try explicit tier mapping first
    model_id = _cfg._MODEL_TIER_FALLBACK
    for max_ram, tier_model in _cfg._MODEL_TIERS:
        if available_gb <= max_ram:
            model_id = tier_model
            break

    spec = catalog.get(model_id)
    if spec and engine in spec.supported_engines:
        return model_id

    # Fallback: scan all Qwen3.5 models for engine compatibility
    candidates = [
        s
        for s in BUILTIN_MODELS
        if s.provider == "alibaba"
        and s.model_id.startswith("qwen3.5:")
        and engine in s.supported_engines
    ]
    candidates.sort(key=lambda s: s.parameter_count_b, reverse=True)
    for s in candidates:
        estimated_gb = s.parameter_count_b * 0.5 * 1.1
        if estimated_gb <= available_gb:
            return s.model_id

    return ""


def estimated_download_gb(parameter_count_b: float) -> float:
    """Estimate download size in GB for Q4_K_M quantized model."""
    return parameter_count_b * 0.5 * 1.1


__all__ = [
    "_run_cmd",
    "_detect_nvidia_gpu",
    "_detect_amd_gpu",
    "_detect_apple_gpu",
    "_detect_cpu_brand",
    "_total_ram_gb",
    "detect_hardware",
    "recommend_engine",
    "_available_memory_gb",
    "recommend_model",
    "estimated_download_gb",
]

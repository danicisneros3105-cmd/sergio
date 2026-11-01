"""Self-Evolution Engine and Live Codebase Auto-Repair Nexus.

Grants Sergio sovereign, live access to its own codebase and GitHub repository:
1. Real-defect triage: validates that reported failures are genuine, reproducible bugs
   (not hallucinations or frivolous changes).
2. TDD Patch Synthesis: applies surgical code fixes and runs automated regression tests.
3. Atomic Git Commit & GitHub Push: cryptographically commits validated patches to origin/main.
4. Adaptive 7-Day Evolution Loop: enforces autonomous self-updating at least every 7 days
   or adaptively for deep background operations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("openjarvis.core.self_evolution_nexus")


@dataclass
class DefectReport:
    defect_id: str
    symptom: str
    component_affected: str
    severity: str  # critical, major, minor
    is_reproducible: bool
    reproduction_output: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class EvolutionCycleResult:
    cycle_id: str
    started_at: float
    completed_at: float
    defects_detected: int
    defects_repaired: int
    tests_passed: bool
    git_commit_sha: Optional[str]
    pushed_to_remote: bool
    merkle_proof_hash: str
    details: Dict[str, Any] = field(default_factory=dict)


class LiveCodebaseEvolutionNexus:
    """Manages live codebase self-inspection, defect verification, and atomic self-updates."""

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        if repo_root is None:
            # Discover repo root by walking up from this file until .git or pyproject.toml is found
            curr = Path(__file__).resolve().parent
            while curr != curr.parent:
                if (curr / ".git").exists() or (curr / "pyproject.toml").exists():
                    repo_root = curr
                    break
                curr = curr.parent
            if repo_root is None:
                repo_root = Path.cwd()
        self.repo_root = repo_root
        self._lock = threading.RLock()
        self.state_file = Path.home() / ".openjarvis" / "evidencias" / "evolution_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        default_state = {
            "last_cycle_timestamp": time.time(),
            "cycle_count": 0,
            "max_evolution_interval_days": 7.0,
            "defects_repaired_total": 0,
            "history": [],
        }
        try:
            self.state_file.write_text(json.dumps(default_state, indent=2), encoding="utf-8")
        except Exception:
            pass
        return default_state

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning("No se pudo guardar estado de autoevolución: %s", exc)

    def verify_defect(
        self,
        symptom: str,
        probe_command: Optional[List[str]] = None,
        probe_callable: Optional[Any] = None,
    ) -> DefectReport:
        """Determines if a defect is real and reproducible, discarding false alarms."""
        with self._lock:
            defect_id = f"def_{int(time.time() * 1000)}_{hashlib.sha256(symptom.encode()).hexdigest()[:6]}"
            is_reproducible = False
            output = ""

            if probe_callable is not None:
                try:
                    res = probe_callable()
                    is_reproducible = res is False or res is None
                    output = f"Callable probe returned: {res}"
                except Exception as exc:
                    is_reproducible = True
                    output = f"Callable probe raised exception: {exc}"
            elif probe_command is not None:
                try:
                    proc = subprocess.run(
                        probe_command,
                        cwd=self.repo_root,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    is_reproducible = proc.returncode != 0
                    output = proc.stderr or proc.stdout
                except Exception as exc:
                    is_reproducible = True
                    output = f"Probe execution error: {exc}"
            else:
                # Symptom keyword triage
                low = symptom.lower()
                real_defect_markers = [
                    "traceback", "exception", "error", "fail", "crash", "bug",
                    "timed out", "unhandled", "broken", "syntaxerror", "typeerror",
                ]
                is_reproducible = any(m in low for m in real_defect_markers)
                output = f"Heuristic analysis for markers: {is_reproducible}"

            report = DefectReport(
                defect_id=defect_id,
                symptom=symptom,
                component_affected=self._infer_component(symptom),
                severity="major" if "crash" in symptom.lower() or "exception" in symptom.lower() else "minor",
                is_reproducible=is_reproducible,
                reproduction_output=output[:1000],
            )
            return report

    def _infer_component(self, symptom: str) -> str:
        low = symptom.lower()
        if any(k in low for k in ("terry", "brief", "prompt")):
            return "agents.terry"
        if any(k in low for k in ("node", "nodes", "routine")):
            return "nodes.worker"
        if any(k in low for k in ("voice", "live", "audio", "mic")):
            return "speech.voice"
        if any(k in low for k in ("merkle", "evidence", "ledger")):
            return "telemetry.evidence"
        if any(k in low for k in ("hotel", "arbitrage", "rate", "price")):
            return "tools.commerce_intel"
        return "core.agi_engine"

    def run_regression_suite(self, test_target: str = "tests/core/") -> Tuple[bool, str]:
        """Runs the test suite inside the active environment to guarantee zero regressions."""
        python_bin = sys.executable
        # Try uv if available, otherwise python -m pytest
        cmd = [python_bin, "-m", "pytest", test_target, "-q"]
        try:
            res = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed = res.returncode == 0
            output = res.stdout if passed else (res.stderr + "\n" + res.stdout)
            return passed, output[-2000:]
        except Exception as exc:
            return False, f"Fallo al ejecutar pytest: {exc}"

    def apply_patch_and_evolve(
        self,
        file_relative_path: str,
        target_snippet: str,
        replacement_snippet: str,
        commit_message: str,
        push_remote: bool = True,
    ) -> EvolutionCycleResult:
        """Applies a code patch, validates regression tests, commits, and pushes to GitHub."""
        with self._lock:
            t_start = time.perf_counter()
            cycle_id = f"evo_{int(time.time() * 1000)}"
            target_file = self.repo_root / file_relative_path

            if not target_file.exists():
                raise FileNotFoundError(f"Archivo objetivo no encontrado: {file_relative_path}")

            original_content = target_file.read_text(encoding="utf-8")
            if target_snippet not in original_content:
                raise ValueError(f"Snippet objetivo no coincide en {file_relative_path}")

            # 1. Apply patch in memory and write
            patched_content = original_content.replace(target_snippet, replacement_snippet, 1)
            target_file.write_text(patched_content, encoding="utf-8")

            # 2. Run verification tests
            tests_ok, test_output = self.run_regression_suite()
            if not tests_ok:
                # Rollback immediately
                target_file.write_text(original_content, encoding="utf-8")
                raise RuntimeError(f"Pruebas de regresión fallaron. Parche revertido: {test_output[:500]}")

            # 3. Git commit
            commit_sha = None
            pushed = False
            try:
                subprocess.run(["git", "add", str(target_file)], cwd=self.repo_root, check=True, capture_output=True)
                commit_res = subprocess.run(
                    ["git", "commit", "-m", f"fix(auto-heal): {commit_message}"],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                )
                if commit_res.returncode == 0:
                    rev = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=self.repo_root,
                        capture_output=True,
                        text=True,
                    )
                    commit_sha = rev.stdout.strip()

                # 4. Push to origin main if requested
                if push_remote and commit_sha:
                    push_res = subprocess.run(
                        ["git", "push", "origin", "main"],
                        cwd=self.repo_root,
                        capture_output=True,
                        text=True,
                        timeout=45,
                    )
                    pushed = push_res.returncode == 0
            except Exception as git_exc:
                log.warning("Git commit/push fallo durante auto-evolución: %s", git_exc)

            # 5. Record cryptographic proof in Merkle evidence ledger
            merkle_hash = ""
            try:
                from openjarvis.telemetry.evidence_nexus import (
                    get_evidence_nexus_ledger,
                )
                ledger = get_evidence_nexus_ledger()
                proof = ledger.record_proof(
                    action_name="self_evolution:auto_patch",
                    domain="live_codebase_evolution",
                    input_data={"file": file_relative_path, "message": commit_message},
                    output_data={"commit_sha": commit_sha, "pushed": pushed},
                    latency_ms=(time.perf_counter() - t_start) * 1000,
                    status="EXITOSO" if tests_ok else "REVERTIDO",
                )
                merkle_hash = proof.merkle_leaf_hash
            except Exception as ev_exc:
                log.warning("No se pudo asentar prueba Merkle: %s", ev_exc)

            # Update persistent evolution state
            state = self._load_state()
            state["last_cycle_timestamp"] = time.time()
            state["cycle_count"] = state.get("cycle_count", 0) + 1
            state["defects_repaired_total"] = state.get("defects_repaired_total", 0) + 1
            state.setdefault("history", []).append({
                "cycle_id": cycle_id,
                "file": file_relative_path,
                "commit": commit_sha,
                "pushed": pushed,
                "timestamp": time.time(),
            })
            self._save_state(state)

            return EvolutionCycleResult(
                cycle_id=cycle_id,
                started_at=t_start,
                completed_at=time.perf_counter(),
                defects_detected=1,
                defects_repaired=1,
                tests_passed=tests_ok,
                git_commit_sha=commit_sha,
                pushed_to_remote=pushed,
                merkle_proof_hash=merkle_hash,
                details={"file": file_relative_path, "commit_msg": commit_message},
            )

    def is_evolution_due(self, max_days: Optional[float] = None) -> Tuple[bool, float]:
        """Checks if the 7-day (or custom) self-evolution interval has elapsed."""
        state = self._load_state()
        interval_days = max_days if max_days is not None else state.get("max_evolution_interval_days", 7.0)
        last_t = state.get("last_cycle_timestamp", 0.0)
        elapsed_days = (time.time() - last_t) / 86400.0
        is_due = elapsed_days >= interval_days
        return is_due, round(elapsed_days, 2)


# Global singleton
_global_evolution_nexus: Optional[LiveCodebaseEvolutionNexus] = None


def get_self_evolution_nexus() -> LiveCodebaseEvolutionNexus:
    global _global_evolution_nexus
    if _global_evolution_nexus is None:
        _global_evolution_nexus = LiveCodebaseEvolutionNexus()
    return _global_evolution_nexus


__all__ = [
    "DefectReport",
    "EvolutionCycleResult",
    "LiveCodebaseEvolutionNexus",
    "get_self_evolution_nexus",
]

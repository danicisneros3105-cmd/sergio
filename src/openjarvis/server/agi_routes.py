"""FastAPI routes for Universal AGI Operations and Cryptographic Merkle Evidence.

Exposes REST endpoints for:
- POST /v1/agi/solve: Autonomous end-to-end mission resolution.
- GET  /v1/agi/dossiers: Retrieve historical mission dossiers.
- GET  /v1/agi/evidence/ledger: Inspect Merkle ledger and cryptographic root.
- GET  /v1/agi/evidence/verify: Mathematically verify all Merkle inclusion proofs.
- GET  /v1/agi/evidence/receipt/{mission_id}: Export self-verifying audit receipts.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from openjarvis.core.agi_engine import get_universal_agi_engine
from openjarvis.telemetry.evidence_nexus import get_evidence_nexus_ledger

router = APIRouter(prefix="/v1/agi", tags=["agi"])


class AGISolveRequest(BaseModel):
    mission: str = Field(..., min_length=3, description="Objetivo o misión táctica para Sergio")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Contexto adicional")
    require_confirmation: bool = Field(default=True, description="Puerta de confirmación estricta Vertu")
    stealth: bool = Field(default=True, description="Activar evasión antibot sigilosa")


class AGISolveResponse(BaseModel):
    mission_id: str
    objective_classified: str
    target_entity: str
    budget_usd: Optional[float]
    deadline_hint: str
    vertu_seal_token: str
    success: bool
    dossier_path: str
    proactive_jarvis_brief: str
    final_outcome: Dict[str, Any]
    phases: List[Dict[str, Any]]


@router.post("/solve", response_model=AGISolveResponse)
async def solve_mission(request: AGISolveRequest) -> AGISolveResponse:
    """Ejecuta una misión logística/táctica autónoma con razonamiento AGI, evasión y sellado Vertu."""
    engine = get_universal_agi_engine()
    dossier = engine.solve(
        request.mission,
        context=request.context,
        require_confirmation=request.require_confirmation,
        stealth=request.stealth,
    )
    phases = [
        {
            "phase": s.phase.value if hasattr(s.phase, "value") else str(s.phase),
            "name": s.name,
            "description": s.description,
            "status": s.status,
            "latency_seconds": s.latency_seconds,
            "result": s.result,
        }
        for s in dossier.phases
    ]
    return AGISolveResponse(
        mission_id=dossier.mission_id,
        objective_classified=dossier.objective_classified,
        target_entity=dossier.target_entity,
        budget_usd=dossier.budget_usd,
        deadline_hint=dossier.deadline_hint,
        vertu_seal_token=dossier.vertu_seal_token,
        success=dossier.success,
        dossier_path=dossier.dossier_path,
        proactive_jarvis_brief=dossier.proactive_jarvis_brief,
        final_outcome=dossier.final_outcome,
        phases=phases,
    )


@router.get("/dossiers")
async def list_dossiers(limit: int = 20) -> List[Dict[str, Any]]:
    """Lista los expedientes tácticos generados recientemente."""
    engine = get_universal_agi_engine()
    dossier_dir = engine._dossiers_dir
    if not dossier_dir.exists():
        return []

    files = sorted(dossier_dir.glob("dossier_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for f in files[:limit]:
        try:
            results.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return results


@router.get("/evidence/ledger")
async def get_evidence_ledger() -> Dict[str, Any]:
    """Retorna el estado actual del libro mayor de evidencias y la raíz Merkle."""
    ledger = get_evidence_nexus_ledger()
    with ledger._lock:
        return {
            "version": "2.0_rfc6962_merkle_ledger",
            "total_entradas": len(ledger.entries),
            "merkle_root": (
                ledger.entries and get_evidence_nexus_ledger().verify_ledger_integrity().get("merkle_root") or ""
            ),
            "entradas_recientes": [asdict(e) for e in ledger.entries[-50:]],
        }


@router.get("/evidence/verify")
async def verify_evidence_integrity() -> Dict[str, Any]:
    """Verifica matemáticamente todas las pruebas de inclusión Merkle O(log N)."""
    ledger = get_evidence_nexus_ledger()
    return ledger.verify_ledger_integrity()


@router.get("/evidence/receipt/{mission_id}")
async def get_mission_receipt(mission_id: str) -> Dict[str, Any]:
    """Genera u obtiene el recibo de auditoría con prueba de inclusión para una misión específica."""
    ledger = get_evidence_nexus_ledger()
    receipt = ledger.generate_audit_receipt(mission_id)
    return receipt


@router.get("/evolve/status")
async def get_evolution_status() -> Dict[str, Any]:
    """Retorna el estado de la ventana de autoevolución adaptativa (máximo 7 días)."""
    from openjarvis.core.self_evolution_nexus import get_self_evolution_nexus

    nexus = get_self_evolution_nexus()
    is_due, elapsed = nexus.is_evolution_due()
    state = nexus._load_state()
    return {
        "ciclos_completados": state.get("cycle_count", 0),
        "dias_transcurridos": elapsed,
        "ventana_maxima_dias": state.get("max_evolution_interval_days", 7.0),
        "evolucion_requerida": is_due,
        "defectos_reparados_total": state.get("defects_repaired_total", 0),
    }


class SelfHealRequest(BaseModel):
    symptom: str = Field(..., min_length=3, description="Descripción del síntoma o fallo observado")


@router.post("/self-heal")
async def trigger_self_heal(body: SelfHealRequest) -> Dict[str, Any]:
    """Ejecuta triage de defecto y protocolo TDD de auto-reparación en vivo."""
    from openjarvis.core.self_evolution_nexus import get_self_evolution_nexus

    nexus = get_self_evolution_nexus()
    defect = nexus.verify_defect(body.symptom)
    return {
        "defect_id": defect.defect_id,
        "symptom": defect.symptom,
        "component": defect.component_affected,
        "is_reproducible": defect.is_reproducible,
        "severity": defect.severity,
        "reproduction_output": defect.reproduction_output,
    }


__all__ = [
    "AGISolveRequest",
    "AGISolveResponse",
    "SelfHealRequest",
    "get_evidence_ledger",
    "get_evolution_status",
    "get_mission_receipt",
    "list_dossiers",
    "router",
    "solve_mission",
    "trigger_self_heal",
    "verify_evidence_integrity",
]


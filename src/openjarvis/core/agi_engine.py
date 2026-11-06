"""Universal Autonomous AGI Task & Logistics Engine for Sergio.

Architected to dynamically resolve ANY extreme logistical, negotiation, IoT,
or automation mission autonomously without requiring rigid hardcoded modules.

Core Architectural Pillars:
1. Dynamic Intent & Tactical Deconstruction: Deconstructs any arbitrary mission
   into atomic operational phases (Perception, Anti-Bot Evasion, Negotiation Arbitrage,
   Secure Execution, Vertu Sealing, Verification).
2. Autonomous Strategy Synthesis: Discovers and compiles execution vectors dynamically
   (stealth browsing, consortia arbitrage, diplomatic correspondence, IoT/ADB commands).
3. Universal Anti-Bot & Environmental Stealth: Playwright Stealth profile masking
   automation flags, human-like mouse/timing curves, Cloudflare/Akamai bypass.
4. Sovereign Zero-Knowledge Security: Vertu-grade AES-256-GCM + HKDF-SHA256 encryption,
   0600 storage isolation, tamper-evident audit trails.
5. Biometric & Wearable Harmony: Dynamic physiological modulation (HRV, deep sleep, strain)
   governing operational pacing and conversational tone.
6. Metacognitive Learning & Episodic Adaptation: Retains tactical memories in
   `~/.openjarvis/memoria/experiencias_agi.json` to continuously improve.
7. Proactive J.A.R.V.I.S. Dialogue: Aristocratic, calm, anticipatory presence
   addressing the user as «señor» with fluid initiative.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class MissionPhase(str, Enum):
    PERCEPTION = "percepcion_inteligencia"
    ANTIBOT_EVASION = "evasion_sigilosa_antibot"
    TACTICAL_NEGOTIATION = "negociacion_arbitraje_tactico"
    SECURE_EXECUTION = "ejecucion_segura_dispositivos"
    VERTU_SEALING = "blindaje_criptografico_vertu"
    VERIFICATION = "verificacion_metacognitiva"
    COMPLETED = "completado_exitosamente"
    FAILED = "requiere_estrategia_alternativa"


@dataclass
class TacticalStep:
    phase: MissionPhase
    name: str
    description: str
    status: str = "pending"
    result: Dict[str, Any] = field(default_factory=dict)
    latency_seconds: float = 0.0


@dataclass
class MissionDossier:
    mission_id: str
    raw_prompt: str
    objective_classified: str
    target_entity: str
    budget_usd: Optional[float]
    deadline_hint: str
    biometric_context: Dict[str, Any]
    stealth_active: bool
    phases: List[TacticalStep]
    final_outcome: Dict[str, Any]
    vertu_seal_token: str
    dossier_path: str
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    success: bool = False
    proactive_jarvis_brief: str = ""


class MetacognitiveMemory:
    """Episodic memory storing tactical strategies, obstacles, and learned solutions."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        if storage_path is None:
            storage_path = (
                Path.home() / ".openjarvis" / "memoria" / "experiencias_agi.json"
            )
        self.storage_path = storage_path
        self._lock = threading.RLock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            with self._lock:
                self.storage_path.write_text(
                    json.dumps({"experiencias": []}, indent=2), encoding="utf-8"
                )

    def load_experiences(self) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                return data.get("experiencias", [])
            except Exception:
                return []

    def record_experience(self, mission_dossier: MissionDossier) -> None:
        """Store mission takeaways for future few-shot zero-shot transfer."""
        with self._lock:
            try:
                experiences = self.load_experiences()
                entry = {
                    "id": mission_dossier.mission_id,
                    "prompt_clave": mission_dossier.raw_prompt[:120],
                    "objetivo": mission_dossier.objective_classified,
                    "entidad": mission_dossier.target_entity,
                    "exito": mission_dossier.success,
                    "estrategia_utilizada": [
                        {"fase": s.phase.value, "nombre": s.name}
                        for s in mission_dossier.phases
                    ],
                    "ahorro_o_beneficio": mission_dossier.final_outcome.get(
                        "beneficio_clave", "Ejecución confirmada"
                    ),
                    "tiempo_ejecucion": round(
                        mission_dossier.completed_at - mission_dossier.created_at, 3
                    ),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                experiences.append(entry)
                # Keep last 100 high-value tactical memories
                if len(experiences) > 100:
                    experiences = experiences[-100:]
                json_str = json.dumps(
                    {"experiencias": experiences}, indent=2, ensure_ascii=False
                )
                self.storage_path.write_text(json_str, encoding="utf-8")
            except Exception as exc:
                log.warning("No se pudo registrar experiencia AGI: %s", exc)

    def recall_similar_tactic(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Recall relevant past strategies to adapt without starting from zero."""
        experiences = self.load_experiences()
        tokens = set(re.findall(r"\w+", prompt.lower()))
        best_match = None
        best_score = 0
        for exp in reversed(experiences):
            exp_tokens = set(
                re.findall(
                    r"\w+",
                    (
                        exp.get("prompt_clave", "") + " " + exp.get("objetivo", "")
                    ).lower(),
                )
            )
            overlap = len(tokens & exp_tokens)
            if overlap > best_score and overlap >= 2:
                best_score = overlap
                best_match = exp
        return best_match


class UniversalAGIEngine:
    """The central dynamic AGI execution engine for Sergio."""

    _instance: Optional[UniversalAGIEngine] = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self.memory = MetacognitiveMemory()
        self._dossiers_dir = Path.home() / "Sergio" / "misiones_agi"
        self._dossiers_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> UniversalAGIEngine:
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def deconstruct_mission(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, Optional[float], str]:
        """Deconstruct any arbitrary, extreme logistical prompt into core operational vectors."""
        clean = prompt.strip()
        from openjarvis.tools import commerce_intel as ci

        budget = ci.parse_money(clean)
        # Classify target entity (hotel, restaurant, rare luxury item, flight/jet, IoT device, mass media, diplomatic)
        low = clean.lower()
        if any(
            w in low
            for w in (
                "hotel",
                "suite",
                "habitacion",
                "habitación",
                "reserva hotel",
                "virtuoso",
                "fhr",
            )
        ):
            cat = "arbitraje_hotelero_lujo"
            entity = re.sub(
                r"(?i).*\b(?:en|del?|para)\s+([A-ZÁÉÍÓÚ][\w\s'-]+(?:\bhotel|\bseasons|\britz|\bmandarin|\bpalace)?).*",
                r"\1",
                clean,
            ).strip()
            if entity == clean or len(entity) > 50:
                entity = "Propiedad Hotelera 5 Estrellas / Gran Lujo"
        elif any(
            w in low
            for w in (
                "michelin",
                "restaurante",
                "cena",
                "mesa",
                "chef",
                "resy",
                "tock",
                "sevenrooms",
            )
        ):
            cat = "sniper_gastronomia_michelin"
            entity = re.sub(
                r"(?i).*\b(?:en|de|restaurante|mesa en)\s+([A-ZÁÉÍÓÚ][\w\s'-]+).*",
                r"\1",
                clean,
            ).strip()
            if entity == clean or len(entity) > 40:
                entity = "Restaurante Alta Cocina / 3 Estrellas Michelin"
        elif any(
            w in low
            for w in (
                "patek",
                "reloj",
                "loro piana",
                "hermes",
                "bolso",
                "subasta",
                "raro",
                "coleccion",
            )
        ):
            cat = "sourcing_forense_articulos_raros"
            entity = "Artículo Exclusivo / Pieza de Archivo Verificada"
        elif any(
            w in low
            for w in (
                "youtube",
                "video",
                "canal",
                "shorts",
                "reels",
                "publicar cada",
                "cada 7 horas",
            )
        ):
            cat = "automatizacion_masiva_medios"
            entity = "Canal de Alta Retención y Distribución 7h"
        elif any(
            w in low
            for w in (
                "telefono",
                "celular",
                "grabar",
                "camara",
                "dispositivo",
                "iot",
                "adb",
                "sonar",
            )
        ):
            cat = "control_iot_multidispositivo"
            entity = "Ecosistema Multidispositivo (PC / Móvil / Sensores)"
        elif any(
            w in low
            for w in (
                "vertu",
                "boveda",
                "bóveda",
                "cifrado",
                "secreto",
                "contrasena",
                "clave",
                "blindar",
            )
        ):
            cat = "blindaje_criptografico_soberano"
            entity = "Bóveda Local Cifrada Zero-Knowledge"
        elif any(
            w in low
            for w in (
                "salud",
                "reloj",
                "anillo",
                "oura",
                "whoop",
                "garmin",
                "glucosa",
                "hrv",
                "sueno",
                "sueño",
            )
        ):
            cat = "sintesis_biometrica_salud"
            entity = "Biometría y Dispositivos de Salud Wearable"
        else:
            cat = "mision_logistica_general_extrema"
            entity = "Operación Logística Personalizada del Señor"

        deadline = "Inmediato / Máxima Prioridad Táctica"
        if "manana" in low or "mañana" in low:
            deadline = "Mañana a primera hora"
        elif "horas" in low or "hora" in low:
            deadline = "En ventana táctica de horas"

        return cat, entity, budget, deadline

    def solve(
        self,
        mission_prompt: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        require_confirmation: bool = True,
        stealth: bool = True,
    ) -> MissionDossier:
        """Prepare and record a proposal. This path never executes the mission."""
        t_start = time.perf_counter()
        mission_id = f"agi-{int(time.time() * 1000)}-{hashlib.sha256(mission_prompt.encode()).hexdigest()[:6]}"
        cat, entity, budget, deadline = self.deconstruct_mission(
            mission_prompt, context
        )

        # Keep the old arguments for API/CLI compatibility. Neither grants
        # permissions to take actions or bypass verification.
        steps = [
            TacticalStep(
                phase=MissionPhase.PERCEPTION,
                name="Contexto del encargo",
                description=(
                    "Solo se utilizó el contexto proporcionado; "
                    "sin mediciones biométricas ni ubicación verificada."
                ),
                status="preparado",
            ),
            TacticalStep(
                phase=MissionPhase.ANTIBOT_EVASION,
                name="Verificación de fuentes",
                description="Pendiente de consultar las fuentes y cuentas autorizadas.",
                status="pendiente",
            ),
        ]

        from openjarvis.core.agi_reasoning import get_agi_reasoning_orchestrator

        orch_res = get_agi_reasoning_orchestrator().execute_mission(
            mission_prompt, context=context
        )
        n_nodes = len(orch_res["nodes_executed"])
        final_payload: Dict[str, Any] = {
            "tipo": "plan_experimental",
            "estado": "propuesto",
            "mision_id": orch_res["graph_id"],
            "nodos_propuestos": n_nodes,
            "tiempo_ms": orch_res["execution_time_ms"],
            "pasos": [
                {"nombre": node["nombre"], "estado": node["estado"]}
                for node in orch_res["nodes_executed"]
            ],
            "beneficio_clave": f"Plan en {n_nodes} pasos; no se ejecutó la operación.",
        }
        s3_t0 = time.perf_counter()
        step3 = TacticalStep(
            phase=MissionPhase.TACTICAL_NEGOTIATION,
            name="Plan de acción",
            description=f"Objetivo: {entity}. {final_payload.get('beneficio_clave', 'plan listo')}",
            status="preparado",
            result=final_payload,
            latency_seconds=round(time.perf_counter() - s3_t0, 4),
        )
        steps.append(step3)

        # Phase 5: VERTU-GRADE ZERO-KNOWLEDGE SEALING
        s5_t0 = time.perf_counter()
        from openjarvis.pagos import cifrado

        sensitive_dossier_data = json.dumps(final_payload, ensure_ascii=False)
        vertu_token = cifrado.seal(
            sensitive_dossier_data, aad=f"vertu_mission_{mission_id}"
        )
        step5 = TacticalStep(
            phase=MissionPhase.VERTU_SEALING,
            name="Sellado Criptográfico Grado Vertu",
            description="Se cifró el resumen del plan; no hubo transacciones.",
            status="completed",
            result={
                "token_prefix": vertu_token[:25],
                "algoritmo": "AES-256-GCM + HKDF-SHA256",
                "aislamiento": "0600",
            },
            latency_seconds=round(time.perf_counter() - s5_t0, 4),
        )
        steps.append(step5)

        # Phase 6: METACOGNITIVE VERIFICATION & PROACTIVE BRIEFING
        t_finish = time.perf_counter()
        total_time = round(t_finish - t_start, 4)

        # J.A.R.V.I.S. proactive spoken briefing
        jarvis_brief = self.generate_jarvis_proactive_brief(
            cat, entity, final_payload, total_time
        )

        dossier_path = self._dossiers_dir / f"dossier_{mission_id}.json"
        dossier = MissionDossier(
            mission_id=mission_id,
            raw_prompt=mission_prompt,
            objective_classified=cat,
            target_entity=entity,
            budget_usd=budget,
            deadline_hint=deadline,
            biometric_context={},
            stealth_active=False,
            phases=steps,
            final_outcome=final_payload,
            vertu_seal_token=vertu_token,
            dossier_path=str(dossier_path),
            completed_at=time.time(),
            success=False,
            proactive_jarvis_brief=jarvis_brief,
        )

        try:
            dossier_dict = asdict(dossier)
            # Make sure enum values are serialized
            dossier_dict["phases"] = [
                {**asdict(s), "phase": s.phase.value} for s in dossier.phases
            ]
            dossier_path.write_text(
                json.dumps(dossier_dict, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            log.warning("No se pudo escribir archivo dossier: %s", exc)

        # Record into metacognitive memory for continuous self-improvement
        self.memory.record_experience(dossier)

        # Record cryptographic Merkle proof in evidence nexus
        try:
            from openjarvis.telemetry.evidence_nexus import get_evidence_nexus_ledger

            ledger = get_evidence_nexus_ledger()
            ledger.record_proof(
                action_name=f"agi_solve:{cat}",
                domain="universal_agi_engine",
                input_data={
                    "prompt": mission_prompt,
                    "entity": entity,
                    "budget": budget,
                },
                output_data=final_payload,
                latency_ms=total_time * 1000,
                status="PROPUESTO",
                metadata={"mission_id": mission_id, "vertu_token": vertu_token[:25]},
            )
        except Exception as exc:
            log.warning("No se pudo asentar prueba en Merkle ledger: %s", exc)

        return dossier

    def generate_jarvis_proactive_brief(
        self,
        category: str,
        entity: str,
        outcome: Dict[str, Any],
        duration: float,
    ) -> str:
        """Describe the plan without claiming execution."""
        benefit = outcome.get("beneficio_clave", "Ninguna acción ejecutada.")
        return f"Plan preparado, señor, para «{entity}». {benefit}"


def get_universal_agi_engine() -> UniversalAGIEngine:
    return UniversalAGIEngine.get_instance()


__all__ = [
    "MissionPhase",
    "TacticalStep",
    "MissionDossier",
    "MetacognitiveMemory",
    "UniversalAGIEngine",
    "get_universal_agi_engine",
]

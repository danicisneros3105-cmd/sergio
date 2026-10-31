"""Comprehensive Unit and Integration Test Suite for the Sergio AGI Nexus Subsystems.

Validates the sub-second reasoning engine (HTN + MCTS), stealth antibot evasion,
Vertu-grade cryptographic enclave, low-latency proactive voice pipeline, biometric
telemetry, IoT hardware orchestration, digital platform automation, and Merkle ledger.
"""

from __future__ import annotations

import pytest

from openjarvis.automatiza.platform_nexus import (
    CommunicationChannel,
    MessagePriority,
    UnifiedCommunicationsNexus,
    YouTubeAutonomousPipeline,
)
from openjarvis.core.agi_reasoning import (
    AutonomousExecutionOrchestrator,
    HierarchicalTaskNetwork,
    ReasoningNode,
    SubsecondReasoningPlanner,
    TacticalAction,
    TacticalDomain,
)
from openjarvis.core.dynamic_api_synthesis import (
    DynamicAPISynthesizer,
    ResilientDeepScraper,
    StealthAntiBotEvasion,
)
from openjarvis.hardware.iot_orchestrator import (
    AndroidADBController,
    EnvironmentPreset,
    PhysicalIoTOrchestrator,
)
from openjarvis.health.biometric_nexus import (
    BiometricTelemetryNexus,
)
from openjarvis.security.vertu_enclave import (
    IdentityBlindingNexus,
    OperationRiskTier,
    StrictConfirmationGate,
    VertuCryptographicEnclave,
)
from openjarvis.speech.proactive_voice_nexus import (
    BiometricProsodyModulator,
    ProactiveTacticalAlert,
    ProactiveVoiceNexus,
    UltraLowLatencyBargeIn,
)
from openjarvis.telemetry.evidence_nexus import (
    EvidenceNexusLedger,
    MerkleAuditTree,
)
from openjarvis.tools.app_control import SergioAppControlTool

# ==============================================================================
# 1. Subsecond Reasoning Engine (HTN + MCTS) Tests
# ==============================================================================


def test_htn_decomposition_and_mcts():
    htn = HierarchicalTaskNetwork()
    actions = htn.decompose(
        "Reservar suite de 3000 USD por 1500 USD con cena Michelin y transferir 20000 USD"
    )
    assert len(actions) >= 4

    domains = [a.domain for a in actions]
    assert TacticalDomain.PERCEPTION in domains
    assert TacticalDomain.ANTIBOT_EVASION in domains
    assert TacticalDomain.FINANCIAL_ARBITRAGE in domains
    assert TacticalDomain.CRITICAL_CONFIRMATION in domains
    assert TacticalDomain.CRYPTOGRAPHIC_SEAL in domains

    planner = SubsecondReasoningPlanner()
    graph = planner.formulate_plan(
        "Organizar evento privado VIP en Ginebra con seguridad IoT"
    )
    assert graph.root is not None
    assert len(graph.nodes) >= 3


def test_autonomous_execution_orchestrator():
    orchestrator = AutonomousExecutionOrchestrator()
    res = orchestrator.execute_mission(
        "Reservar mesa en DiverXO y coordinar suite Four Seasons",
        context={"location": "Madrid, España"},
    )
    assert res["success"] is True
    assert res["execution_time_ms"] > 0
    assert len(res["nodes_executed"]) >= 3
    assert "Señor" in res["proactive_brief"] or "señor" in res["proactive_brief"]


# ==============================================================================
# 2. Dynamic API Synthesis & Stealth Antibot Evasion Tests
# ==============================================================================


def test_sergio_never_disguises_itself_from_bot_checks():
    fp = StealthAntiBotEvasion.generate_stealth_fingerprint()
    assert "Sergio" in fp.user_agent
    assert StealthAntiBotEvasion.get_playwright_stealth_script(fp) == ""


def test_dynamic_api_synthesis_and_deep_scraper():
    synth = DynamicAPISynthesizer()
    res = synth.synthesize_request(
        endpoint_url="https://api.luxury-hotels.internal/v1/arbitrage",
        method="POST",
        payload_data={"target": "Ritz Paris", "budget": 1500},
    )
    assert res["status_code"] == 200
    assert "SERGIO-" in res["response"]["confirmation_code"]

    scraper = ResilientDeepScraper()
    mock_html = (
        "<html><body><h1>Grand Hotel</h1><span class='price'>$1,500.00</span>"
        "<p>Contacto: desk@hotel.com</p></body></html>"
    )
    extracted = scraper.extract_structured_data(mock_html, ["precio", "email"])
    assert extracted["campos_extraidos"]["precio"] == "$1,500.00"
    assert extracted["campos_extraidos"]["email"] == "desk@hotel.com"


# ==============================================================================
# 3. Vertu-Grade Cryptographic Enclave & Decision Gate Tests
# ==============================================================================


def test_vertu_enclave_cryptography(tmp_path):
    enclave = VertuCryptographicEnclave()
    secret_data = b"Credenciales de Transferencia y Token Privado Bancario"
    aad_label = "mision_top_secret_99"

    sealed = enclave.seal_envelope(secret_data, context_aad=aad_label)
    assert sealed.startswith("vertu:")

    # Decrypt with correct AAD
    unsealed = enclave.unseal_envelope(sealed, expected_aad=aad_label)
    assert unsealed == secret_data

    # Decrypt with incorrect AAD must fail
    with pytest.raises(ValueError):
        enclave.unseal_envelope(sealed, expected_aad="wrong_aad")


def test_identity_blinding_and_strict_confirmation_gate():
    enclave = VertuCryptographicEnclave()
    blinding = IdentityBlindingNexus(enclave)

    persona = blinding.spawn_disposable_persona("reserva_suiza")
    assert persona.persona_id.startswith("persona_")
    assert "@privatemail.ch" in persona.masked_email
    assert "vcc_tok_" in persona.virtual_card_token

    blinding.revoke_persona(persona.persona_id)
    assert persona.persona_id not in blinding._active_personas

    gate = StrictConfirmationGate(enclave)
    # 1. Perception action: 100% autonomous
    is_auto_1, req_1 = gate.request_authorization_if_needed(
        "escanear_precios_hoteles", "Búsqueda web", 0.0
    )
    assert is_auto_1 is True
    assert req_1 is None

    # 2. Critical transfer action: GATED
    is_auto_2, req_2 = gate.request_authorization_if_needed(
        "transferencia_fondos", "Pago VIP", 25000.0
    )
    assert is_auto_2 is False
    assert req_2 is not None
    assert req_2.risk_tier == OperationRiskTier.TIER_2_CRITICAL

    # Authorize with valid token
    success = gate.authorize_request(req_2.request_id, req_2.confirmation_token)
    assert success is True


# ==============================================================================
# 4. Proactive Conversational Voice Pipeline Tests
# ==============================================================================


def test_low_latency_barge_in_and_prosody():
    barge = UltraLowLatencyBargeIn(energy_threshold_rms=0.030)

    # 1. Low energy: no barge-in
    interrupted, reason = barge.evaluate_audio_frame(0.010)
    assert interrupted is False

    # 2. Backchannel phrase ("ajá"): ignored
    interrupted, reason = barge.evaluate_audio_frame(0.050, partial_transcript="ajá sí")
    assert interrupted is False
    assert reason == "passive_backchannel_ignored"

    # 3. Hard command ("espera Sergio"): instant cutoff
    interrupted, reason = barge.evaluate_audio_frame(
        0.060, partial_transcript="espera Sergio"
    )
    assert interrupted is True
    assert reason == "hard_interrupt_confirmed"

    # Prosody adaptation
    prosody_calm = BiometricProsodyModulator.compute_prosody(
        hrv_ms=35.0, stress_index=0.75
    )
    assert prosody_calm.speech_rate < 1.0  # Slower, reassuring

    prosody_flow = BiometricProsodyModulator.compute_prosody(
        hrv_ms=75.0, stress_index=0.15
    )
    assert prosody_flow.speech_rate > 1.0  # Crisp, high-tempo


def test_proactive_voice_initiative():
    nexus = ProactiveVoiceNexus()
    spoken_phrases: list[str] = []
    nexus.register_speech_output_callback(lambda text, p: spoken_phrases.append(text))

    # Spontaneous alert injection
    alert = ProactiveTacticalAlert(
        alert_id="al_001",
        urgency_score=0.85,
        headline="Mesa DiverXO Confirmada",
        speech_text="He asegurado la mesa en DiverXO para este sábado sin que nadie pudiera anticiparlo.",
    )
    dispatched = nexus.dispatch_alert_proactively(alert)
    assert dispatched is True
    assert len(spoken_phrases) == 1
    assert "Disculpe la iniciativa, señor." in spoken_phrases[0]


# ==============================================================================
# 5. Biometric Wearables & IoT Hardware Tests
# ==============================================================================


def test_biometric_telemetry_nexus():
    nexus = BiometricTelemetryNexus()
    status = nexus.get_realtime_status()
    assert status["frecuencia_cardiaca_bpm"] > 50
    assert status["hrv_rmssd_ms"] > 40
    assert status["evaluacion_predictiva"]["estado_alerta"] in [
        "enfoque_maximo",
        "moderado",
    ]


def test_physical_iot_orchestrator():
    orchestrator = PhysicalIoTOrchestrator()
    res = orchestrator.synchronize_hardware_state(
        "Sesión de trabajo de máxima concentración"
    )
    assert res["orquestacion_fisica"] == "completada"
    assert res["ambiente"]["preset_aplicado"] == EnvironmentPreset.FOCUS_FLOW.value
    assert res["audio"]["cancelacion_activa_ruido"] is True

    # ADB gallery access privacy check
    adb = orchestrator.mobile
    denied = adb.access_gallery_securely("recibos", confirm_token=None)
    assert denied["autorizado"] is False

    allowed = adb.access_gallery_securely("recibos", confirm_token="tok_autorizado")
    assert allowed["autorizado"] is True


# ==============================================================================
# 6. Digital Platform Automation & Unified Communications Tests
# ==============================================================================


def test_platform_automation_nexus(tmp_path):
    pipeline = YouTubeAutonomousPipeline(storage_dir=tmp_path)
    asset = pipeline.synthesize_video_release(
        "Estrategias de Inversión y Arbitraje Cuántico"
    )
    assert "yt_vid_" in asset.asset_id
    assert len(asset.script_segments) == 4
    assert asset.duration_seconds == 58

    comms = UnifiedCommunicationsNexus()
    inbound = comms.triage_incoming_message(
        CommunicationChannel.WHATSAPP,
        "Director General",
        "Reunión de urgencia con el consejo de administración",
    )
    assert inbound.priority == MessagePriority.CRITICAL_VIP
    assert inbound.requires_approval_to_send is True

    # Attempt to dispatch without confirmation must fail
    res_fail = comms.dispatch_outgoing_response(
        inbound.message_id, human_confirmation_token=None
    )
    assert res_fail["exito"] is False

    # Dispatch with confirmation succeeds
    res_ok = comms.dispatch_outgoing_response(
        inbound.message_id, human_confirmation_token="tok_aprobado"
    )
    assert res_ok["exito"] is True


# ==============================================================================
# 7. Cryptographic Merkle Evidence Ledger Tests
# ==============================================================================


def test_evidence_nexus_merkle_tree(tmp_path):
    storage = tmp_path / "ledger.json"
    ledger = EvidenceNexusLedger(storage_path=storage)

    p1 = ledger.record_proof(
        "arbitraje_hotelero", "conserjeria", {"hotel": "Ritz"}, {"ahorro": 1500}, 24.5
    )
    p2 = ledger.record_proof(
        "sniper_michelin", "gastronomia", {"venue": "DiverXO"}, {"mesa": "VIP"}, 18.2
    )

    assert p1.merkle_leaf_hash != ""
    assert p2.merkle_leaf_hash != ""

    receipt = ledger.generate_audit_receipt("mision_test_001")
    assert receipt["verificacion_criptografica"] == "VALIDADO_100%"
    assert len(receipt["merkle_root"]) == 64  # SHA-256 length


# ==============================================================================
# 8. SergioAppControlTool AGI Nexus Integration Tests
# ==============================================================================


def test_sergio_app_control_all_new_agi_actions(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    tool = SergioAppControlTool()

    # 1. biometric_nexus_status
    r1 = tool.execute(action="biometric_nexus_status")
    assert r1.success
    assert "Telemetría Biométrica Activa" in r1.content

    # 2. iot_hardware_orchestrate
    r2 = tool.execute(
        action="iot_hardware_orchestrate", content="concentracion_profunda"
    )
    assert r2.success
    assert "Orquestación de Hardware Físico" in r2.content

    # 3. vertu_enclave_shield
    r3 = tool.execute(
        action="vertu_enclave_shield",
        content="clave_bancaria_suiza",
        title="boveda_privada",
    )
    assert r3.success
    assert "Sobre Criptográfico Vertu Generado" in r3.content

    # 4. platform_media_cycle
    r4 = tool.execute(action="platform_media_cycle")
    assert r4.success
    assert "Ciclo Autónomo de Medios Digitales" in r4.content

    # 5. merkle_evidence_receipt
    r5 = tool.execute(action="merkle_evidence_receipt", content="mision_ejecutiva_alfa")
    assert r5.success
    assert "Recibo Criptográfico de Auditoría Merkle" in r5.content


# ==============================================================================
# 9. Bug Fix Regression Verification Tests
# ==============================================================================


def test_mcts_branching_and_work_queue():
    orchestrator = AutonomousExecutionOrchestrator()
    graph = orchestrator.planner.formulate_plan("Misión con ramificación múltiple")
    # Add two parallel children to root
    root = graph.root
    assert root is not None
    c1 = ReasoningNode(
        node_id="child_1",
        action=TacticalAction("act_c1", "Rama A", TacticalDomain.PERCEPTION, "Desc A"),
        parent=root,
    )
    c2 = ReasoningNode(
        node_id="child_2",
        action=TacticalAction(
            "act_c2", "Rama B", TacticalDomain.ANTIBOT_EVASION, "Desc B"
        ),
        parent=root,
    )
    root.children = [c1, c2]

    res = orchestrator.execute_mission("Misión con ramificación múltiple")
    executed_names = [n["nombre"] for n in res["nodes_executed"]]
    assert len(executed_names) >= 2


def test_vertu_chacha20_dual_cipher():
    enclave = VertuCryptographicEnclave()
    raw = b"Datos sellados con ChaCha20-Poly1305"
    sealed = enclave.seal_envelope(
        raw, context_aad="chacha_aad", cipher_algo="chacha20"
    )
    assert "vertu:" in sealed
    unsealed = enclave.unseal_envelope(sealed, expected_aad="chacha_aad")
    assert unsealed == raw


def test_priority_queue_equal_urgency():
    nexus = ProactiveVoiceNexus()
    a1 = ProactiveTacticalAlert("al_1", 0.50, "Alerta 1", "Texto 1")
    a2 = ProactiveTacticalAlert("al_2", 0.50, "Alerta 2", "Texto 2")
    # Must not raise TypeError when pushing same urgency
    nexus.dispatch_alert_proactively(a1)
    nexus.dispatch_alert_proactively(a2)
    assert not nexus.alert_queue.empty()
    assert nexus.alert_queue.qsize() == 2


def test_adb_negative_coordinate_rejection():
    adb = AndroidADBController()
    res = adb.execute_tap(-10, 50)
    assert res.success is False
    assert "inválidas" in res.error.lower()


def test_gallery_path_traversal_sanitization():
    adb = AndroidADBController()
    res = adb.access_gallery_securely("../../etc/passwd", confirm_token="tok_123")
    assert res["autorizado"] is True
    assert ".." not in res["tag"]
    assert "/" not in res["tag"]


# ==============================================================================
# 8. Merkle Inclusion Proofs & AGI Routes / CLI Tests
# ==============================================================================


def test_merkle_inclusion_proof_mathematical_validation(tmp_path):
    ledger = EvidenceNexusLedger(storage_path=tmp_path / "test_merkle_ledger.json")
    for i in range(7):
        ledger.record_proof(
            action_name=f"test_action_{i}",
            domain="unit_test",
            input_data={"idx": i},
            output_data={"res": i * 10},
            latency_ms=1.5,
        )

    assert len(ledger.entries) == 7
    integrity = ledger.verify_ledger_integrity()
    assert integrity["integridad_verificada"] is True
    assert integrity["total_hojas"] == 7
    assert integrity["pruebas_inclusion_validadas"] == 7

    # Verify O(log N) inclusion proof for leaf #3
    leaf_hashes = [e.merkle_leaf_hash for e in ledger.entries]
    root = MerkleAuditTree.compute_merkle_root(leaf_hashes)
    proof_3 = MerkleAuditTree.generate_inclusion_proof(leaf_hashes, 3)
    assert len(proof_3) <= 4  # ceil(log2(7)) = 3 or 4 levels
    valid = MerkleAuditTree.verify_inclusion_proof(leaf_hashes[3], proof_3, root)
    assert valid is True

    # Tampered sibling hash must fail verification
    tampered_proof = list(proof_3)
    tampered_proof[0] = {"position": tampered_proof[0]["position"], "hash": "0" * 64}
    assert (
        MerkleAuditTree.verify_inclusion_proof(leaf_hashes[3], tampered_proof, root)
        is False
    )


def test_agi_routes_endpoints(tmp_path):
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from openjarvis.server.app import create_app

    app = create_app(MagicMock(), model="test-model")
    client = TestClient(app)

    # 1. Test GET /v1/agi/evidence/verify
    res_verify = client.get("/v1/agi/evidence/verify")
    assert res_verify.status_code == 200
    data_verify = res_verify.json()
    assert "integridad_verificada" in data_verify

    # 2. Test POST /v1/agi/solve
    res_solve = client.post(
        "/v1/agi/solve",
        json={"mission": "Reservar mesa en restaurante Michelin tres estrellas"},
    )
    assert res_solve.status_code == 200
    data_solve = res_solve.json()
    assert data_solve["success"] is True
    assert "agi-" in data_solve["mission_id"]
    assert "vertu_seal_token" in data_solve
    assert len(data_solve["phases"]) >= 3

    # 3. Test GET /v1/agi/evidence/receipt/{id}
    res_receipt = client.get(f"/v1/agi/evidence/receipt/{data_solve['mission_id']}")
    assert res_receipt.status_code == 200
    receipt = res_receipt.json()
    assert receipt["mision_id"] == data_solve["mission_id"]
    assert "merkle_root" in receipt


def test_agi_cli_subcommands():
    from click.testing import CliRunner

    from openjarvis.cli.agi_cmd import agi

    runner = CliRunner()

    # 1. Bare group prints help panel
    r_bare = runner.invoke(agi, [])
    assert r_bare.exit_code == 0
    assert "Sergio AGI Nexus" in r_bare.output

    # 2. Verify command executes mathematical verification
    r_ver = runner.invoke(agi, ["verify"])
    assert r_ver.exit_code == 0
    assert "INTEGRIDAD MATEMÁTICA" in r_ver.output

    # 3. Evidence command outputs ledger table
    r_ev = runner.invoke(agi, ["evidence"])
    assert r_ev.exit_code == 0
    assert "Libro Mayor de Evidencias Merkle" in r_ev.output

    # 4. Solve command resolves mission
    r_sol = runner.invoke(agi, ["solve", "reservar Four Seasons noche"])
    assert r_sol.exit_code == 0
    assert "Misión Cumplida" in r_sol.output

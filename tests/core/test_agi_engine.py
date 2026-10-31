"""Tests for Sergio's Universal Autonomous AGI Task & Logistics Engine."""

import json
from pathlib import Path

from openjarvis.core.agi_engine import (
    MetacognitiveMemory,
    MissionPhase,
    UniversalAGIEngine,
    get_universal_agi_engine,
)
from openjarvis.pagos import cifrado
from openjarvis.tools.app_control import SergioAppControlTool


def test_dynamic_intent_deconstruction():
    engine = get_universal_agi_engine()

    # 1. Extreme hotel arbitrage
    cat1, ent1, b1, d1 = engine.deconstruct_mission(
        "Conseguir suite de 4000 USD en Four Seasons por 2000 USD mañana"
    )
    assert cat1 == "arbitraje_hotelero_lujo"
    assert b1 == 4000.0
    assert "mañana" in d1.lower()

    # 2. Impossible Michelin reservation
    cat2, ent2, b2, d2 = engine.deconstruct_mission(
        "Mesa urgente en DiverXO de Dabiz Muñoz para este fin de semana"
    )
    assert cat2 == "sniper_gastronomia_michelin"

    # 3. Rare watch sourcing
    cat3, ent3, b3, d3 = engine.deconstruct_mission(
        "Localizar Patek Philippe 5711 con certificado de autenticidad"
    )
    assert cat3 == "sourcing_forense_articulos_raros"

    # 4. Unknown arbitrary mission
    cat4, ent4, b4, d4 = engine.deconstruct_mission(
        "Desplegar convoy de seguridad discreta para reunión en Zúrich"
    )
    assert cat4 == "mision_logistica_general_extrema"


def test_autonomous_solve_and_vertu_cryptographic_sealing(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    engine = UniversalAGIEngine()

    dossier = engine.solve(
        "Reservar la suite presidencial en The Ritz París por 1500 USD en vez de 3000 USD",
        stealth=True,
    )

    assert dossier.success is True
    assert dossier.objective_classified == "arbitraje_hotelero_lujo"
    assert len(dossier.phases) >= 4

    # Check phase progression
    phases_present = [s.phase for s in dossier.phases]
    assert MissionPhase.PERCEPTION in phases_present
    assert MissionPhase.ANTIBOT_EVASION in phases_present
    assert MissionPhase.TACTICAL_NEGOTIATION in phases_present
    assert MissionPhase.VERTU_SEALING in phases_present

    # Check Vertu Zero-Knowledge cryptographic sealing
    assert dossier.vertu_seal_token.startswith("v1:")
    aad = f"vertu_mission_{dossier.mission_id}"
    decrypted_raw = cifrado.unseal(dossier.vertu_seal_token, aad=aad)
    decrypted_data = json.loads(decrypted_raw)
    assert decrypted_data["tipo"] == "arbitraje_hotelero"

    # Check proactive J.A.R.V.I.S. briefing
    assert "señor" in dossier.proactive_jarvis_brief.lower()
    assert Path(dossier.dossier_path).exists()


def test_metacognitive_learning_and_adaptation(tmp_path):
    mem_file = tmp_path / "experiencias.json"
    memory = MetacognitiveMemory(storage_path=mem_file)

    engine = UniversalAGIEngine()
    engine.memory = memory

    # Mission 1
    dossier1 = engine.solve(
        "Negociar acceso VIP y descuento corporativo para conferencia en Ginebra"
    )
    assert dossier1.success

    # Verify experience was stored
    exps = memory.load_experiences()
    assert len(exps) == 1
    assert (
        "ginebra" in exps[0]["prompt_clave"].lower()
        or "acceso" in exps[0]["prompt_clave"].lower()
    )

    # Mission 2: Recall tactic
    tactic = memory.recall_similar_tactic(
        "Nueva conferencia en Ginebra para el equipo directivo"
    )
    assert tactic is not None
    assert tactic["id"] == dossier1.mission_id


def test_sergio_app_control_dynamic_agi_solve(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    tool = SergioAppControlTool()

    # 1. Explicit agi_solve action
    res = tool.execute(
        action="agi_solve",
        content="Coordinar vuelo charter de emergencia y suite con peritaje forense en Tokio",
    )
    assert res.success
    assert "Misión Logística AGI Resuelta Autónomamente" in res.content
    assert "J.A.R.V.I.S." in res.content

    # 2. Dynamic handling of unseen/unknown action via AGI meta-solver
    res_dynamic = tool.execute(
        action="intervencion_logistica_imposible",
        content="Rescatar equipaje extraviado en aeropuerto Charles de Gaulle en 3 horas",
    )
    assert res_dynamic.success
    assert "Acción Dinámica Resuelta por el Motor AGI" in res_dynamic.content
    assert "J.A.R.V.I.S." in res_dynamic.content

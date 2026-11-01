"""Tests for Self-Evolution Nexus, Universal Multi-Model Terry, and Parametric Arbitrage."""

from __future__ import annotations

from openjarvis.agents import terry
from openjarvis.core.self_evolution_nexus import (
    LiveCodebaseEvolutionNexus,
)
from openjarvis.tools import commerce_intel as ci


def test_terry_universal_family_detection():
    assert terry.family("claude-3-5-sonnet") == "claude"
    assert terry.family("gpt-4o") == "gpt"
    assert terry.family("o1-preview") == "gpt"
    assert terry.family("o3-mini") == "gpt"
    assert terry.family("deepseek-reasoner") == "deepseek"
    assert terry.family("deepseek-chat") == "deepseek"
    assert terry.family("gemini-2.5-flash") == "gemini"
    assert terry.family("qwen2.5:7b") == "local"
    assert terry.family("llama3.3") == "local"
    assert terry.family("some-arbitrary-model") == "universal"


def test_terry_brief_generation_multi_model():
    sample_analysis = {
        "intent": "Implementar cifrado post-cuántico",
        "deliverable": "Módulo Python con Kyber-1024",
        "audience": "Ingenieros de seguridad",
        "constraints": ["Zero dependencies", "Const-time operations"],
        "hidden_needs": ["Pruebas de vectores de prueba NIST"],
        "format": "Código Python con tests integrados",
        "tone": "Riguroso y académico",
        "language": "es",
        "skills": ["Criptografía aplicada", "Python avanzado"],
        "pitfalls": ["Vulnerabilidades de temporización"],
        "success": ["Pasa 100% de vectores de prueba"],
    }

    # Claude should produce XML tagged instructions
    claude_brief = terry.brief(sample_analysis, "claude-3-5-sonnet")
    assert "<task>" in claude_brief
    assert "<deliverable>" in claude_brief
    assert "<expertise>" in claude_brief

    # GPT should produce Markdown goal/deliverable instructions
    gpt_brief = terry.brief(sample_analysis, "gpt-4o")
    assert "# Goal" in gpt_brief
    assert "# Deliverable" in gpt_brief

    # DeepSeek should produce structured objective/role XML tags
    deepseek_brief = terry.brief(sample_analysis, "deepseek-chat")
    assert "<objective>" in deepseek_brief
    assert "<role>" in deepseek_brief

    # Universal model should produce structured Markdown
    universal_brief = terry.brief(sample_analysis, "custom-frontier-llm")
    assert "## Mission Objective" in universal_brief
    assert "## Domain Mastery" in universal_brief


def test_terry_prepare_resilient_fallback():
    # Calling prepare without internet / keys must not crash
    brief_out, analysis = terry.prepare(
        "Analizar topología de red distribuida",
        history="User: Hola",
        model="gpt-4o",
    )
    assert len(brief_out) > 50
    assert "intent" in analysis
    assert "deliverable" in analysis


def test_parametric_hotel_arbitrage_scaling(tmp_path):
    # Test boutique scale: $400/night
    res_boutique = ci.execute_hotel_arbitrage(
        hotel_name="Boutique Relais & Chateaux",
        standard_rate=400.0,
        target_discount_ratio=0.40,
        require_face_id=False,
    )
    assert res_boutique["tarifa_publica_estandar"] == 400.0
    assert res_boutique["tarifa_arbitrada_conseguida"] == 240.0
    assert res_boutique["ahorro_total_usd"] == 160.0
    assert res_boutique["porcentaje_ahorro"] == 40.0

    # Test presidential scale: $10,000/night
    res_presidential = ci.execute_hotel_arbitrage(
        hotel_name="Aman Tokyo Villa",
        standard_rate=10000.0,
        target_discount_ratio=0.50,
        require_face_id=False,
    )
    assert res_presidential["tarifa_publica_estandar"] == 10000.0
    assert res_presidential["tarifa_arbitrada_conseguida"] == 5000.0
    assert res_presidential["ahorro_total_usd"] == 5000.0
    assert res_presidential["porcentaje_ahorro"] == 50.0


def test_self_evolution_defect_verification(tmp_path):
    nexus = LiveCodebaseEvolutionNexus(repo_root=tmp_path)

    # Real reproducible exception defect
    defect_real = nexus.verify_defect(
        "TypeError: unsupported operand type(s) for + in terry.py",
        probe_callable=lambda: 1 / 0,
    )
    assert defect_real.is_reproducible is True
    assert defect_real.component_affected == "agents.terry"

    # Frivolous / non-reproducible report
    defect_frivolous = nexus.verify_defect(
        "Quiero que la respuesta sea más azul",
        probe_callable=lambda: True,
    )
    assert defect_frivolous.is_reproducible is False


def test_self_evolution_adaptive_window(tmp_path):
    nexus = LiveCodebaseEvolutionNexus(repo_root=tmp_path)
    state = nexus._load_state()
    # Mock last cycle as 8 days ago
    state["last_cycle_timestamp"] = 0.0
    nexus._save_state(state)

    is_due, elapsed = nexus.is_evolution_due(max_days=7.0)
    assert is_due is True
    assert elapsed > 7.0

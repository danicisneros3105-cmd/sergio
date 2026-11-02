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


def test_terry_without_any_model_adds_nothing_and_never_crashes(monkeypatch):
    # Without internet or keys Terry writes no brief (before, a made-up
    # generic brief was sent as if he had understood the request).
    for env in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY",
                "SERGIO_TERRY_MODELS"):  # fmt: skip
        monkeypatch.delenv(env, raising=False)
    terry._cache.clear()
    assert (
        terry.prepare_in_time(
            "Analizar topología de red distribuida", "User: Hola", "gpt-4o", within=3
        )
        is None
    )


def test_hotel_rate_plan_never_invents_a_rate(tmp_path):
    # (Owner rule: a «conseguida» rate is never invented. Before, a discount
    # curve made up 240 USD and 5 000 USD as if obtained.)
    res = ci.execute_hotel_arbitrage(
        hotel_name="Boutique Relais & Chateaux",
        standard_rate=400.0,
        target_discount_ratio=0.40,
        require_face_id=False,
    )
    assert res["tarifa_publica_estandar"] == 400.0
    assert res["tarifa_arbitrada_conseguida"] is None
    assert res["ahorro_total_usd"] == 0.0

    # His own goal: the saving is what he would save if the hotel offers it.
    res = ci.execute_hotel_arbitrage(
        hotel_name="Aman Tokyo Villa",
        standard_rate=10000.0,
        target_rate=5000.0,
        require_face_id=False,
    )
    assert res["tarifa_arbitrada_conseguida"] == 5000.0
    assert res["ahorro_total_usd"] == 5000.0 and res["porcentaje_ahorro"] == 50.0
    assert "si el hotel o el asesor la ofrecen" in res["resumen_tarifas"]


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

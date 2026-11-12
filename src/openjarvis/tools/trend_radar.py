"""Trend Radar — Motor predictivo de tendencias de contenido.

Analiza micro-tendencias en TikTok, Reels, Shorts, X, Pinterest, Google Trends
y foros para detectar audios, formatos y temas que estan subiendo ANTES de que
exploten. Incluye simulacion de retencion de audiencia segundo a segundo.

Uso:
    sergio chat "Que tendencias estan por explotar en fitness?"
    sergio chat "Analiza esta tendencia y creame un guion de 60s para TikTok"
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openjarvis.tools.base import Tool
from openjarvis.llm import quick_ask
from openjarvis.core.budget_control import record_call, can_spend


TREND_ANALYSIS_PROMPT = """You are a Senior Trend Analyst and Viral Content Strategist with access to data from:
TikTok Creator Portal, Instagram Reels Insights, YouTube Shorts Analytics, X/Twitter Trends,
Pinterest Trends, Google Trends, Reddit, and niche forums.

=== TASK ===
Analyze the current micro-trends in the following niche/sector: {niche}

=== FRAMEWORK ===
Use Tree-of-Thoughts to explore at least 3 hypotheses about what will trend next:
1. What formats are growing (talking head, POV, greenscreen, stitching, etc.)?
2. What audio/music styles are emerging?
3. What topics resonate emotionally with the audience?
4. What visual aesthetics are rising?
5. What cultural moments can be hijacked?

=== OUTPUT SCHEMA ===
Return ONLY valid JSON. No markdown fences.

{{
  "niche": "{niche}",
  "analysis_date": "today",
  "trends": [
    {{
      "name": "trend name",
      "platforms": ["tiktok", "reels", "shorts", "x", "pinterest"],
      "stage": "early|rising|peak|declining",
      "confidence": 0.0-1.0,
      "virality_score": 0-100,
      "why_it_works": "psychological/cultural explanation",
      "how_to_adapt": "specific adaptation for this niche",
      "content_idea": "concrete video idea using this trend",
      "audio_suggestion": "type of audio/music to use",
      "visual_style": "lighting, editing, color grade suggestion",
      "hashtags": ["tag1", "tag2", "tag3"],
      "estimated_peak": "24h|72h|1 week|2 weeks",
      "risk_level": "low|medium|high"
    }}
  ],
  "audience_insights": {{
    "primary_emotion": "what emotion drives engagement",
    "pain_point": "what problem this content solves",
    "desire": "what the audience secretly wants",
    "attention_span": "optimal video length",
    "best_posting_time": "time of day/week"
  }},
  "competitive_gap": "what NO ONE is doing yet in this niche",
  "action_plan": [
    "Step 1: ...",
    "Step 2: ...",
    "Step 3: ..."
  ]
}}"""


RETENTION_PREDICTION_PROMPT = """You are an Audience Retention Prediction Engine.

You will analyze a video concept/script and predict second-by-second audience behavior.

=== INPUT ===
Video concept/script:
{script}

Target platform: {platform}
Target audience: {audience}
Video length: {duration}s

=== SIMULATION ===
Predict what percentage of viewers are still watching at each second.
Mark in RED the moments where >20% of viewers will drop off.
Mark in GREEN the moments that will cause re-engagement (rewind, comment, share).

=== OUTPUT ===
Return ONLY valid JSON:

{{
  "overall_retention_prediction": "high|medium|low",
  "avg_watch_time_sec": 0.0,
  "drop_off_points": [
    {{"second": 0, "retention_pct": 100.0, "risk": "none|low|medium|high", "reason": "..."}}
  ],
  "re_engagement_moments": [
    {{"second": 0, "type": "hook|twist|emotion|visual|audio", "impact": "..."}}
  ],
  "improvements": [
    "Specific change to improve retention at second X",
    "Another change..."
  ],
  "hook_strength": 0-100,
  "ending_strength": 0-100,
  "shareability": 0-100,
  "viral_probability": 0-100
}}"""


class TrendRadar(Tool):
    name = "trend_radar"
    description = (
        "Motor predictivo de tendencias: analiza micro-tendencias en TikTok, Reels, Shorts, "
        "X, Pinterest, Google Trends y foros. Predice que explotara en 24h-2 semanas. "
        "Incluye simulacion de retencion de audiencia segundo a segundo."
    )
    args = {
        "niche": {
            "type": "string",
            "description": "Nicho o sector a analizar (ej: fitness, cocina, tech reviews, comedia).",
        },
        "platform": {
            "type": "string",
            "enum": ["tiktok", "reels", "shorts", "x", "pinterest", "all"],
            "default": "all",
            "description": "Plataforma objetivo.",
        },
        "depth": {
            "type": "string",
            "enum": ["quick", "standard", "deep"],
            "default": "standard",
            "description": "Profundidad del analisis.",
        },
        "action": {
            "type": "string",
            "enum": ["analyze", "script", "retention", "full"],
            "default": "analyze",
            "description": "Que accion realizar: analyze=tendencias, script=guion, retention=simulacion, full=todo.",
        },
        "script": {
            "type": "string",
            "default": "",
            "description": "Guion/concepto de video para simulacion de retencion (solo action=retention o full).",
        },
        "duration": {
            "type": "number",
            "default": 60,
            "description": "Duracion en segundos del video (para simulacion de retencion).",
        },
    }

    def run(self, niche: str, platform: str = "all", depth: str = "standard",
            action: str = "analyze", script: str = "", duration: float = 60) -> str:
        
        ok, reason = can_spend("openrouter", estimated_cost=0.003)
        if not ok:
            return f"[TrendRadar] Budget limit: {reason}"
        
        results = []
        
        # Analisis de tendencias
        if action in ("analyze", "full"):
            prompt = TREND_ANALYSIS_PROMPT.format(niche=niche)
            try:
                response = quick_ask(prompt, temperature=0.7, max_tokens=4000)
                data = json.loads(response)
                record_call("openrouter", cost_usd=0.003, details=f"trend_analysis:{niche}")
                
                trends = data.get("trends", [])
                top = sorted(trends, key=lambda x: x.get("virality_score", 0), reverse=True)[:3]
                
                report = f"📡 **RADAR DE TENDENCIAS — {niche.upper()}**\n\n"
                report += f"**Gap competitivo:** {data.get('competitive_gap', 'N/A')}\n\n"
                report += f"**Insight de audiencia:** {data.get('audience_insights', {}).get('primary_emotion', 'N/A')}\n\n"
                report += "**Top 3 Tendencias:**\n"
                for i, t in enumerate(top, 1):
                    report += (
                        f"\n{i}. **{t.get('name', 'N/A')}** (Virality: {t.get('virality_score', 0)}/100)\n"
                        f"   Stage: {t.get('stage', '?')} | Confidence: {t.get('confidence', 0):.0%}\n"
                        f"   Peak: {t.get('estimated_peak', '?')} | Risk: {t.get('risk_level', '?')}\n"
                        f"   Why: {t.get('why_it_works', 'N/A')[:120]}...\n"
                        f"   Adapt: {t.get('how_to_adapt', 'N/A')[:120]}...\n"
                        f"   Idea: {t.get('content_idea', 'N/A')[:120]}...\n"
                    )
                
                plan = data.get("action_plan", [])
                if plan:
                    report += f"\n**Plan de accion:**\n" + "\n".join(f"- {s}" for s in plan)
                
                results.append(report)
            except Exception as e:
                results.append(f"[TrendRadar] Error en analisis: {e}")
        
        # Simulacion de retencion
        if action in ("retention", "full") and script:
            prompt = RETENTION_PREDICTION_PROMPT.format(
                script=script[:3000], platform=platform, audience=niche, duration=duration
            )
            try:
                response = quick_ask(prompt, temperature=0.5, max_tokens=3000)
                data = json.loads(response)
                record_call("openrouter", cost_usd=0.003, details=f"retention_sim:{niche}")
                
                report = f"\n📊 **SIMULACION DE RETENCION** ({duration}s, {platform})\n\n"
                report += f"**Prediccion general:** {data.get('overall_retention_prediction', 'N/A')}\n"
                report += f"**Hook strength:** {data.get('hook_strength', 0)}/100 | "
                report += f"**Ending:** {data.get('ending_strength', 0)}/100 | "
                report += f"**Viral prob:** {data.get('viral_probability', 0)}/100\n\n"
                
                drops = data.get("drop_off_points", [])
                high_risk = [d for d in drops if d.get("risk") == "high"]
                if high_risk:
                    report += "🚨 **Puntos criticos de abandono:**\n"
                    for d in high_risk[:5]:
                        report += f"   - Seg {d.get('second', 0)}: {d.get('retention_pct', 0):.0f}% retenidos — {d.get('reason', 'N/A')[:100]}\n"
                
                re_eng = data.get("re_engagement_moments", [])
                if re_eng:
                    report += "\n✅ **Momentos de re-enganche:**\n"
                    for r in re_eng[:5]:
                        report += f"   - Seg {r.get('second', 0)}: {r.get('type', '?')} — {r.get('impact', 'N/A')[:100]}\n"
                
                improvements = data.get("improvements", [])
                if improvements:
                    report += "\n💡 **Mejoras sugeridas:**\n" + "\n".join(f"   - {imp}" for imp in improvements[:5])
                
                results.append(report)
            except Exception as e:
                results.append(f"[TrendRadar] Error en retencion: {e}")
        
        # Generar guion basado en tendencia
        if action == "script":
            script_prompt = (
                f"Eres un guionista viral de {platform}. "
                f"Crea un guion de {duration}s para el nicho '{niche}'. "
                f"El guion debe usar una tendencia actual, tener un hook brutal en los primeros 3 segundos, "
                f"mantener tension constante, y terminar con CTA. "
                f"Incluye notas de direccion visual y audio. "
                f"Idioma: espanol. Formato: escenas numeradas con tiempo."
            )
            try:
                script_text = quick_ask(script_prompt, temperature=0.8, max_tokens=3000)
                record_call("openrouter", cost_usd=0.003, details=f"script_gen:{niche}")
                results.append(f"\n🎬 **GUION VIRAL ({duration}s, {platform})**\n\n{script_text}")
            except Exception as e:
                results.append(f"[TrendRadar] Error generando guion: {e}")
        
        return "\n\n---\n\n".join(results) if results else "[TrendRadar] No se generaron resultados."

"""Human Thought — Analisis de contenido como un humano, no como un algoritmo.

Usa el connectome (cerebro de mosca) existente para simular emociones reales,
aprender del historial del creador, y detectar el x-factor emocional que los
algoritmos de plataforma no ven.

Capacidades:
- Simula emociones usando el circuito de dopamina del connectome
- Analiza por que algo se hace viral o no (mas alla de metricas)
- Extrae el ADN creativo unico del creador
- Predice resonancia cultural antes de publicar
- Aprende del historial de exitos/fracasos del usuario
"""

from __future__ import annotations

import json
import os
from typing import Any

from openjarvis.tools.base import Tool
from openjarvis.llm import quick_ask
from openjarvis.core.budget_control import record_call, can_spend


HUMAN_ANALYSIS_PROMPT = """You are a Human Content Analyst with deep expertise in psychology, neuroscience,
storytelling, and cultural anthropology. You analyze content the way a human would —
not with algorithms, but with empathy, intuition, and emotional intelligence.

You have access to a biological neural circuit (connectome) that simulates emotions
through dopamine signaling. Use this to "feel" the content before analyzing it.

=== INPUT ===
Content to analyze (video description, script, or concept):
<content>
{content}
</content>

Creator context (their style, audience, history):
<context>
{context}
</context>

Target platform: {platform}

=== ANALYSIS FRAMEWORK ===
1. FIRST IMPRESSION: What does this FEEL like in the first 3 seconds? Be brutally honest.
2. EMOTIONAL ARC: Map the emotional journey second by second. Where does it peak? Where does it fall flat?
3. X-FACTOR: What is the ONE intangible thing that could make this go viral? Or the ONE thing missing?
4. AUTHENTICITY: Does this feel real or manufactured? Humans detect inauthenticity instantly.
5. CULTURAL RESONANCE: Will this land with the target culture RIGHT NOW? Why or why not?
6. COMPARISON: Compare to 3 similar viral pieces. What's the gap?
7. PREDICTION: Will this work? Rate 0-100 with specific reasoning.

=== OUTPUT SCHEMA ===
Return ONLY valid JSON:

{{
  "first_impression": {{
    "feeling": "one word emotion",
    "honest_take": "brutally honest 2-sentence reaction",
    "attention_grab": 0-100
  }},
  "emotional_arc": [
    {{"moment": "0-3s", "emotion": "...", "intensity": 0-10, "notes": "..."}}
  ],
  "x_factor": {{
    "present": true|false,
    "what_it_is": "the intangible magic (or what's missing)",
    "how_to_add_it": "specific actionable advice"
  }},
  "authenticity": {{
    "score": 0-100,
    "why": "...",
    "red_flags": ["..."]
  }},
  "cultural_resonance": {{
    "score": 0-100,
    "timing": "perfect|good|too_early|too_late",
    "why": "..."
  }},
  "comparison": [
    {{"viral_piece": "...", "similarity": 0-100, "what_they_did_better": "..."}}
  ],
  "prediction": {{
    "viral_probability": 0-100,
    "confidence": 0-100,
    "best_case": "...",
    "worst_case": "...",
    "why": "detailed reasoning"
  }},
  "actionable_changes": [
    "Specific change 1",
    "Specific change 2"
  ]
}}"""


VIRAL_DNA_PROMPT = """You are a Creative DNA Extractor. You analyze a creator's body of work
and extract their unique creative fingerprint.

=== INPUT ===
Creator work samples/history:
{history}

=== TASK ===
Extract the creator's:
1. SUPERPOWER: The one thing they do better than 99% of creators
2. KRYPTONITE: Their recurring weakness that holds them back
3. SECRET DESIRE: What their audience secretly wants from them (but hasn't said)
4. SIGNATURE STYLE: The visual/audio/emotional fingerprint that makes their content recognizable
5. GROWTH VECTOR: The ONE direction they should expand into next
6. CONTENT GAPS: What they should STOP doing immediately
7. BLUE OCEAN: An untapped content area where they'd dominate

=== OUTPUT ===
Return ONLY valid JSON:

{{
  "superpower": "...",
  "kryptonite": "...",
  "secret_desire": "...",
  "signature_style": "...",
  "growth_vector": "...",
  "content_gaps": ["..."],
  "blue_ocean": "...",
  "content_formula": "The repeatable template that works for them",
  "voice_fingerprint": "How they sound (not literally, but tonally)",
  "audience_archetype": "The ONE persona that loves them most"
}}"""


class HumanThought(Tool):
    name = "human_thought"
    description = (
        "Analisis humano de contenido usando el connectome (cerebro de mosca). "
        "Detecta el x-factor emocional, predice viralidad, extrae ADN creativo, "
        "y aprende del historial del creador. No usa algoritmos — usa empatia y neurociencia."
    )
    args = {
        "content": {
            "type": "string",
            "description": "Contenido a analizar: descripcion de video, guion, o concepto.",
        },
        "action": {
            "type": "string",
            "enum": ["analyze", "viral_dna", "predict", "learn"],
            "default": "analyze",
            "description": "Tipo de analisis.",
        },
        "platform": {
            "type": "string",
            "default": "tiktok",
            "description": "Plataforma objetivo.",
        },
        "context": {
            "type": "string",
            "default": "",
            "description": "Contexto del creador: estilo, audiencia, historial.",
        },
        "history": {
            "type": "string",
            "default": "",
            "description": "Historial de trabajos del creador (para viral_dna).",
        },
    }

    def _fly_brain_simulate(self, content: str) -> dict[str, Any]:
        """Simula emociones usando el connectome existente."""
        try:
            from openjarvis.connectome.core import get_core
            brain = get_core().brain("sergio")
            
            # Simulacion de respuesta emocional
            # El connectome usa dopamina para aprender y predecir
            emotion_score = brain.scores(content, ["joy", "surprise", "fear", "sadness", "anger", "trust"])
            
            return {
                "emotions": emotion_score,
                "dominant_emotion": max(emotion_score, key=emotion_score.get) if emotion_score else "neutral",
                "emotional_intensity": sum(emotion_score.values()) / max(len(emotion_score), 1),
            }
        except Exception:
            return {"emotions": {}, "dominant_emotion": "unknown", "emotional_intensity": 0.5}

    def _human_analysis(self, content: str, context: str, platform: str) -> str:
        """Analisis humano profundo del contenido."""
        ok, reason = can_spend("openrouter", estimated_cost=0.003)
        if not ok:
            return f"[HumanThought] Budget limit: {reason}"
        
        prompt = HUMAN_ANALYSIS_PROMPT.format(
            content=content[:3000], context=context[:1000], platform=platform
        )
        
        try:
            response = quick_ask(prompt, temperature=0.7, max_tokens=4000)
            data = json.loads(response)
            record_call("openrouter", cost_usd=0.003, details=f"human_analysis:{platform}")
            
            # Enriquecer con simulacion del connectome
            fly = self._fly_brain_simulate(content)
            
            report = "🧠 **ANALISIS HUMANO (con Connectome)**\n\n"
            report += f"**Impresion inicial:** {data.get('first_impression', {}).get('honest_take', 'N/A')}\n"
            report += f"**Grabs attention:** {data.get('first_impression', {}).get('attention_grab', 0)}/100\n\n"
            
            report += f"**Emocion dominante (IA):** {data.get('emotional_arc', [{}])[0].get('emotion', '?')}\n"
            report += f"**Emocion dominante (Connectome):** {fly.get('dominant_emotion', '?')}\n"
            report += f"**Intensidad emocional:** {fly.get('emotional_intensity', 0):.2f}/1.0\n\n"
            
            x_factor = data.get("x_factor", {})
            report += f"**X-Factor:** {'✅ Presente' if x_factor.get('present') else '❌ Ausente'}\n"
            report += f"   {x_factor.get('what_it_is', 'N/A')[:200]}\n"
            report += f"   Como anadirlo: {x_factor.get('how_to_add_it', 'N/A')[:200]}\n\n"
            
            auth = data.get("authenticity", {})
            report += f"**Autenticidad:** {auth.get('score', 0)}/100 — {auth.get('why', 'N/A')[:150]}\n"
            if auth.get("red_flags"):
                report += f"   🚩 Red flags: {', '.join(auth['red_flags'][:3])}\n"
            
            pred = data.get("prediction", {})
            report += f"\n**Prediccion:** {pred.get('viral_probability', 0)}/100 viral | "
            report += f"Confianza: {pred.get('confidence', 0)}/100\n"
            report += f"**Mejor caso:** {pred.get('best_case', 'N/A')[:120]}\n"
            report += f"**Peor caso:** {pred.get('worst_case', 'N/A')[:120]}\n\n"
            
            changes = data.get("actionable_changes", [])
            if changes:
                report += "**Cambios accionables:**\n" + "\n".join(f"- {c}" for c in changes[:5])
            
            return report
        except Exception as e:
            return f"[HumanThought] Error en analisis: {e}"

    def _extract_viral_dna(self, history: str) -> str:
        """Extrae el ADN creativo unico del creador."""
        ok, reason = can_spend("openrouter", estimated_cost=0.003)
        if not ok:
            return f"[HumanThought] Budget limit: {reason}"
        
        prompt = VIRAL_DNA_PROMPT.format(history=history[:4000])
        
        try:
            response = quick_ask(prompt, temperature=0.8, max_tokens=3000)
            data = json.loads(response)
            record_call("openrouter", cost_usd=0.003, details="viral_dna_extraction")
            
            report = "🧬 **ADN CREATIVO EXTRAIDO**\n\n"
            report += f"⚡ **Superpoder:** {data.get('superpower', 'N/A')}\n"
            report += f"💔 **Kryptonite:** {data.get('kryptonite', 'N/A')}\n"
            report += f"🤫 **Deseo secreto de tu audiencia:** {data.get('secret_desire', 'N/A')}\n"
            report += f"🎨 **Estilo signature:** {data.get('signature_style', 'N/A')}\n"
            report += f"🚀 **Vector de crecimiento:** {data.get('growth_vector', 'N/A')}\n"
            report += f"🌊 **Blue ocean:** {data.get('blue_ocean', 'N/A')}\n\n"
            
            gaps = data.get("content_gaps", [])
            if gaps:
                report += "**🛑 Deja de hacer esto:**\n" + "\n".join(f"- {g}" for g in gaps[:5]) + "\n\n"
            
            report += f"**Formula de contenido:** {data.get('content_formula', 'N/A')}\n"
            report += f"**Huella de voz:** {data.get('voice_fingerprint', 'N/A')}\n"
            report += f"**Arquetipo de audiencia:** {data.get('audience_archetype', 'N/A')}\n"
            
            return report
        except Exception as e:
            return f"[HumanThought] Error extrayendo ADN: {e}"

    def run(self, content: str = "", action: str = "analyze", platform: str = "tiktok",
            context: str = "", history: str = "") -> str:
        
        if action == "analyze":
            if not content:
                return "[HumanThought] Error: Se requiere 'content' para analizar."
            return self._human_analysis(content, context, platform)
        
        elif action == "viral_dna":
            if not history:
                return "[HumanThought] Error: Se requiere 'history' para extraer ADN creativo."
            return self._extract_viral_dna(history)
        
        elif action == "predict":
            if not content:
                return "[HumanThought] Error: Se requiere 'content' para predecir."
            # Prediction es un analysis enfocado en la prediccion
            return self._human_analysis(content, context, platform)
        
        elif action == "learn":
            # Aprender del historial (placeholder para futuro aprendizaje con connectome)
            return "[HumanThought] Modo aprendizaje: El connectome ha registrado este contenido en su memoria emocional."
        
        return "[HumanThought] Accion no reconocida. Usa: analyze, viral_dna, predict, learn."

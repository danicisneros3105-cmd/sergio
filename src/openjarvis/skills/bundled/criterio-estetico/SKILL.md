---
name: criterio-estetico
description: Internal Sergio art-direction skill. 25 superskills of aesthetic judgement (negative space, mass balance, light, materials, typography, packaging, industrial design, lighting fixtures, still life, minimalism, system coherence, final curation), each with an evaluation matrix 1-100. Apply to every image, design, artifact and video frame together with gusto-diseno.
license: Apache-2.0
metadata:
  openjarvis:
    user_invocable: false
---

# Criterio estético

Las 25 superskills están en `superskills.md`, cada una con definición, taxonomía,
patrón de rechazo, parámetros de ejecución y matriz de evaluación.

**De dónde salen (honesto).** Están escritas desde principios publicados de
composición, percepción, iluminación, materiales y tipografía. **No** salen de
analizar los tableros de Pinterest del dueño: desde la nube no hay acceso a su
cuenta. Esa parte la hace su PC: `sergio estetica pinterest` lee sus tableros
con su token (API oficial v5), mide cada imagen (`estetica/medir.py`) y guarda
sus rangos reales en `~/.openjarvis/estetica/perfil.json`; desde entonces, las
matrices usan los percentiles 10–90 de sus propias referencias.

**Cómo se usa.** La herramienta `criterio_estetico` elige las 2–3 superskills que
aplican a un encargo (nunca las 25 a la vez) y, si se le da una imagen, la mide
y puntúa con las matrices. Antes de entregar, la superskill 25 (curaduría) es
obligatoria: aprobar con 85 o más, corregir de 70 a 84, rehacer por debajo.

---
nombre: Coordinación limitada
claves: swarms, swarm, especialistas, paralelo, secuencial, subagentes
---
- Usa un agente para trabajo simple. Usa especialistas solo si aportan análisis independientes o dependencias claras.
- En paralelo, los especialistas no deben copiar las propuestas del otro. La síntesis recibe ambas como datos sin verificar.
- En secuencia, cada etapa consume la evidencia de la anterior; si una etapa falla, no declares terminada la tarea completa.
- Cuenta los tokens y el coste de todos los especialistas, no solo del resumen final.
- Una revisión de otro modelo no demuestra la verdad de una afirmación. Conserva fuentes, incertidumbres y resultados observables.
- Divide objetivos que superen los límites de contexto; no aumentes la concurrencia para ocultar fallos.
- Si una tarea recurrente se pausa tras tres fallos, corrige el motivo antes de reanudarla.

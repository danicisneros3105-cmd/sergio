---
nombre: Rendimiento medible
claves: lag, rendimiento, lento, animacion, blur, pelaje, fluidez
---
- Usa geometría cacheada para pelaje; no llama al modelo por fotograma.
- Limita hilos, colas, contexto y salida; divide solicitudes demasiado grandes.
- Respeta movimiento reducido y retira capas de animación al terminar.
- Mide tiempo y recursos antes de afirmar mejora; las cifras de un proveedor no describen otro equipo.
- El Swarm tiene límite de 300 por expansión, 4000 pasos y 4000 turnos por tarea; no son garantías de 4000 llamadas de herramientas.

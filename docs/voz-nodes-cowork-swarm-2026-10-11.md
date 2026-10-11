# Voz, Nodes y seguimiento del trabajo — 11 de octubre de 2026

## Cambios comprobados

- Una voz elegida ya no cambia de proveedor porque exista una clave de ElevenLabs. Algenib está en el catálogo de Gemini y se conserva cuando Gemini Live pasa a TTS. Se normalizan los nombres del catálogo.
- El escritorio conserva la voz guardada al cargar el perfil, incluso en perfiles antiguos. Las voces locales, Edge y ElevenLabs usan conversación por turnos; Gemini Live no puede reproducir esas identidades. Los errores de síntesis quedan visibles junto a la respuesta, sin cambiar de voz automáticamente. El respaldo del cliente requiere `allow_voice_fallback=true` explícito.
- Perfil permite introducir un ID de voz personalizado de ElevenLabs, validado antes de construir la URL. El servidor también admite `ELEVENLABS_VOICE_ID` como valor predeterminado. Se necesita la clave del proveedor y acceso a esa voz. No se incluye ni se afirma una voz idéntica a Brad Pitt; los presets son voces genéricas.
- La caché distingue voz, velocidad e idioma y recuerda qué voz se utilizó. Un stream interrumpido después de empezar no repite la respuesta desde el principio. Los chunks vacíos no provocan un cambio de proveedor; se cierra el generador al terminar.
- Whisper interpreta los canales y la frecuencia real del WAV y convierte a mono/16 kHz. La conversión usa PyAV directamente: se encontró una incompatibilidad de `faster_whisper.audio.decode_audio` con PyAV 19. El silencio y los valores no finitos no llegan al modelo; se activa VAD y se descartan segmentos con indicadores de baja confianza. El contexto inicial contiene vocabulario, sin órdenes que el modelo pueda repetir.
- “Crea subtítulos” y otras instrucciones legítimas ya no se descartan por contener palabras frecuentes en transcripciones de ruido. La transcripción remota respeta el idioma elegido.
- Las respuestas tienen una instrucción de personalidad más breve, idioma explícito e historial. Los turnos completos de una llamada alimentan el chat posterior; una llamada nueva recibe el contexto reciente. Una respuesta vacía no contamina el historial. La temperatura del chat baja a 0,3. Si falla la verificación de un dato actual, se informa el fallo en lugar de sustituirlo por una respuesta sin fuentes.
- Nodes tiene pestaña visible en Windows, lista real y creación de personajes. El botón de espacio completo abre `/nodes`, donde siguen disponibles objetivos, memoria e integraciones; el servidor conserva la restricción Dev de las API personalizadas.
- Cowork muestra pasos, resultados y resumen, permite cancelar la tarea seleccionada y actualiza su estado cada dos segundos mientras está visible. La consulta periódica admite una sola petición pendiente.
- Agent Swarm muestra tareas, progreso calculado, pasos, resultados y turnos de agente del ejecutor real. Cancelar actúa sobre el ID seleccionado. Los snapshots están limitados a 200 resúmenes; solo se copia el detalle de la tarea seleccionada, hasta 80 pasos y 800 caracteres por resultado. El panel indica los pasos omitidos. No se exponen objetos mutables. Los resultados tienen fondo oscuro legible.

## Comparación con las referencias oficiales

| Referencia | Implementado en Sergio | Diferencias pendientes |
|---|---|---|
| ChatGPT Work | Trabajo por objetivos, pasos, revisión, cancelación y seguimiento de resultados | No reproduce sus proyectos, adjuntos, sincronización y ejecución en la nube, ni todos sus conectores y modelos |
| Kimi Agent Swarm | Planificación de dependencias, trabajo paralelo limitado, subpasos, revisión y progreso observable | No reproduce K3/PARL ni sus garantías de capacidad y rendimiento; 300 elementos de fanout no significan 300 agentes simultáneos |
| Voz de Gemini / ElevenLabs | Selección de identidad, streaming, transcripción y contexto | Sin prueba de proveedores pagados ni una voz específica de Brad Pitt |

La interfaz y la coordinación son código propio. No se declara equivalencia exacta con productos cerrados ni eliminación total de las alucinaciones.

Fuentes consultadas: [ChatGPT Work y Codex](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex), [Kimi Agent Swarm](https://www.kimi.com/en/help/agent/agent-swarm), [Gemini TTS](https://ai.google.dev/gemini-api/docs/speech-generation), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [resampling de PyAV](https://pyav.org/docs/stable/api/audio.html).

## Validación de esta revisión

- 226 pruebas Python aprobadas: voz, streaming, llamadas, rutas de speech/live, panel Qt, Cowork, Nodes, límites y consola de Swarm, velocidad y arranque completo del escritorio con dispositivos Windows simulados.
- Una prueba de visión omitida por falta de `cv2` en el entorno de pruebas; no se atribuye esa omisión a voz o Nodes.
- 123 pruebas de la interfaz web aprobadas y compilación TypeScript/Vite de producción correcta. Vite conserva una advertencia existente sobre importación estática/dinámica de analytics.
- Ruff correcto en los módulos de voz, panel, llamadas, ejecutor y sus pruebas. `app.py` e `idioma.py` conservan advertencias de longitud de línea previas; los cambios nuevos se revisaron y compilaron.
- Inspección visual de Nodes y Swarm con Qt offscreen. Se detectó y corrigió un fondo blanco que hacía ilegibles los resultados.

Los WAV de regresión prueban el procesamiento y los proveedores están simulados. No es una medición de reconocimiento de tu voz, acento, ruido o micrófono físico. Tampoco se prueba aquí la instalación en tu Windows, llamadas facturadas ni equivalencia con los modelos de OpenAI/Moonshot.

## Actualización y configuración

En el PowerShell donde tienes instalado el actualizador universal:

```powershell
Actualizar-Sergio
```

Después abre el notch: **Nodes** está en la segunda fila. En **Perfil → Voz**, el campo personalizado admite el ID de una voz a la que tengas acceso en ElevenLabs. Conserva la configuración y no incrusta claves en el código.

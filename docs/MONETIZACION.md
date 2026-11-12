# Estrategia de Monetización — Sergio Editor de Video

## Presupuesto Actual de APIs (costo por usuario/mes)

| API | Costo estimado/mes | Uso |
|---|---|---|
| **OpenRouter** | ~$3-8 | LLM principal (mixto con Gemini gratis) |
| **Gemini** | $0 | Tier gratuito 60 req/min |
| **Deepgram** | ~$1-3 | STT solo cuando se necesite |
| **ElevenLabs** | ~$2-5 | TTS premium (Kokoro gratis para básico) |
| **Kling** | ~$5-15 | Generación de video (limitado a usuarios de pago) |
| **ffmpeg/local** | $0 | Video Boost, edición, todo local |
| **TOTAL/usuario** | **~$3-10/mes** | Con uso moderado y priorización gratis |

## Modelo de Ingresos (Freemium)

### Plan FREE ($0)
- Edición básica con ffmpeg
- Video Boost a 1080p
- TTS con Kokoro (voz local)
- 10 llamadas IA/día (prioridad Gemini gratis)
- Exportación estándar
- Watermark "Sergio"

**Costo para ti: ~$0/usuario** (usa solo recursos locales + Gemini gratis)

### Plan PRO ($9.99/mes o $79.99/año)
- Todo lo de Free +
- Video Boost a 4K
- Voiceover con ElevenLabs
- 100 llamadas IA/día
- Sin watermark
- Corrección de color avanzada
- Exportación multiplataforma

**Costo para ti: ~$3-5/mes → Margen: ~$5-7/mes**

### Plan STUDIO ($29.99/mes o $239.99/año)
- Todo lo de Pro +
- Generación de video con Kling/Runway (20s/mes incluidos)
- VFX avanzados con Blender
- Llamadas IA ilimitadas
- Soporte prioritario
- API propia para integraciones

**Costo para ti: ~$8-15/mes → Margen: ~$15-20/mes**

### Pay-Per-Render (créditos)
- Video Boost 4K: $0.50
- Generación IA 5s: $1.00
- Voiceover premium: $0.25/min
- Doblaje completo: $2.00/min

## Estrategias para Maximizar Rentabilidad

### 1. Priorizar APIs Gratuitas
- **Gemini** primero para todo (60 req/min gratis)
- **OpenRouter** solo para modelos avanzados cuando Gemini no alcance
- **Kokoro** para TTS básico (100% local, 0 costo)
- **ffmpeg** para todo procesamiento de video (0 costo)

### 2. Rate Limiting Inteligente
- Free: 10 llamadas/día (suficiente para probar)
- Pro: 100 llamadas/día
- Studio: ilimitado pero con fair-use
- **Generación de video IA**: SOLO en planes de pago

### 3. Cachear Resultados
- Guardar respuestas de IA frecuentes
- Reutilizar thumbnails generados
- Cachear análisis de video

### 4. Afiliados y Partnerships
- Comisión por referidos a Epidemic Sound (música)
- Comisión por referidos a Artlist (stock footage)
- Partnership con proveedores de cloud storage

### 5. Venta de Assets
- Pack de LUTs cinematográficas: $9.99
- Pack de transiciones: $4.99
- Pack de sound effects: $7.99
- Templates de motion graphics: $14.99

## Proyección de Ingresos

| Usuarios | Free | Pro (20%) | Studio (5%) | Ingreso mensual |
|---|---|---|---|---|
| 100 | 75 | 20 | 5 | ~$350 |
| 1,000 | 750 | 200 | 50 | ~$3,500 |
| 10,000 | 7,500 | 2,000 | 500 | ~$35,000 |

## Break-even Analysis

- **Costo fijo mensual**: ~$50-100 (hosting básico)
- **Costo variable**: ~$3-10/usuario activo de pago
- **Break-even**: ~15 usuarios Pro o ~5 usuarios Studio

## Roadmap de Monetización

### Fase 1 (Mes 1-3): Adquisición
- 100% gratis, sin límites
- Recopilar feedback
- Construir comunidad

### Fase 2 (Mes 4-6): Freemium
- Introducir límites en free
- Lanzar Pro a $9.99
- Target: 100 usuarios pagos

### Fase 3 (Mes 7-12): Escalar
- Lanzar Studio a $29.99
- Marketplace de assets
- API para developers
- Target: 1,000 usuarios pagos

## Notas Críticas

- **NUNCA** gastar más de $2/día en APIs por usuario
- **SIEMPRE** usar Gemini primero (gratis)
- **Limitar** Kling/Runway a usuarios de pago
- **Monitorear** costos diarios con `budget_control.py`
- **Ajustar** precios según costos reales

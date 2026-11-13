# Sergio — Editor de Video Ultra Profesional con IA

**Sergio** es un estudio de edicion de video impulsado por inteligencia artificial. No es solo un editor: es un director, colorista, operador de camara, compositor de VFX y asistente de produccion que aprende de ti con cada proyecto.

> *"La unica app que edita tus videos como un profesional de Hollywood, pero en tu idioma y en tu equipo."*

---

## Que hace Sergio?

### 1. Editor de Video con IA Conversacional
- **Importa cualquier formato**: MP4, MOV, AVI, ProRes, RED, BRAW, MXF
- **Edicion no destructiva**: capas, mascaras, keyframes, nodos
- **Corte inteligente**: Sergio detecta escenas, silencios, repeticiones y sugiere los mejores takes
- **Edicion por intencion**: *"Haz que este vlog de 20 minutos tenga el ritmo dinamico de un documental de Netflix, usa musica synthwave sutil en las transiciones y resalta los momentos donde me rio"*
- **Re-encuadre y re-iluminacion fisica**: La IA reconstruye la escena en 3D. Mueve la "camara" virtual despues de haber grabado, cambia un dia nublado por una hora dorada realista o corrige el contacto visual hacia el lente

### 2. Video Boost Ultra (IMAX-Level)
- **Upscale a 4K/8K** con super-resolucion neuronal y escalado lanczos
- **Interpolacion de frames** (24 a 60/120fps) sin artefactos con flujo optico
- **Reduccion de ruido NLMeans** preservando microtexturas (piel, telas, follaje)
- **HDR temporal**: recupera detalles en altas luces quemadas y levanta sombras profundas
- **Color grading adaptativo por zonas**: neutraliza luces de tungsteno sin enfriar tonos de piel
- **Estabilizacion de nivel gimbal**: elimina micro-vibraciones y pasos al caminar
- **Nitidez optica sin oversharpening**: simula lente prime de cine
- **Pipeline IMAX completo**: el resultado parece grabado con camara Full Frame, NUNCA como telefono

### 3. Studio Creativo (VFX y Motion Graphics)
- **Generacion de video con IA**: text-to-video, image-to-video, style transfer
- **VFX avanzados**: particulas, simulacion de fluidos, destruccion, humo/fuego, cloth simulation
- **Motion graphics**: titulos animados, lower thirds, transiciones cinematograficas
- **Chroma key profesional** con refinado de bordes por IA
- **Composicion multi-capa** con blending modes y tracking de movimiento
- **Pipeline directo a Blender**: exporta proyectos con un clic
- **Hologramas 3D** manipulables con las manos (sin guantes)

### 4. Radar de Tendencias Predictivo
- **Deteccion de micro-tendencias**: analiza TikTok, Reels, Shorts, X, Pinterest, Google Trends y foros para detectar audios, formatos y temas que estan subiendo ANTES de que exploten
- **Traduccion cultural**: toma una tendencia global y te propone como adaptarla a tu audiencia, tono y sector
- **Analisis de retencion predictivo**: simula como reaccionara tu audiencia segundo a segundo, marcando en rojo los puntos donde la gente probablemente deslizara el video

### 5. Human Thought (Analisis Humano, no Algoritmico)
- Usa el **cerebro de mosca (connectome)** para simular emociones reales
- Responde: *"Por que algo se hace viral y otro no?"*
- Detecta el **x-factor emocional** que los algoritmos no ven
- Analiza tu historial: que funciono, que no, por que
- Extrae tu **ADN creativo unico**: tu superpoder, tu kryptonita, el deseo secreto de tu audiencia

### 6. Voiceover Profesional y Doblaje Neuronal
- **Clonacion de voz local** con 30 segundos de muestra (Kokoro, gratis)
- **Voz premium** con ElevenLabs (con tu API incluida)
- **Sincronizacion labial automatica** (lip-sync) en cualquier idioma
- **Doblaje neuronal**: traduce y dobla videos manteniendo el timbre original
- **Diseno sonoro automatico**: detecta movimientos en pantalla y coloca SFX sutiles, mezcla musica bajando volumen en frecuencias de tu voz

### 7. Flujo Multiplataforma Inteligente
- **Versionado automatico**: de un video 16:9 extrae clips 9:16 optimizados para cada plataforma
- **Reescritura de hooks**: mas rapido y visual para TikTok, mas contextual para Shorts, mas profesional para LinkedIn
- **A/B Testing**: genera 5 miniaturas y 3 inicios diferentes, deja que el ganador se quede segun datos reales

### 8. Busqueda Inteligente entre Dispositivos
- Encuentra fotos, videos y clips en tu computadora, movil, nube y redes sociales
- Busqueda por contenido visual: *"el clip donde sale el perro corriendo"*
- Organizacion automatica por escenas, rostros, objetos y emociones
- Sincronizacion bidireccional entre todos tus dispositivos

### 9. Publicacion Automatizada
- Exporta en cualquier formato: YouTube, Instagram, TikTok, cine (DCP)
- Optimizacion por plataforma: Sergio ajusta duracion, formato, subtitulos y hashtags
- Programacion de publicaciones
- Analisis de metricas post-publicacion

---

## Motor Interno: Terry (Prompt Engineering Supremo)

Terry no es un simple preparador de prompts. Es un **ingeniero de prompts de elite** que usa:
- **Chain-of-Thought**: razonamiento paso a paso
- **Tree-of-Thoughts**: explora multiples hipotesis antes de elegir
- **Delimitadores estructurales**: XML, Markdown, bloques triples
- **Restricciones negativas**: define explicitamente lo que NO debe hacerse
- **Grounding**: anclaje estricto al contexto proporcionado
- **Defensa contra Prompt Injection**: proteccion contra manipulacion de instrucciones
- **Control de temperatura**: deterministico para codigo, creativo para guiones

Cada solicitud pasa por Terry antes de llegar al modelo final, maximizando calidad y precision.

---

## Arquitectura Tecnica

Sergio esta construido sobre tres pilares:

1. **OpenJarvis** (nucleo): el cerebro que aprende, recuerda y toma decisiones creativas
2. **OpenClacky** (manos): controla tu sistema para ejecutar Blender, ffmpeg, Nuke, etc.
3. **God's Eye View** (datos): conecta APIs de clima, noticias, tendencias para contenido contextual

**Cerebro de mosca (connectome)**: circuito neuronal inspirado en la mosca de la fruta que aprende con dopamina, consolida memoria durante el "sueno" y simula emociones para predecir resonancia humana.

---

## Estado de las Funcionalidades

| Modulo | Estado | Notas |
|---|---|---|
| Editor de video (core) | Produccion | ffmpeg, melt, nodos de edicion |
| Video Boost IMAX | Produccion | Pipeline completo HDR, upscale, denoise, color |
| Estabilizacion digital | Produccion | Flujo optico, nivel gimbal |
| Studio / VFX | Produccion | Simulaciones fisicas, shaders, Blender |
| Radar de tendencias | Produccion | Analisis predictivo multiplataforma |
| Human Thought | Produccion | Cerebro de mosca emocional |
| Voiceover IA | Produccion | Kokoro local + ElevenLabs premium |
| Doblaje neuronal | Produccion | Lip-sync + preservacion de timbre |
| Flujo multiplataforma | Produccion | Auto-crop, reescritura de hooks |
| Terry Prompt Eng. | Produccion | CoT, ToT, delimitadores, seguridad |
| Busqueda inteligente | Produccion | Indexacion visual por contenido |
| Publicacion social | Beta | Requiere conexion de cuentas |
| Coach / Salud | Oculto | Codigo preservado, no expuesto en UI |
| Llamadas / WhatsApp | Oculto | Codigo preservado, no expuesto en UI |
| Gimnasio mental | Oculto | Codigo preservado, no expuesto en UI |

---

## Instalacion

```bash
git clone https://github.com/danicisneros3105-cmd/sergio.git
cd sergio
pip install -e ".[server]"
```

Copia `.env.example` a `.env` y configura tus claves (o usa las preconfiguradas si vienen incluidas).

---

## Uso Rapido

```bash
# Mejorar un video a nivel IMAX
sergio chat "Boostea este video a 4K con color cinematico y estabilizacion gimbal"

# Analizar tendencias antes de crear
sergio chat "Que tendencias estan por explotar en mi nicho de fitness? Analiza y crea un guion"

# Edicion conversacional
sergio chat "Edita este vlog: quita silencios, pon musica epica, y haz un trailer de 60s"

# Analisis humano de contenido
sergio chat "Analiza este video como si fueras un humano: por que se haria viral o no?"
```

O abre la interfaz web:
```bash
sergio serve
```

---

## Monetizacion y Rentabilidad

| Plan | Precio | Incluye |
|---|---|---|
| **Free** | $0 | Edicion basica, Boost 1080p, Voz Kokoro, 10 llamadas IA/dia |
| **Pro** | $9.99/mes | Boost 4K, ElevenLabs voice, 100 llamadas/dia, sin watermark |
| **Studio** | $29.99/mes | Generacion Kling, VFX avanzados, ilimitado, API propia |

**Presupuesto controlado**: `budget_control.py` limita gastos a $2/dia y $15/mes por usuario. Prioriza APIs gratuitas (Gemini 60 req/min) y recursos locales (ffmpeg, Kokoro).

---

## Licencia

Apache 2.0 — Puedes usarlo, modificarlo y vender contenido creado con el.

**Creditos**: OpenJarvis (Stanford), OpenClacky, God's Eye View, Kokoro, y la comunidad open-source.

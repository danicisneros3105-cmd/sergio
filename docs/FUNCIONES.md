# Todo lo que tiene Sergio

Lista del 2 de noviembre de 2026, hecha leyendo el código (118 herramientas
registradas, 19 neuronas, 14 skills empaquetadas y las páginas de la web).
Para saber con qué claves o programas funciona cada cosa, mire la columna
«Necesita».

**Cómo leer los estados**
- **Hecho**: está programado y tiene pruebas automáticas.
- **Con servicio**: además necesita una clave o cuenta de un tercero.
- **Windows**: solo en la app de escritorio de Windows.
- **Parcial**: hecho, pero falta algo (se dice qué).

**Aviso honesto.** «Hecho» significa que el código y sus pruebas existen. Las
pruebas usan simulaciones: casi nada se ha probado de punta a punta con
servicios reales (pagos, publicación, llamadas, cámara) ni con personas
reales. Eso es lo que debe hacer la beta cerrada.

---

## 1. Conversar

| Función | Estado | Necesita |
|---|---|---|
| Chat de texto con respuesta en vivo, estilo iMessage | Hecho | Una IA conectada |
| Tres apartados: Texto, Voz y Quick Chat (respuesta corta y rápida) | Hecho | — |
| Chat con cualquier modelo: Google, OpenAI, Anthropic, DeepSeek y cientos más por OpenRouter | Con servicio | Clave o «Conectar la IA con un clic» |
| Selector de modelo y esfuerzo | Hecho | — |
| Terry: entiende pedidos medianos y complejos y escribe el encargo a medida del modelo (con plan y comprobaciones, tope de 4 s) | Hecho | Un modelo rápido |
| Voz en vivo: Sergio escucha y responde hablando, solo si le hablan a él | Con servicio | Gemini Live o voz propia (Whisper + ElevenLabs/Kokoro) |
| Lectura en voz alta de cualquier respuesta | Con servicio | Voz |
| Trato elegible («señor», «señora», nombre, neutro, «tú»), idioma y país | Hecho | — |
| Proyectos: chats con instrucciones y archivos propios | Hecho | — |
| Tarjetas de aprobación en palabras simples | Hecho | — |
| Tarjeta de video en vivo en el chat (avance, resultado o motivo del fallo) | Hecho | — |
| Galería: abanico como vista previa y galería completa estilo Fotos (por día, visor con zoom), videos convertidos para que cualquier navegador los reproduzca | Hecho | ffmpeg para convertir |
| «Mi semana»: lo que de verdad hizo esta semana y lo que quedó a medias | Hecho | — |
| Artefactos: Sergio entrega páginas HTML (tablas, calculadoras, juegos) como tarjeta en el chat, en un marco aislado y sin red | Hecho | — |
| Constancia en el perfil: días seguidos y mejor racha, sana (sin culpa ni avisos) | Hecho | — |
| Puntero propio: Sergio señala lo que explica | Hecho | — |
| Paleta de comandos (Ctrl/⌘ K), atajos, pantalla dividida | Hecho | — |

## 2. Memoria y cerebro

| Función | Estado |
|---|---|
| Memoria que llega más allá de la ventana de contexto (engramas, enlaces que se refuerzan con el uso) | Hecho |
| Cerebro de mosca real (FlyWire v783, 139 255 neuronas, 1 066 822 conexiones) que decide cuánto pensar en cada turno | Hecho |
| Cuerpo fungiforme medido, dopamina y sueño que repasa lo aprendido | Hecho |
| Un cerebro propio por cada Node | Hecho |
| Estilo del dueño: aprende cómo escribe y ajusta las respuestas | Hecho |
| Memoria, grafo de conocimiento y búsqueda en documentos personales | Hecho |
| Superskills siempre activas (9 reglas) y skills empaquetadas (razonamiento, investigación, decisiones, código limpio, datos y gráficos, claridad, escritura humana, diseño, anatomía y otras) | Hecho |
| Sergio mejora su propio código con red de seguridad (copia aparte, ruff y pruebas, deshacer) | Hecho |
| Aprende lo que funcionó con cada herramienta (neuronas nuevas) | Hecho |

## 3. Nodes, enjambre y automatizaciones

| Función | Estado |
|---|---|
| Cuatro Nodes fijos: Rihno, Manchas, Hous y Tennessee, con memoria, reglas y rutinas propias | Hecho |
| Agent Swarm: muchos agentes en paralelo para una tarea | Hecho |
| Automatizaciones en tres pasos (cuándo, qué, quién), plantillas, varios pasos y lista de todas | Hecho |
| Rutinas que vigilan una web o una app y despiertan al Node solo si cambió algo | Hecho |
| Cowork: caja central, plan, autonomía, tope, archivos y registro | Hecho |
| Aprobaciones por Node: lo importante espera el sí del dueño | Hecho |
| Canales: Telegram, Discord, Slack y otros | Con servicio |
| Conectores y plugins (MCP remoto, OAuth, formato de plugins de Claude) | Con servicio |
| «Sus apps»: Gmail, Notion, Shopify, Calendar, Drive, Slack, GitHub, Figma, Canva, Stripe, Linear, Zapier (un toque) | Con servicio |
| Agente de código para tareas de programación en el equipo | Con servicio |

## 4. Imágenes, video y 3D

| Función | Estado | Necesita |
|---|---|---|
| Generar imágenes (Gemini, OpenAI, FLUX, Pollinations) | Con servicio | Clave |
| Fotos reales de internet con crédito (Pexels, Openverse, Wikimedia, Pixabay) | Hecho | Clave gratuita en algunas |
| Video rápido desde una idea, con subtítulos animados | Hecho | IA + ffmpeg |
| Video ensayo profesional (tratamiento, tomas, clips, voz de locutor, música, color, subtítulos con varias letras, control de calidad) en 4 modos y varios géneros | Hecho | IA, ffmpeg; varias horas |
| Escuela de video: mide segundo a segundo los videos de referencia y escribe una superskill por categoría | Hecho | Su PC |
| Edición profesional (`video_pro`: máster, color, interpolación) y montaje rápido (`video_edit`) | Windows | ffmpeg |
| Videos programados y subida a YouTube e Instagram con API oficial | Con servicio | Cuentas del dueño |
| Cine con IA toma por toma (Higgsfield) | Con servicio | Cuenta del dueño |
| Escenas de películas, miniaturas, títulos y radar de tendencias | Hecho | Clips: solo edición personal |
| Modelos 3D por piezas dentro del chat, y 3D en la nube (Meshy, Tripo, fal) | Con servicio | Clave |
| Blender, Unreal Engine 5, movimiento de personajes (NVIDIA) | Windows | Programas y GPU |
| Láminas «Anatomy» dentro del chat | Hecho | — |
| Diseño, código, planos, BIM: programas reales que Sergio abre | Con servicio | Se instalan aparte |

## 5. Control del equipo y de la pantalla (Windows)

| Función | Estado |
|---|---|
| Ver la pantalla y usar ratón y teclado como una persona; cualquier tarea en una web o programa | Windows |
| Guía en pantalla (flechas y círculos que se van con un clic) | Windows |
| Notch/isla con orbe, voz y trabajos en curso; compañero junto al cursor | Windows |
| Centro de control con botones rápidos y «En marcha» con botón de parar | Windows |
| Revisión del PC, ordenar archivos, duplicados de fotos, programas Python y PowerShell | Windows |
| Deshacer lo último que Sergio hizo (30 min) | Windows |
| Cámara: ver, reconocer personas (con su permiso), manos, hologramas | Windows (la ventana «Sergio ve» está escondida) |
| Dictado limpio y detección de a quién se le habla | Windows |
| Confirmar con Visage lo que no tiene vuelta | Windows |

## 6. Seguridad y cuentas

| Función | Estado |
|---|---|
| Registro e inicio de sesión: correo, teléfono, Google, Microsoft, Apple | Con servicio |
| Antifraude: correos temporales, equipo o red repetidos, verificación | Hecho |
| Visage: reconocimiento facial propio con movimiento de un solo uso y código de respaldo | Hecho |
| Llaves de acceso (WebAuthn) del propio dispositivo | Hecho |
| Bloqueo de Sergio con Visage o código | Hecho |
| Todo lo de afuera es 403 salvo cuentas y avisos firmados; XML y CSS endurecidos | Hecho |
| Claves de IA de clientes cifradas con AES-256-GCM | Hecho |
| Cifrado de datos sensibles (salud, recordatorios, caras, memoria, Nodes) en reposo | Hecho (`docs/SEGURIDAD.md`) |
| `sergio lanzamiento`: qué falta para publicar, separando código y pasos del dueño | Hecho (`docs/LANZAMIENTO.md`) |

## 7. Salud y bienestar

| Función | Estado |
|---|---|
| Hoy, medicinas, comida y ejercicio, metas y recordatorios | Hecho |
| Métricas, longevidad, explorar, compartir con el médico, dispositivos (anillo, enlace, archivos) | Hecho |
| Salud mental: tarjetas cortas y encuesta completa con escalas publicadas; las líneas de crisis salen al instante si hace falta | Hecho |
| Gimnasio mental (complemento que el dueño activa) | Hecho |
| Reuniones: grabar, acta y quién dijo qué | Hecho |

## 8. Conserje, investigación y finanzas

| Función | Estado |
|---|---|
| Investigación profunda con citas literales y contraste de fuentes | Con servicio |
| Conserje: restaurantes, viajes, ventas, mensajes en borrador; el último paso siempre espera su sí | Con servicio |
| Llamadas con la voz de Sergio (empiezan diciendo que habla una IA) | Con servicio |
| WhatsApp y mensajes: esperan el sí del dueño | Con servicio |
| Clientes y empleos: busca, puntúa y deja borradores; nada se envía solo | Hecho |
| Trading (Alpaca) en papel por defecto, con límites y prueba histórica | Con servicio |
| Datos en vivo: aviones, sismos, lanzamientos, clima, globo | Hecho |
| Calculadora exacta, matemáticas verificadas, intérprete de Python y 12 lenguajes | Hecho |
| Revisión de código, depuración, refactorización segura, pruebas primero | Hecho |

## 9. Planes y cobros

| Función | Estado |
|---|---|
| Cinco planes: Free, Go $5, Work $21, Dev $50–115, Founders $99–235 | Hecho |
| Cobros con Stripe, PayPal o Hyperswitch; libro sellado, recibos, devoluciones | Con servicio |
| Clave de IA propia por cliente, con tope mensual, creada sola | Con servicio |
| Modelos por plan (Free y Go rápidos, Work medios, Dev y Founders todos) | Hecho |
| Panel del dueño: ganancia por cliente con el gasto real de su clave | Con servicio |

## 10. Diseño y dispositivos

- Diseño «Cristal y burdeos» en claro y oscuro, minimalista y con animaciones suaves.
- Web instalable (PWA) en Windows, macOS, iPhone, iPad y Android.
- App de Windows con el Python oficial firmado.
- Funciona con modo liviano en equipos lentos.

## Lo que NO existe todavía (para no prometerlo)

- Sergio en la nube para clientes (hoy corre en el equipo del dueño).
- Instalador para Mac, iPhone y Android con control del dispositivo (esos sistemas no lo permiten a una app; solo funciona la web).
- Desbloquear Windows, macOS o el teléfono (ningún sistema lo permite a una app).
- Casa inteligente, «AGI», Vertu: no hay aparato ni servicio real detrás.
- Sincronización alojada y actualizaciones anticipadas: «Próximamente».
- Cifrado de todo lo sensible en reposo: ver el estado exacto en `docs/SEGURIDAD.md`.

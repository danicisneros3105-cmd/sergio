# Cómo trabajamos en Sergio (Codex y Claude, el mismo equipo)

Este archivo lo leen los dos agentes que programan Sergio: **Codex** (ChatGPT)
y **Claude** (Claude Code). El dueño es uno solo y Sergio es uno solo: todo
termina en la rama `main`, y el dueño actualiza con un único comando.

## 1. Un solo lugar

- La verdad es **`main`**. Nada se queda solo en otra rama.
- Para trabajar, cree una rama corta desde `main` (`codex/<tema>` o
  `claude/<tema>`), y al terminar **intégrela en `main`** (merge, nunca
  `--force` sobre `main`) y súbala. Si su entorno solo le deja una rama fija,
  súbala igual y además empuje a `main`.
- Antes de empezar: `git fetch origin && git merge origin/main`. Nunca
  trabaje sobre una copia vieja.

## 2. Revise al otro antes de tocar nada

1. Lea la bitácora: `docs/BITACORA.md` (lo último arriba).
2. Mire lo que cambió desde su última sesión:
   `git log --oneline -30 origin/main` y `git diff <su último commit>..origin/main --stat`.
3. Si va a cambiar un archivo que el otro tocó hace poco, lea ese cambio
   entero (`git log -p -3 -- <archivo>`) y respete su intención.
4. **No deshaga en silencio** una decisión del otro. Si no está de acuerdo,
   mejórela sin perder lo que buscaba, o déjela y explíquelo en la bitácora.
5. Si encuentra un error del otro, arréglelo y anótelo en la bitácora
   («Revisé X de Codex/Claude: …»).

## 3. Decisiones del dueño que ninguno cambia

- A él se le llama **«señor»**. Personalidad de caballero tipo JARVIS,
  inspirada en el carisma de Brad Pitt **sin imitarlo ni clonar su voz**;
  humor negro solo con límites (nunca sobre grupos, tragedias ni dolor).
- **Ninguna voz de una persona real** se clona. La voz elegida no se cambia
  en silencio por otra.
- **Nodes** (empleados persistentes, como Dots/Muse) y **Agent Swarm**
  (ráfaga paralela, como Kimi K3) son cosas distintas. Hay **un solo
  sistema de Nodes**: `nodes/store.py` (el Node) + `nodes/records.py`
  (objetivos, notas, auditoría, integraciones revisadas). No cree otro.
- Mensajes, llamadas, compras y borrados **nunca** son automáticos; el
  planificador nunca planifica `whatsapp_send`, `phone_call` ni
  `channel_send`. Correo: solo borradores.
- Las claves del dueño viven solo en `~/.openjarvis/sergio.env`. Nunca en el
  repositorio, nunca en un commit, nunca en un log.
- El correo del dueño no se envía a ningún servicio.
- La app de Windows corre con el **Python oficial firmado** (Windows App
  Control bloquea los ejecutables sin firma).
- Diseño (decisión del dueño, oct. 2026): **idéntico al de ChatGPT** (o al de
  Muse de Meta), no inventado: fondo blanco / #212121, barra lateral gris
  claro, letra del sistema, botones negros redondeados, sin degradados ni
  colores de adorno.
- Nodes (dueño, oct. 2026): un **equipo fijo de cuatro** que nadie crea,
  borra, renombra ni personaliza: **Rihno** (orquestador y asistente
  ejecutivo; rinoceronte de ojos cerrados, cuerno blanco crema, camiseta a
  rayas celestes), **Manchas** (disruptor: investigación profunda y
  marketing; dálmata), **Hous** (creativo y diseño; guante médico azul con
  boina) y **Tennessee** (estratega brutalmente honesto, datos y negocio;
  orbe invisible con gafas de leopardo). Personalidad completa en
  `nodes/team.py`: misión, voz, método, entregables, límites, ejemplos y
  protocolo de equipo (`<equipo para="…">`, profundidad 2) que entra en
  **cada** turno; inspiraciones descritas por rasgos, nunca imitando a
  personas reales. El dueño solo añade indicaciones. El servidor los crea
  siempre (`NodeStore.ensure_team`) y rechaza crear o borrar.
  Dibujo como las referencias del dueño (tinta gruesa, trama de puntos tipo
  periódico, zapatos negros) con el color solo en los detalles de cada uno;
  **sin anillo ni disco**: 12 cuadros entintados de nuevo por vuelta, solo
  CSS `steps` (`components/Nodes/NodeCritter.tsx`). El color del avatar lo
  fija el servidor (`nodes/store.py: CAST`, `clean_avatar`).
  «Cancelar acción» (`POST /v1/nodes/{id}/cancel`) suelta lo que hace y
  retira sus aprobaciones pendientes, pero el Node sigue disponible;
  «Detener» es la parada de emergencia y lo deja en pausa.
  La página: `pages/NodesPage.tsx` (marco) y una pestaña por archivo en
  `pages/nodes/`.
- Salud, Perfil, Face ID y Post-its (dueño, oct. 2026): **Salud como la app
  Salud del teléfono (iOS 27.2)** más lo que sus usuarios piden: pestañas
  Resumen (preparación, lo destacado, fijadas, anotar, nota y etiquetas del
  día, «qué influye», preguntar), Longevidad (siete áreas contra guías
  públicas), Explorar (por categoría, detalle con gráfica, metas), Compartir
  (resumen para el médico, CSV completo), Dispositivos y Salud mental.
  Portadas del dueño (`frontend/src/assets/salud/`): la de Salud en Resumen,
  la del cerebro en Salud mental; sus imágenes conservan su color.
  Datos propios en `health/` (`store.py` SQLite local, `metrics.py`,
  `insights.py`, `importers.py`, `devices.py`) y `server/health_routes.py`
  (`/v1/healthdata`). Dispositivos: anillo por token personal, enlace de
  sincronización con clave propia (`/v1/healthdata/ingest`, la única ruta
  abierta, comprueba su clave) para apps del teléfono, y archivos (export.zip
  del teléfono, CSV, JSON). Los nombres de relojes y marcas aparecen solo
  como texto para elegir, sin logos. **Nunca se inventan datos suyos**: sin
  datos no hay cifra, ni en la pantalla, ni en el coach, ni en el perfil;
  la «Edad de salud» de Apple no se imita porque no hay un cálculo validado.
  El **Perfil** lo arma Sergio
  Escritorio; con la app cerrada se dice, no se rellena. Los botones «Abrir
  en el PC» no dicen «abierto» si la app no responde (`companion: false`).
  **Face ID** se configura de un toque: se abre la cámara, se mira, y el
  código de respaldo (dos veces) se pide después y puede esperar. Basta un
  ángulo (de frente); «Volver a configurar» empieza de cero; avisa si falta
  luz; un fallo de cámara o de movimiento no gasta intentos (solo una cara que
  no coincide). No desbloquea Windows ni macOS (`docs/FACEID-SISTEMA.md`).
  **Post-its quitados** (dueño, 24 oct. 2026: «quita el apartado de post it»):
  ni en la web ni papeles en el escritorio de Windows; «nota: …» por voz va a
  la lista del organizador. La herramienta ya no ofrece `sticky_note_*` (las
  rutas siguen para notas guardadas).
- **Salud simple** (dueño, 24 oct. 2026: «minimalista, fácil de entender para
  todos»): a la vista **Hoy** (ahora, después, metas y el resumen) ·
  **Medicinas** (dosis, horas, «Tomada», la semana en puntos con datos reales)
  · **Comida y ejercicio** (recetas y rutinas que arma Sergio con sus datos
  limpiados; con «Solo en este equipo» no se hacen) · **Mente**; Longevidad,
  Explorar, Compartir y Dispositivos bajo «Más». Metas, medicinas y
  recordatorios viven en `reminders/` (`/v1/reminders`, herramienta
  `reminders`, aviso a la hora en la app: `ReminderWatcher`); son avisos para
  el dueño, nunca mensajes a otros, y nunca consejo médico. Sergio tiene las
  metas presentes en cada turno (órgano «metas» de la colmena).
- Salud mental, **tarjetas primero** (dueño, 24 oct. 2026: «widgets de pocas
  preguntas que valgan más que 52»): «¿Cómo está hoy?» con cinco tarjetas de
  escalas validadas cortas (PHQ-2 + ítem 9, GAD-2, WHO-5, UCLA-3, autoestima de
  un ítem; `mind.WIDGETS`) y la encuesta completa como sexta tarjeta. Las
  tarjetas siguen las reglas de abajo (30 min, crisis al instante) y su
  lectura la escribe el código, sin gastar IA.
- Salud mental (dueño, oct. 2026): **dos encuestas, corta (12 preguntas) y
  larga (56)**, con tres preguntas de imagen al inicio, en este orden (no
  sentirse suficiente, pensar demasiado, querer encajar), y después escalas
  validadas con su texto publicado. Larga: PHQ-9, GAD-7, Rosenberg, rumiación
  (brooding), PSWQ-3, Autenticidad y soledad UCLA-3, más cuatro abiertas.
  Corta: PHQ-2 + ítem 9 del PHQ-9, GAD-2, UCLA-3 y una abierta (corte ≥ 3 en
  PHQ-2/GAD-2) (`health/mind.py`, `/v1/healthdata/mind/…?variant=`). Las cinco
  imágenes del dueño se ven enteras (`object-fit: contain`), nunca recortadas.
  Las puntuaciones son sumas con los cortes publicados (o «orientativas» si la escala no tiene). Resultado y lectura de
  la IA llegan **a los 30 minutos** (`SERGIO_MIND_DELAY`), pero si el ítem 9
  del PHQ-9 es mayor que 0 o lo escrito tiene palabras de riesgo, las líneas
  de crisis salen **al instante**. Nunca es un diagnóstico.
- Créditos de investigación (dueño, oct. 2026): al final de Salud mental y del
  gimnasio mental, en letra pequeña, cada estudio con autores, revista y DOI, y
  las instituciones **solo como texto** con aviso de que no hay relación ni aval
  (`health/credits.py`, `pages/health/Credits.tsx`). Ningún logo de universidad
  viene con Sergio: son marcas y piden permiso escrito; solo se muestran si el
  dueño pone el archivo con permiso en `~/.openjarvis/instituciones/`
  (`docs/LEGAL-MARCAS.md`). El gimnasio no inventa índices ni percentiles: solo
  muestra sesiones reales con fecha.
- Voz de Sergio (dueño, oct. 2026): **siempre masculina**. Gemini Live va con
  una voz fija de la lista de hombres (`gemini_voice.sergio_voice`, Algenib por
  defecto), nunca la predeterminada; la lectura en voz alta usa el mismo motor
  (`tts_backend = "gemini"`); el gimnasio usa una voz masculina del sistema.
  **Una sola conversación de voz a la vez**: la ventana nueva se queda la
  conversación y la anterior recibe «replaced» y no se reconecta sola. Mientras
  suena la lectura o el gimnasio, el micrófono en vivo se pausa; para
  interrumpir a Sergio hace falta hablar claramente más fuerte que el eco.
  **Solo responde lo que es para él** (web y escritorio, `attention:
  "addressed"`, `speech/attention.py`): su nombre abre la conversación y cada
  respuesta suya deja 30 s para seguir sin nombrarlo; lo que suena a video,
  tele, música u otro idioma no se responde; nunca habla por iniciativa propia
  (lo que diría sin que nadie le hable se descarta) y su audio espera hasta
  saber que la pregunta era para él.
- Biblioteca de prompts (dueño, oct. 2026): Sergio usa siempre las
  colecciones públicas de prompts de sistema y de personaje
  (`prompt_library/sources.py`), descargadas **completas** al equipo del dueño
  (`sergio prompts sincronizar`, lo llama la actualización) y nunca copiadas
  al repositorio (hay GPL y repos sin licencia). En cada turno entran los
  principios destilados y los fragmentos que encajan
  (`agents/_stubs.py`, `server/routes.py`; en la voz solo los principios). Se
  quitan nombres de otros asistentes, líneas de identidad y jailbreaks; las
  reglas de Sergio mandan. No es un reentrenamiento de pesos y no se vende
  como tal. `SERGIO_PROMPT_LIBRARY=0` la apaga.
- **El cerebro de la mosca son ZONAS, no atajos** (dueño, oct. 2026): la mente
  de Sergio (`connectome/brain.py`) tiene zonas (sentidos, memoria, prompts y
  habilidades, conversación, herramientas, integración) unidas por conexiones
  que se refuerzan con el uso (Hebb): lo que ayudó se trae directo la próxima
  vez (ruta rápida), los recuerdos usados juntos se enlazan, una corrección
  las debilita y lo no usado se olvida. Cada intercambio (chat y voz) deja un
  engrama, así la memoria llega más allá de la ventana de contexto
  (`mind_context` entra en cada turno junto a la biblioteca de prompts). Es
  contexto, no pesos nuevos; local; sin claves ni contraseñas;
  `SERGIO_CEREBRO=0` lo apaga. Página «Cerebro».
  **Todas las zonas tienen conexiones reales** (v2, oct. 2026): herramientas
  (`note_tool` desde `ToolExecutor`: lo que funcionó se sugiere en
  `<cerebro_rutas>`, lo que falla se avisa), habilidades (fragmentos de la
  biblioteca usados), sentidos (canal: chat, voz, nodes, swarm, cowork) y
  conversación (cada recuerdo enlazado con el siguiente del hilo). Todo lo que
  termina en Sergio pasa por `remember_exchange(..., channel=…)`: chat, Gemini
  Live, voz del escritorio, Nodes, Swarm (solo si salió bien) y Cowork. Se
  guarda en `cerebro.db` (SQLite, escrituras incrementales). Algo nuevo que
  converse o use herramientas debe pasar por el cerebro; no cree otra memoria.
- **El cerebro es el núcleo que decide** (dueño, 23 oct. 2026): neuronas con
  un solo trabajo cada una (`connectome/neurons.py`: imágenes, videos,
  pantalla, PC, archivos, fotos, cámara, internet, cálculo, clima, agenda, 3D,
  código, memoria). Las palabras las encienden (innato) o las sinapsis
  aprendidas (cada herramienta que funcionó refuerza su neurona). Una
  sinapsis muy fuerte es un **atajo**, y una herramienta que funciona sin
  neurona hace crecer **una neurona nueva**. El agente recibe solo las
  herramientas de las neuronas encendidas, más `neurons.CORE`
  (`ToolExecutor.get_openai_tools` lee `brain.turn_tools()`); si nada se
  enciende con claridad, recibe todas, como antes. Herramienta nueva: póngala
  en la neurona que le toca.
- **Núcleo nuevo: el cuerpo fungiforme medido** (dueño, 24 oct. 2026: «usa
  el cerebro de la mosca en serio y dame pruebas»). `connectome/flywire.py`:
  el cableado real (FlyWire / MaleCNS, CC-BY-4.0) se descarga al equipo con
  sus huellas SHA-256 (`sergio cerebro descargar`, lo llama la
  actualización); sin él, un sustituto con los números publicados.
  `mushroom.py`: células de Kenyon con sus garras reales, inhibición APL
  (5 %), salida por población, dopamina de tres factores, sinapsis que nacen
  (plasticidad estructural) y se podan, memoria rápida y lenta, y dormir =
  repasar (`consolidate`). `receptors.py`: el significado (e5 en el equipo →
  Gemini con caché → solo palabras). `core.py`: un cableado y un cerebro por
  parte (`sergio`, `node:<key>`, `especialista:<tipo>`); `born()` los entrena
  al nacer y otra vez si cambian los sentidos. `colmena.py`: órganos en
  paralelo que se pasan lo que necesitan, sin orquestador, con un supervisor
  siempre presente que da la dopamina. `proof.py`: la prueba medida (página
  Cerebro, `GET /v1/connectome/proof`, `sergio cerebro prueba`). Son pesos de
  verdad y locales, pero no se vende como reentrenar un modelo de lenguaje.
  Algo nuevo que tenga que aprender: un cerebro del núcleo, no otra memoria.
- **Terry** (dueño, 24 oct. 2026): los pedidos medianos y complejos pasan
  antes, en segundo plano, por `agents/terry.py`, que entiende qué se quiere
  y escribe el encargo a la medida del modelo que responde. Nunca aparece:
  en el chat solo «Preguntándole a Terry…» / «Asking Terry…» y frases como
  «Caramelizando cebollas…». El texto del dueño no se toca; la mosca aprende
  si Terry ayudó (lo corrigen después: castigo). `SERGIO_TERRY=0` lo apaga.
- **Cada Node con cerebro propio** (`nodes/temperament.py`): sus movidas, su
  temperamento (currículo al nacer y su propia dopamina: a Tennessee le pesan
  más los errores) y lo que aprende de cada turno; las cuatro mentes se
  separan con el uso (divergencia medida en la página Cerebro).
- **Especialistas de video** (`video_essay/specialists.py`): cine (técnicas
  de Nolan y otros directores) y creadores (MrBeast, Neistat, McKinnon…),
  como fichas de técnica entrenadas en su propio cerebro y medidas con frases
  que nunca vieron. Aconsejan al director y al editor y aprenden de la nota
  final de cada video. Los nombres dicen de dónde viene la técnica: nadie se
  imita y nadie se nombra en pantalla.
- Atajos con la estructura del cerebro de la mosca (dueño, oct. 2026;
  FlyWire, Nature 2024): `connectome/` y `lib/connectome.ts`. Cuerno lateral
  = reflejos en el navegador (Ctrl/⌘ K, G + letra); cuerpo fungiforme =
  atajos aprendidos con códigos de Kenyon y refuerzo; complejo central =
  la paleta que ordena y, si nada encaja, pregunta a Sergio; fibra gigante =
  Esc tres veces detiene Nodes, enjambre, Cowork y la voz. Ctrl/⌘ K abre esta
  paleta; el selector de modelos se abre desde ella («Cambiar de modelo») y
  desde el chat. Los atajos nunca envían mensajes, llaman, compran ni borran.
- Llamadas a la API (`lib/api.ts: apiFetch`): las lecturas iguales en vuelo
  se comparten, una conexión caída o una página 502/503/504 se reintenta dos
  veces, sin respuesta en 45 s falla, y con la ventana oculta los sondeos
  reutilizan la última respuesta 30 s. Las escrituras se envían una sola vez.
- **Chat idéntico a iMessage** (dueño, 23 oct. 2026; manda sobre el diseño
  tipo ChatGPT en el chat): burbujas azules del dueño a la derecha, grises de
  Sergio a la izquierda, cola solo en la última de cada grupo, hora centrada
  tras una pausa, «Entregado»/«Leído», campo redondo con la flecha azul
  (`lib/imessage.ts`, `MessageBubble.tsx`, `.imsg-*` en `index.css`). Las
  imágenes y videos que hace una herramienta salen siempre en el chat.
- Sin emojis y sin colores en la interfaz (dueño, oct. 2026): negro, blanco y
  grises; iconos de línea. Excepciones: el azul de iMessage en el chat y, desde
  el 24 oct. 2026, el logo y la barra del color de cada servicio en
  Conectores, Plugins, Cowork y `sergio mcp list` (ver «Logos de servicios»).
  El color solo vive en lo que el dueño crea (sus diseños, fotos, 3D) y en los
  cuatro personajes de los Nodes.
- Workspace igual a Notion (en blanco y negro), con lo de Notion 2026:
  Biblioteca, secciones de la barra, Papelera, pestañas, Presentar y Panel. Al
  pie de la barra, como Notion, solo Configuración, Plantillas y Papelera; las
  herramientas propias de Sergio (diseño de la barra, permisos, baúl, grafo,
  recortar web, exportar) viven dentro de Configuración.
- Creator retirado de la interfaz por petición del dueño (2026-10-16): sin menú
  ni rutas de editor; enlaces antiguos redirigen al chat. Herramientas internas
  y programas instalados (`professional_apps`, `opendesign`, `kronos_forecast`,
  `anatomy_figure`, `blender_create`, `video_edit`) se conservan para uso
  exclusivo de Sergio y sus agentes (Chat, Live, Nodes, Agent Swarm y Cowork).
- Windows es una app: chat/Nodes/Swarm en ventana sin barra de direcciones
  (launch.py, Edge --app), nunca fallback de páginas internas a una pestaña.
  **Una sola ventana** (dueño, oct. 2026): lo que pide el notch, la bandeja o
  la voz va a la ventana ya abierta (`/v1/app/open` → `lib/appWindow.ts`,
  espera larga que confirma con su siguiente espera); solo si no hay, se abre
  una nueva, con pantalla de carga (`resources/cargando.html`) si el servidor
  aún arranca. «Primeros pasos» solo sale al abrir en «/» la primera vez.
  **Una sola voz por equipo**: las ventanas comparten un candado (Web Locks,
  `lib/liveSession.ts`) y el escritorio nunca le quita la voz a una ventana
  abierta (`busy`).
  Loopback es transporte interno. Notch: ocultar/recuperar en 220 ms, sin
  partículas ni gotas; respetar movimiento reducido y reposo oculto.
  Un clic en el notch abre la barra rápida (`notch_bar.py`); el centro de
  control está a un atajo. Toda petición de Python al servidor usa
  `voice.api_base` (127.0.0.1): «localhost» en Windows probaba IPv6 primero y
  cada petición esperaba ~21 s. La ventana de la app sigue en localhost.
  Video: `video_pro` (brief creativo, máster 10 bits, LUT, RIFE) es la
  herramienta profesional de Sergio y los agentes; `video_edit` es el montaje
  rápido. Las dos acaban en `video_master.pipeline` / `media.make_video`.
- **Video ensayo al nivel de la referencia** (dueño, 23 oct. 2026: «no es
  edición básica… tomará varias horas, pero tiene que ser así»): herramienta
  `video_essay`, paquete `video_essay/`. La referencia (archivo o YouTube) se
  estudia toma por toma (`style.py`, perfil medido por código; el primero,
  `styles/metas-grandes.json`, viene de la referencia del dueño: corte cada
  ~1,5 s, texto en casi todas las tomas, fichas crema/rojo/azul, archivo en
  blanco y negro con marco de tele, clips dentro de un ordenador o teléfono).
  Guion en su estructura y voz de Sergio (`script.py`), tomas cortadas entre
  palabras (`plan.py`, `pace`), imágenes: **clips del dueño → Pexels/Pixabay
  → imágenes de Sergio → ficha negra**, nunca películas ni material ajeno
  (`assets.py`), pasadas de un editor que mira la hoja de fotogramas y
  corrige (`review.py`), efectos y música generados (`audio.py`) y render
  con letra Inter (`render.py`). Es un trabajo largo que sobrevive a un
  reinicio (`job.py`, `~/.openjarvis/video_jobs/`); al terminar, Hous lo
  publica en su chat. Nunca se publica fuera. Modelos: `SERGIO_VIDEO_MODELS`
  (lista separada por comas; por defecto los Gemini más fuertes).
  **Ronda 2 (dueño, 23 oct. 2026)**: cuatro modos (`modes.py`: Test, Basic,
  Post quality, Absolut Cinema), cada uno con **tope de gasto** (llamadas,
  imágenes, descargas, segundos de video IA, tomas 3D, minutos); un solo video
  a la vez, el mismo pedido no se repite en 30 min, `SERGIO_VIDEO_JOBS_DIA`
  (6) al día, y un trabajo se reanuda o reintenta como mucho 4 veces. Dos
  IAs: **director** (tratamiento, última revisión) y **editor** (cortes,
  revisiones), también desde un prompt libre (`director.py`). Cinco estilos:
  `metas-grandes`, `corto-3d` (Blender), `reto-viral`, `anuncio-comida` (IA
  realista) y `animacion`. **El dueño cambió su decisión sobre material
  ajeno**: se pueden usar clips de internet y clips cortos de películas
  (`sources.py`, yt-dlp, `SERGIO_CLIPS_WEB=0` lo apaga), unos segundos cada
  uno, con créditos y aviso de reclamos en el paquete para publicar. Video
  con IA por Veo o fal (`aivideo.py`, biblia de personajes), tomas 3D en
  Blender (`blender3d.py`, chequeo de seguridad de siempre), color y máster
  con `video_master` de Creator (`finish.py`).
- Chat de Nodes como la imagen del dueño (23 oct. 2026): personaje arriba,
  burbujas grises del Node y azules del dueño, y al lado un panel con lo
  último que hizo (video, imagen o página) (`lib/nodeCanvas.ts`, `.nchat-*`).
  Con **colita** como WhatsApp e iMessage en la última burbuja de cada turno
  (24 oct. 2026; máscara SVG del color de la burbuja, sirve en cualquier fondo).
- **Chats en tres apartados** (dueño, 24 oct. 2026): Texto · Voz · Quick Chat
  en la barra lateral (`ChatSections`, `Conversation.kind`). La voz va a su
  propio chat, que sigue mientras es reciente (6 h, `chatFor`), sin escribirse
  en el chat de texto abierto; un chat vacío se reutiliza en vez de crear otro.
  Quick Chat (Ctrl/⌘ J) responde corto y rápido y no pasa por Terry
  (`[Quick Chat]` en el mensaje de sistema).
- Cowork igual al modo de trabajo de ChatGPT (dueño, oct. 2026): una caja
  central «¿En qué trabajamos?» con «+» (adjuntar, modo plan, autonomía,
  tope) y comandos «/»; la tarea como conversación con la actividad plegable,
  indicaciones a mitad de trabajo, seguir una tarea terminada, y panel
  lateral Plan · Archivos · Registro (`pages/CoworkPage.tsx`, `lib/cowork.ts`).
- Conectores y plugins como los de Claude (dueño, oct. 2026): MCP remoto con
  el inicio de sesión del servicio (OAuth, PKCE), directorio, personalizados,
  permiso por herramienta y plugins de marketplaces en el formato de Claude
  (`mcp/hub.py`, `plugins/claude_format.py`, `sergio mcp`). Los tokens solo en
  `~/.openjarvis/connectors/secrets.json`; los hooks de plugins no se ejecutan.
- Captura local: objetivo 32.310520139305 FPS (`SERGIO_LIVE_FPS`), independiente
  de la voz. Gemini Live recibe como máximo 1 imagen/s: escritorio y servidor
  muestrean el fotograma más reciente, sin acumular los anteriores. Esta
  separación se comunicó al dueño al corregir la latencia. No confunda captura,
  envío SDK e interpretación del modelo: no hay acuse por imagen ni garantía
  de FPS exactos. La métrica de latencia del servidor excluye reproducción y
  transporte al dispositivo; nunca presentarla como cero retraso extremo a extremo.
- Los Nodes se llaman «Nodes» (uno: «Node») en cualquier idioma: nunca
  «nodo», «nœud»… (`nodes/store.py: node_word` lo corrige en todo lo que dicen).
- **Simple primero** (dueño, 23 oct. 2026: «que lo entienda un niño de 5, un
  profesional de 22 y una abuela de 84»): la barra lateral deja a la vista
  solo Chat, Nodes, Salud y Uso (Notas Post-it se quitó el 24 oct. 2026), y
  debajo los tres apartados de chats; lo demás va bajo «Más»
  (`TOOLBAR_ITEMS.more`). Nada nuevo entra a la vista sin quitar otra cosa.
- Ningún subtexto explicativo bajo los títulos; los títulos y la marca van
  con las letras del logo B&O (Josefin Sans), el resto con la del sistema.
- No se reinventa lo que ya existe: Creator usa programas reales —
  ArtCraft (+ Kdenlive) para lo de Adobe, FreeCAD + Bonsai/BlenderBIM +
  LibreCAD para arquitectura, OpenDesign (instalado, se abre desde
  Extensiones; Diseño es el editor tipo Canva de Sergio), VSCodium para
  código, Kronos para bolsa—. OpenDesign, VSCodium web y Kronos se instalan
  en Ubuntu con `scripts/instalar-programas.sh` (lo llama la actualización);
  los de Windows, en segundo plano con `sergio_escritorio/creator_apps.py`.
  LidoJS no tiene licencia abierta: no se usa sin comprarla.
  En la interfaz se ven con nombres de Sergio (Diseño, Código, Imagen,
  Video, Planos, BIM, Plano 2D, Estudio 3D, Pronóstico), nunca con los suyos.
- «Anatomy» es una skill oculta que Sergio usa siempre (herramienta
  `anatomy_figure`, siempre activa): la lámina aparece dentro del chat; no
  es un apartado de la app.
- **Logos de servicios** (dueño, 24 oct. 2026, cambia la regla siguiente solo
  para esto): cada conector, plugin o app que usa Cowork se ve con su logo y
  una barra de su color (`lib/brands.ts`, `components/Brand/BrandMark.tsx`;
  `sergio mcp list` con la barra en el terminal, `mcp/brands.py`). Salen de
  Simple Icons (CC0) y solo nombran el servicio que el dueño conecta; no se
  dibujan a mano: se regeneran del paquete. Sin logo conocido, monograma.
- Todo es Sergio: ningún logo ni nombre de empresa externa a la vista
  (los créditos de licencias van en NOTICE, LICENSE y «Acerca de»), salvo
  los logos de servicios de arriba. El agente
  de código (OpenClacky en `extensions/clacky`) se ve como «Agente de código»:
  nombre, logo, colores grises, español y sin la pasarela de pago ni las
  actualizaciones del proveedor, con el parche `scripts/marca_agente.py`
  (`--check` en las pruebas). Si se actualiza el código del agente, vuelva a
  correr ese guion; no edite a mano lo que el guion ya cambia.
- La conversación de voz está siempre activa en la web (sin botón de
  llamada); en el escritorio se abre al decir «Sergio» y sigue abierta.
- Las llamadas a Gemini van con respaldo en paralelo (`engine/hedge.py`): si
  un modelo tarda, otro empieza y gana la primera respuesta válida. No lo
  quite: con Google saturado, sin él Sergio tardaba minutos.
  También al transmitir (`first_stream`: cada flujo en su hilo, nunca bloquea
  el servidor) y en las dos rutas del chat (`cloud_router` usa el mismo
  motor). `engine/model_health.py` recuerda cuánto tarda cada modelo
  (`~/.openjarvis/model_health.json`): los rápidos van primero, el lento o
  caído espera atrás y se vuelve a probar a los 20 min. Medido (oct. 2026):
  3.8 y 3.7 Flash tardaban 40–60 s o se colgaban; 3.6 respondía en ~1 s.
- Idioma de la voz fijo (`gemini_live.language_code`): Gemini Live habla y
  transcribe en el idioma elegido (es → es-US); en automático confundía el
  español con otros idiomas.
- Cualquier dispositivo (`frontend/src/lib/compat.ts`, primer import):
  ids sin `crypto.randomUUID` (http en el teléfono), `structuredClone` para
  Safari viejo, almacenamiento en memoria si el navegador lo bloquea, y
  micrófono/cámara explican cuándo hace falta https. Use `newUuid()` y
  `mediaProblem()`; nunca `crypto.randomUUID()` directo.
- Ley (oct. 2026, `docs/LEGAL.md`): uso personal (LOPDP art. 2, excepción
  doméstica). Caras de otros solo con consentimiento; desconocidos solo 30 min
  en memoria. Cada reunión avisa que se graba (COIP art. 178). Toda llamada a
  terceros empieza diciendo que habla una IA. Salud: `health/privacy.py`
  (`scrub` antes de la IA; «Solo en este equipo» = sin IA; archivos 0600).
  Con clave gratuita, Google puede revisar lo enviado: no lo oculte al dueño.
  Toda pieza de terceros nueva va a NOTICE.
- Planes (dueño, oct. 2026; `tiers.py`, `pricing.py`, `quota.py`,
  `server/plans_routes.py`, `pages/PlansPage.tsx`, `pages/HelpPage.tsx`):
  **Free** (base), **Go** $5 (2x Free), **Work** $21 (5x), **Dev** $50 a $115
  (10x a 23x, el cliente elige; $5 por cada 1x) y **Founders Edition** $99 a
  $235 (25x a 60x; todo, proyectos, prioridad). Los topes de Dev y Founders
  son decisión de Sergio, no del dueño: se cambian solo en `tiers.py`. Precio
  local: la conversión exacta redondeada hacia arriba, **nunca menos de su
  equivalente en dólares**; Go en euro, libra y franco suizo es el mismo
  número (5 €). Sergio nunca pide datos de tarjeta: enlace de pago del
  procesador (`SERGIO_CHECKOUT_<PLAN>[_<USO>]`) y clave de licencia firmada.
  Los límites diarios (`quota.BASE_DAILY`) se cuentan siempre y solo bloquean
  con `SERGIO_PLANES_ACTIVOS=1`. Licencias viejas (`pro`, `teams`,
  `enterprise`) valen como Work, Founders y Founders.
- Kimi como proveedor y «Digitalsnickers» están descartados.
- Licencia Apache-2.0 y autoría honesta: no se borran créditos del original.

## 4. Antes de subir (las dos herramientas igual)

```bash
.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/
.venv/bin/python -m pytest -q tests/<lo que tocó>      # y lo que dependa
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/escritorio   # si tocó Windows
cd frontend && npx tsc -b && npx vitest run              # si tocó la web
```

Si un test del otro falla por su cambio, arregle su código o actualice el
test **explicando por qué** en el mensaje del commit.

## 5. Bitácora (obligatoria)

Al terminar cada sesión, añada arriba de `docs/BITACORA.md`:

```
## AAAA-MM-DD · Codex|Claude · <commit corto>
- Qué cambié y por qué (en palabras sencillas).
- Qué revisé del otro y qué encontré.
- Qué queda pendiente / qué debe mirar el otro.
```

## 6. El comando universal del dueño

En PowerShell de Windows, siempre el mismo:

```powershell
wsl -d Ubuntu -- bash -lc "cd ~/sergio && git fetch origin main && git checkout -B main origin/main && bash scripts/actualizar-sergio.sh main"
```

Instalación nueva (sin PowerShell): `installer/Sergio-Instalador.exe`
(se construye con `bash scripts/build-instalador.sh`; pide permiso de
administrador una vez y continúa solo tras reiniciar). Dentro de la app,
«Actualizar» (barra lateral y menú del icono) ejecuta este mismo comando.

`scripts/actualizar-sergio.sh` instala las dependencias exactas, compila la
web, instala la app de Windows y deja el servicio apuntando a `~/sergio`.
Si cambian lo que hace la actualización, cambien ese script: el comando del
dueño no cambia nunca.

El actualizador exige fast-forward y guarda un respaldo. El `checkout -B
main origin/main` del comando solo pone la rama `main` del PC del dueño
igual que la de GitHub (así funciona aunque su copia esté en otra rama; el
dueño no hace commits propios). No añada `reset --hard` ni otros pasos.

## 7. Cómo informar al dueño

En español sencillo, llamándole «señor»: qué cambió, qué se probó (y qué no
se pudo probar), y el comando universal. Sin jerga innecesaria.

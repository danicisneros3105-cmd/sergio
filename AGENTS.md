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
  colores de adorno. **Cambiado el 26 oct. 2026** («que no se vea triste
  pero tampoco maximalista, usa Apple de referencia»): la contención de
  Apple — lienzo gris claro (#f5f5f7) y tarjetas blancas (de noche negro y
  #1c1c1e), texto casi negro, **un solo acento: el azul del sistema**
  (#007aff / #0a84ff) en lo que se pulsa o está elegido (botones, iconos de
  la barra lateral como en un Mac, fila elegida, pestaña activa), y verde,
  naranja y rojo del sistema solo para decir cómo salió algo. Nada de
  degradados ni fondos de color. Es la última capa de `index.css`
  («Apple look»); los tokens nuevos van ahí.
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
- **La base es el cerebro real de una mosca, no uno humano** (dueño, 26 oct.
  2026: «sobre el cerebro no es uno humano, es un cerebro real mapeado por
  Google (el cerebro de una mosca)»; reemplaza la decisión del 25 oct. de
  imitar un cerebro humano y la capa H01, que se quitaron).
  `connectome/decision.py` decide cada turno antes de llamar al modelo, con
  las partes de la mosca que hacen ese trabajo: lóbulo antenal (código ralo y
  novedad), cuerno lateral (prisa, peligro, ánimo y cautela aprendida),
  cuerpo fungiforme (los engramas de `brain.py`) y sus lóbulos α/β
  (conceptos que se forman al dormir), complejo central (el tema en curso,
  la duda → camino cuidadoso, y el integrador que predice cuánto tarda),
  neuronas de salida con dopamina PAM/PPL1 (reflejo / responder /
  reflexionar / a fondo), octopamina, acetilcolina, serotonina y sueño. Lo
  que llega cruza el **cableado real** de `connectome/mosca.py`: FlyWire
  versión 783 (reconstrucción de Google, corrección de Princeton y el
  consorcio, CC BY 4.0), 49 434 neuronas fuera de los lóbulos ópticos y sus
  573 006 conexiones de 10 o más sinapsis, en `connectome/data/mosca_*` con
  SHA-256 (`scripts/mosca_cerebro.py` las rehace desde el bucket público). El
  signo sigue al transmisor (acetilcolina excita; GABA y glutamato inhiben)
  y queda encendido ~2 %. Lo aprendido se guarda en
  `~/.openjarvis/connectome/mosca` (lo del antiguo `humano` se muda solo).
  `SERGIO_MOSCA=0` quita solo el cableado; `SERGIO_CEREBRO=0` todo. Prueba en
  la página Cerebro, `/v1/connectome/proof` (`mosca`, `mosca_viva`) y
  `sergio cerebro prueba`. No es una simulación del comportamiento de la
  mosca ni un cerebro humano, y no se vende como tal. Cada prueba nace con un
  cerebro nuevo (`tests/conftest.py`). Algo nuevo que converse: pasa por
  `mind_context` y `remember_exchange`, nunca a su lado.
- **Terry** (dueño, 24 oct. 2026): los pedidos medianos y complejos pasan
  antes, en segundo plano, por `agents/terry.py`, que entiende qué se quiere
  y escribe el encargo a la medida del modelo que responde. Nunca aparece
  (26 oct. 2026: el nombre «Terry» no le decía nada a la gente): en el chat
  «Entendiendo lo que necesitas…» y frases de lo que de verdad pasa
  («Revisando los detalles…»), nunca bromas sin sentido. El texto del dueño no se toca; la mosca aprende
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
- Sin emojis (dueño, oct. 2026); iconos de línea. Colores: solo los del
  diseño Apple de arriba (26 oct. 2026), antes negro, blanco y grises. Excepciones: el azul de iMessage en el chat y, desde
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
- **Cuentas** (dueño, 24 oct. 2026): inicio de sesión y registro en `/entrar`
  con correo, teléfono (Twilio Verify) o Google/Microsoft/Apple (OIDC + PKCE,
  firma comprobada con JWKS) — `accounts/`, `/v1/cuentas/*`, `sergio cuentas`.
  La **primera cuenta creada en este equipo es la del dueño**; las demás
  quedan «pendiente» hasta que el dueño las aprueba (un túnel no cuenta como
  local). Antifraude: correos temporales (lista CC0 + semilla), correo
  canónico (puntos y +etiquetas), mismo equipo/red/teléfono en varias
  cuentas → verificar, revisar o bloquear. Contraseñas con scrypt; códigos y
  tokens guardados con HMAC, nunca en un log. `SERGIO_EMAIL_SOLO_SEGUROS=1`
  acepta solo proveedores seguros. Los proveedores y el SMS necesitan sus
  claves en `sergio.env`; sin ellas el botón no sale.
- **Vista** (antes «Sergio ve», dueño 24 oct. 2026): nombre corto y controles
  mínimos (una píldora de iconos redondos); sin el recuadro con el nombre que
  seguía a la cara en la vista limpia. Los recuadros solo salen en «detalle».
- **Pantalla dividida** (dueño, 24 oct. 2026): Ctrl/⌘ \, «Dividir pantalla» en
  la paleta o «activa multitasking» por voz (también divide la ventana abierta,
  `launch.split_window`). La segunda pantalla es la misma app en modo panel
  (`?pane=1`, sin barra lateral ni voz) dentro de un iframe; por eso el servidor
  manda `X-Frame-Options: SAMEORIGIN` y `frame-ancestors 'self'` (otros sitios
  siguen sin poder enmarcarla). Se abre con el pliegue del iPhone Duo (estira,
  desenfoca al moverse, sombra en el pliegue). En un plegable con dos pantallas
  (Viewport Segments) se divide sola sobre la bisagra real (`lib/split.ts`).
- **Entrar con la cara** (dueño, 24 oct. 2026): llaves de acceso (WebAuthn) con
  el Face ID, Touch ID, Windows Hello o la huella **del propio dispositivo**
  (`accounts/passkeys.py`, `/v1/cuentas/llave/*`). Es la seguridad del
  dispositivo más la firma atada a la dirección (una página falsa no sirve) y
  el contador contra copias. Solo en https o localhost. No desbloquea el
  sistema operativo del PC, Mac o teléfono: eso no lo permite ningún sistema a
  una app (`docs/FACEID-SISTEMA.md`); no lo prometa.
- **Todo se aprueba con el Face ID propio de Sergio, no con Windows Hello**
  (dueño, 26 oct. 2026: «recuerda que todo se verifica vía nuestro propio
  ultra Face ID»). La hoja de confirmación del escritorio (`facegate.py`)
  usa `faceid_verify.py`: reto de movimiento de un solo uso, ráfaga de la
  webcam y `/v1/faces/faceid/unlock` (cara viva, mirando, el dueño y nadie
  más). Luz o un movimiento fallido no gastan intento; tras 5 caras que no
  coinciden, o si pasó mucho tiempo, pide el código de Sergio en la misma
  hoja. Sin cámara, sin servidor o sin Face ID configurado: «no». Límite
  honesto: una webcam no tiene cámara de profundidad como un iPhone.
  `platform_auth.py` (Windows Hello) queda en el código pero ya no se usa
  para aprobar.
- Notch menos cargado (24 oct. 2026): en reposo solo el orbe, centrado; la onda
  solo cuando hay voz; sin el título «Sergio» encima de la respuesta.
- Voz entre escritorio y ventanas: la ventana tiene prioridad, pero si el
  dueño llama a Sergio a propósito (palabra «Sergio», Ctrl+Espacio) el
  escritorio recupera la voz (`start.force`, `live_routes._take_over`), salvo
  que la ventana de Sergio esté al frente. El reconectador silencioso nunca fuerza.
- Botones redondos en Qt: radio = media altura exacta (con min/max-height), o
  Qt los dibuja cuadrados. Iconos del escritorio en `iconos.py` (Lucide).
- **Investigación profunda de verdad** (dueño, 25 oct. 2026): `research/deep.py`
  (herramienta `investigacion_profunda`, `POST /v1/investigar` en vivo,
  `sergio investigar`). Plan → búsqueda amplia (máx. 2 páginas por sitio) →
  leer las páginas → cada dato con cita literal que el código busca en la
  página (si no está, se descarta) → contraste por sitios distintos
  (confirmado / una fuente / en disputa) → segunda ronda por lo que falta →
  informe que solo cita fuentes reales. Buscadores: los de `web_search` y, si no
  dan nada, Google Search por Gemini. No lo reemplace por una sola búsqueda.
- Reuniones y llamadas en la web (`/reunion`, paleta «Grabar reunión»): graba,
  «boca abajo» deja la pantalla negra y despierta para seguir grabando, y el
  acta trae «Quién dijo qué» (`meeting_notes.by_person`). Con el aparato
  apagado no se puede grabar: no lo prometa. Siempre recuerda avisar que se graba.
- Estilo del dueño (`connectome/estilo.py`, órgano «estilo»): mide en este
  equipo cómo escribe (largo, usted/tú, idioma, emojis, horas, temas, si pide
  más corto o más largo) y ajusta cada respuesta; reglas de escritura humana
  siempre (`skills/bundled/escritura-humana`, `gusto-diseno`).
- Rendimiento: el servidor comprime las respuestas (gzip, nunca SSE ni audio) y
  los archivos con huella en el nombre se guardan en el navegador para siempre
  (`immutable`); un nombre viejo resuelto al nuevo nunca. Un equipo lento pasa
  solo a modo liviano (`lib/perf.ts`: sin desenfoques ni animaciones largas).
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
  de la voz, **mientras Sergio mira o actúa** (8 s tras cada mirada o acción).
  Cambiado el 26 oct. 2026 («realentiza mi laptop»): con una llamada que
  comparte la pantalla, 8 por segundo (recibe 1); sin nadie mirando, una
  mirada por segundo, aunque haya un video; una mirada la acelera al
  instante (`live_screen.py`). El árbol de accesibilidad solo se relee
  mientras mira. Notch y compañero del cursor redibujan a 60 Hz solo cuando
  algo se mueve (en reposo 10 Hz). Gemini Live recibe como máximo 1 imagen/s: escritorio y servidor
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
- **Logo de Sergio: disco azul con aro blanco** (dueño, 26 oct. 2026, con
  su foto; antes la mosca, 25 oct.). Un solo dibujo,
  `assets/marca/sergio.svg`; `scripts/marca_sergio.py` saca de él favicon,
  PWA, iPhone, instalador, accesos directos, bandeja, ventanas del escritorio,
  Tauri (.ico/.icns) y el agente de código (`--check` en las pruebas). Cambie
  el SVG y corra el guion; nunca edite un PNG a mano. El reactor de OpenJarvis
  solo queda en el README como crédito al proyecto original. En Windows la
  ventana de Sergio se ancla a la barra de tareas como app propia
  (`taskbar.py`: AppUserModelID y comando para volver a abrirla); Windows no
  deja que una app se ancle sola: el dueño lo hace una vez.
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
- **Centro de control del notch = botones rápidos** (dueño, 26 oct. 2026:
  «solo se podrá ver botón para Multitasking y Split Screen, Retroceder
  última acción de Sergio, Usage, Change Model / Effort, Display… y las
  acciones que están corriendo»): abre en una sola página
  (`panel_inicio.py`): «En marcha» (`/v1/personal/en-marcha` y las tareas del
  PC, cada una con su botón para detener), los interruptores como botones
  redondos y seis mosaicos — Multitarea (isla y ventana divididas a la vez),
  Deshacer, Uso, Modelo y esfuerzo, Pantalla (Night Shift, junto al cursor,
  esconder el notch) y Habilidades. Sin barra de pestañas: Chat, Nodes,
  Swarm, Salud y Ajustes quedan a un paso con «Volver». Nada nuevo entra a la
  página de inicio sin quitar otra cosa.
- **Videos: subtítulos que se mueven y videos programados** (dueño, 26 oct.
  2026: «subtítulos cool y no simplones en una línea… cree videos cada 3
  horas… y lo postee»). El video rápido (`video_create`) ya no pone la frase
  en una caja negra: 2–3 palabras grandes con borde, la que suena en amarillo,
  entrando con un pequeño salto (`video_essay/captions.py`, ASS con libass; si
  el ffmpeg no lo tiene, las líneas de antes). En el chat, «+ → Video»: idea,
  formato, **barra de esfuerzo** (Prueba, Básico, Para publicar, Absolut
  Cinema) y «repetir cada…» (`video_essay/schedule.py`, `/v1/personal/videos`).
  Lo programado respeta un video a la vez y el tope diario. **Nunca se publica
  solo**: cada video espera en «Listos para publicar» y «Publicar» (el toque
  del dueño) solo entrega archivo, título y descripción para subirlo.
- **Modelos 3D por piezas dentro del chat** (dueño, 26 oct. 2026: «un auto
  ultra detallado… verlo pieza por pieza con la skill anatomy»): herramienta
  `modelo_por_piezas` (`creator/despiece.py`, `/v1/creator/despiece/*`,
  visor `components/Chat/PartsViewer.tsx`). Sergio lo dibuja con medidas
  reales (un auto de prueba: 181 piezas en ~2 min), o abre un .glb/.gltf del
  equipo, o baja un modelo **solo CC0** de Poly Haven con su crédito. **Mods
  y modelos sacados de videojuegos no se usan**: son de sus estudios. El
  visor dibuja solo cuando algo cambia (nunca un bucle a 60 fps) y se carga
  solo cuando hay un modelo en el chat.
- **Aprobaciones en palabras simples** (dueño, 26 oct. 2026: «salen mensajes
  raros… debemos ser simples pero profesionales»): ninguna etiqueta interna
  (`<aprobacion>`, `<cli>`, `<mente>`…) llega a la pantalla; una aprobación
  es una tarjeta con una frase que entiende cualquiera y los comandos
  plegados (`lib/plainReply.ts`, `ApprovalCard.tsx`). Todo texto de un modelo
  que se muestre pasa por `plainReply`.
- **Cada persona elige cómo la llaman** (dueño, 26 oct. 2026: «usable con
  todos los géneros, en todos los países»): `personal.py` y
  `/v1/personal/*` (trato «señor», «señora», nombre, neutro o «tú»; idioma,
  país, saludos, habilidades apagadas). Sin perfil, «señor» como siempre: al
  dueño se le sigue llamando «señor». Una habilidad apagada no llega al
  modelo (`ToolExecutor`). «Deshacer» revierte lo último que Sergio hizo en
  el PC (`deshacer.py`, solo lo reversible y de los últimos 30 min).
- **Nadie inventa avances de video** (dueño, 26 oct. 2026: un Node dijo «el
  motor ha arrancado en modo Post» un día después, sin video): el chat y los
  Nodes reciben `<videos_reales>` (`video_essay/job.truth`) cuando se habla
  de un video y solo cuentan lo que dice; un trabajo parado más de 30 min se
  dice «detenido». El bucle de cada minuto retoma los videos a medias
  (`resume_unfinished`, 4 intentos como máximo).
- **Sin lag** (dueño, 26 oct. 2026: «se laguea demasiado… realentiza el
  cursor… tarda mucho pensando»): nada de ganchos globales de ratón (el
  salto del compañero al hacer clic lee el botón 20 veces por segundo); un
  solo gancho de teclado para todos los atajos; notch y compañero a 30 Hz
  mientras escuchan/hablan y 60 Hz solo cuando algo se mueve; la ventana del
  compañero se mueve solo si cambia de píxel; cámara en MJPG y sin pausas
  extra (manos a 30/s contando la detección). En el servidor: la respuesta
  del chat se escribe en vivo (`agents/_stubs.stream_tokens`), cada pedido
  corre en su propia copia del agente (antes una voz esperaba a un chat) y
  el chat no tiene la herramienta «think» (costaba una llamada extra al
  modelo antes de casi cada respuesta; `SERGIO_THINK_TOOL=1` la devuelve).
  Capturas de pantalla sin CAPTUREBLT (`windows_backend.no_captureblt`: con
  él el cursor parpadeaba y se frenaba en cada captura); la pantalla
  compartida se mira 4 veces por segundo (Gemini recibe 1); la memoria y la
  decisión del cerebro corren fuera del bucle del servidor.
- **Una sola ventana de Sergio**: al hacer clic en Sergio con la ventana ya
  abierta (aunque esté minimizada y dormida) se trae al frente esa misma
  (`launch.focus_open_window`); antes se abría otra igual.
- **Cualquier modelo, no solo Gemini** (dueño, 27 oct. 2026): el selector
  (`ModelSheet.tsx`, `/v1/personal/modelos`) agrupa por empresa — Google,
  OpenAI, Anthropic, DeepSeek y «todos los demás» por OpenRouter (una clave,
  cientos de modelos) — con «Conectar» por empresa y «Otro modelo» para
  escribir cualquier id (`vendor/modelo` = OpenRouter). El esfuerzo
  (`@low`…) solo va a Gemini (`cloud._plain`, `withEffort`). Cada respuesta
  cuenta según lo que cuesta el modelo (`quota.model_weight`: Flash/mini 1,
  Sonnet/GPT-5/Pro 3, Opus 8): así los planes y créditos dejan margen.
  **Intermediario con ganancia** (dueño, 27 oct. 2026: «el cliente paga un
  plan → el dinero llega a mi cuenta → un software paga al proveedor → nos
  quedamos el resto; las claves se crean por ellos en segundo plano»):
  `accounts/provision.py`. El dueño tiene UNA cuenta de empresa en
  OpenRouter con recarga automática desde su tarjeta y una clave de gestión
  (`OPENROUTER_MANAGEMENT_KEY` en `sergio.env`). Al aprobar o entrar un
  cliente, Sergio crea en segundo plano una **subclave dentro de la cuenta
  del dueño** con tope mensual = precio del plan − margen (`SERGIO_MARGEN`,
  0,40); el cliente no ve nada. Sus chats usan esa subclave
  (`provision.CUSTOMER_KEY`, middleware del servidor, `cloud_router` y
  `CloudEngine._openrouter_client`) por OpenRouter (`openrouter/auto` si
  eligió otro modelo). Bloquear o borrar la cuenta apaga la clave; el dueño
  cambia el plan con `POST /v1/cuentas/{id}/plan`. **Nunca** se abren
  cuentas en OpenAI, Google, Anthropic u otros a nombre de los clientes ni se
  sacan claves de sus cuentas (sus términos lo prohíben).
  **Modelos al día** (27 oct. 2026): Gemini 4 Argon, GPT-5.6 Sol/Terra/Luna,
  Claude Opus/Sonnet/Haiku 5.5, DeepSeek V4. Los nuevos aparecen solos: con
  la clave de cada empresa se lee su lista de modelos (`_discover`, cada 6 h).
- **Sergio Pagos** (dueño, 27 oct. 2026: «crea una tipo Stripe, Paddle o
  PayPal propia exclusivamente para Sergio… para automatizar todo»): paquete
  `pagos/` (`ledger.py` SQLite 0600, `gateways.py`, `service.py`),
  `server/pagos_routes.py` (`/v1/pagos/*`), páginas `/pagar` y
  `/pagar/listo` (`PayPage.tsx`) y «Cobros» del dueño en Planes →
  Facturación (`plans/PagosPanel.tsx`). Es la caja y el libro de Sergio. Debajo
  siempre va un procesador con licencia: Stripe (suscripción mensual), PayPal
  (un mes por pago) o Hyperswitch (Apache-2.0, alojado por el dueño, para
  pasarelas locales). Un pago confirmado (aviso firmado: HMAC de Stripe y de
  Hyperswitch, verificación de PayPal; importe comprobado; cada evento cuenta
  una vez) activa el plan y la subclave de IA solo, y anota ingreso,
  comisión, tope de IA y margen. Un mes sin renovar vuelve a Free. Solo
  `/v1/pagos/aviso/` y `/v1/pagos/vuelta/` quedan abiertos, y cada uno
  comprueba la firma o el pedido. **Sergio nunca ve una tarjeta, y los datos
  bancarios del dueño van solo en el panel del procesador**, nunca en Sergio
  ni en un chat (`docs/PAGOS.md`). Sergio no se presenta como procesador de
  pagos: eso exige licencias.
  **Endurecido** (dueño, 27 oct. 2026: «mejorar cifrado, profesionalismo y
  seguridad»): subclaves de IA cifradas con AES-256-GCM y atadas al cliente
  (`pagos/cifrado.py`, clave maestra local 0600 o `SERGIO_CLAVE_MAESTRA`);
  libro sellado con HMAC encadenado (`ledger.verify`) y devoluciones como
  líneas negativas; recibos `SG-AAAA-NNNNNN`; idempotencia en Stripe y
  PayPal; moneda USD comprobada; dinero real solo con https; 5 intentos cada
  10 min; aviso de 256 KB como máximo; reembolsos y contracargos de PayPal
  automáticos, los de Stripe con «Devolver»; lista de pasos
  (`/v1/pagos/estado`). El dueño comprueba con su tarjeta mediante «Probar
  con mi tarjeta ($1)», escribiéndola solo en la página del procesador.
  **Nunca se aceptan números de tarjeta ni datos bancarios en un chat**, ni
  se guardan en Sergio.
- **Seguridad** (dueño, 27 oct. 2026: «que todo Sergio sea in-hackeable y que
  nadie pueda copiarnos»): nada es imposible de hackear y no se promete. Lo
  que sí hay está en `docs/SEGURIDAD.md`:
  - Desde fuera, todo es 403 salvo cuentas y avisos firmados.
  - Los archivos secretos vuelven a 0600 al arrancar (`security/permisos.py`).
  - CSP con `object-src 'none'` y `base-uri 'self'`, y el servidor no dice
    qué programa es.
  - Desde fuera, los errores no muestran el detalle técnico.
  - El XML de fuera no puede traer DOCTYPE ni entidades (`security/safe_xml.py`).
  - Las dependencias se revisan con pip-audit y npm audit. Los `overrides` de
    `frontend/package.json` fuerzan dompurify y katex sin fallos conocidos.
  - Si se añade una dependencia, se audita.
  El repositorio es público: hacerlo privado lo decide el dueño (antes, su PC
  necesita `gh auth login` para seguir actualizando).
- **Voz propia de Sergio, siempre** (dueño, 27 oct. 2026: «voz propia… transcripción ultrarrápida al mismo tiempo que se escribe la respuesta, menos de 0,5 s», y eligió usarla siempre, con Gemini Live solo de respaldo):
  - Dónde está: `speech/voz_propia.py`, con el mismo protocolo que `/v1/live`, así que la web y el escritorio no cambian.
  - Escuchar: faster-whisper transcribe mientras se habla.
  - Hablar (cambiado el 27 oct. 2026, el dueño: «la voz es una mierda»): Kokoro `em_alex` no da la talla en español y ya no habla por defecto. La voz propia habla con ElevenLabs Flash (la voz de Sergio en ElevenLabs, original, nadie clonado) cuando hay `ELEVENLABS_API_KEY`; sin esa clave la llamada va con Gemini Live (Algenib). `SERGIO_VOZ=propia` fuerza la voz propia (con Kokoro si no hay clave); `SERGIO_VOZ=gemini`, siempre Gemini. Responde frase por frase mientras se escribe la respuesta; la primera frase sale a las 3 palabras.
  - Acuse: si la primera frase no está lista a los 0,35 s, suena un «Claro,» ya sintetizado.
  - Se le interrumpe hablando por encima.
  - `latency` separa el tiempo de Sergio del tiempo del modelo.
  - El dueño va con su agente y sus herramientas; el cliente, con su subclave, sin herramientas ni memoria del dueño.
  - Si los modelos no cargan (`ready()`), o con `SERGIO_VOZ=gemini`, se usa Gemini Live. La actualización baja los modelos.
  - Al arrancar, el servidor precalienta el cerebro, la memoria y la voz (`app._warm_up`): la primera respuesta bajó de ~12 s a ~3 s.
- **Edición de video profesional** (dueño, 27 oct. 2026), en `video_essay/pro.py`:
  - Voz de locutor: paso alto, reducción de ruido, de-esser, ecualización, compresor, puerta suave y limitador.
  - Cortes al ritmo de la música, sin partir palabras.
  - Formatos 9:16, 1:1 y 16:9 que siguen caras o movimiento.
  - SRT y capítulos.
  - Control de calidad: −14 LUFS, picos, negros y congelados de 3 s o más.
  `job.py` lo usa en sonido y acabado.
- **Tipografías, color y composición; clips y música de internet** (dueño, 27 oct. 2026: «subtítulos en diferentes partes con diferentes tipografías, como NextCore; teoría del color y composición; clips de internet, música, películas y series»):
  - `video_essay/typo.py`: seis letras con un papel cada una (base, impacto, pesada, elegante, técnica, mano); cuatro como mucho por video. Cada línea toma la que pide (números en técnica, 1–3 palabras en impacto, citas en elegante) y no repite la de la toma anterior sin motivo. Los subtítulos rápidos (`captions.py`) también cambian de letra y de lugar.
  - `video_essay/color.py`: paleta, armonías (complementario, análogo, triádico, complementario dividido), contraste WCAG, saliencia y caras. Las palabras van al tercio libre, dentro del área segura, nunca sobre una cara, y no dos veces seguidas en el mismo sitio. Un solo acento por video (el del estilo, o el complemento del color de las tomas). Si el blanco no se lee, las palabras van sobre bloques.
  - Lo que el editor (el modelo) elige en el plan (`font`, `position`, `accent`, `box`) se respeta; `typo.dress` solo rellena lo que quedó libre.
  - Escenas de películas y series: fuente `film` (yt-dlp, unos segundos, citadas como «no libre»); si no hay, películas de dominio público del Internet Archive.
  - Música: `video_essay/music.py`. Busca por el ánimo del estilo en Openverse, ccMixter e Internet Archive, solo licencias para ganar dinero (CC0, BY, BY-SA; `monetize: false` abre las NC). La pista se repite hasta el largo del video, se desvanece y va a los créditos. Una canción con derechos solo si el dueño la nombra (`music: "canción: …"`), nunca otra en su lugar, y el paquete avisa que pueden reclamarla. Sin internet o sin resultados: la música propia de Sergio.
  - No se piratea: nada de torrents ni sitios de copias; las películas y series salen de clips públicos (como ya decidió el dueño) o de dominio público.
- **Edición más larga, con más clips y más coherente** (dueño, 27 oct. 2026: «mejora la edición mucho más, videos más largos, más clips, mejores subtítulos, más coherencia; y la voz es una mierda»):
  - Voz del video: narrador dirigido (`script.NARRATOR`), con ElevenLabs Multilingual v2 si hay clave y, si no, las voces de estudio de Gemini (Pro primero). Se narra por partes, tres a la vez, y cada parte conoce la anterior.
  - Largo: hasta 30 min (120 s si no se dice). Desde 3 min el guion va por capítulos con mini-ganchos y lazos abiertos; si el modelo lo acorta, se le pide otra vez el largo. El presupuesto crece con la duración (`modes.limits_for`), pero no el video IA ni el 3D. El plan va por tramos de ~220 palabras (`plan.segments`), y cada tramo ve cómo terminó el anterior.
  - Clips: si la descripción larga no encuentra nada, busca su núcleo y luego dos palabras (`media.queries`). Un clip repetido da otro trozo, nunca el mismo. Antes que una imagen o una ficha negra, se corta un trozo nuevo de un clip ya encontrado que no salió en las dos tomas anteriores (`Filler._reuse`).
  - Subtítulos: en tomas largas salen de 2 a 5 palabras a la vez que se reemplazan en el mismo sitio, y la palabra que se dice se enciende en el color de acento (`render.chunks_of`, `Placed.until`, `lit_rgb`). Las fichas siguen enteras.
  - Coherencia: el editor recibe el título, la idea y el «look» del video. El tratamiento pide un hilo (porque, pero, así que) y un mundo visual que vuelve. Todas las tomas se acercan a medias a un mismo color (`color.unify`, `Shot.tone`), salvo fichas y tomas con su propio look.
- **Skills de GitHub, automatización, estabilidad, inicio de sesión y tour** (dueño, 27 oct. 2026: «mínimo 20 skills reales de GitHub para guiones… 25 de motion graphics… automatización completa… trading con resultados reales… estabilizar todo… Sergio no es solo Gemini… inicio de sesión y un tour con widgets»):
  - Skills: `video_essay/skills_catalog.json` (37 de guion, 38 de motion: 23 SKILL.md y 15 herramientas), descargadas al equipo con `skillbook.sync` (lo hace la actualización), nunca al repositorio. `skillbook.guidance` mete las que encajan en el tratamiento (guion) y en el plan (motion). Beav no se usa (solo no comercial).
  - Entrega del guion: cada beat lleva `delivery` (`tone`, `pause` de 0 a 1,6 s). `script.narrate_beats` agrupa por tono, dirige la voz con ese tono y deja silencio real en las pausas.
  - Todos los modelos: `creator.llm.ask` usa Gemini y, si falla o el dueño elige otro (`SERGIO_VIDEO_MODELO`), Claude, GPT, DeepSeek u OpenRouter; las imágenes siguen yendo a Gemini. El narrador también cae a OpenAI (`gpt-4o-mini-tts`, voz onyx).
  - Material real primero: clips del dueño, bancos, internet, escenas de películas y archivo; la imagen generada es el último recurso (`media.order_for`).
  - Automatizar (`automatiza/`, `/v1/automatiza`, página `/automatizar`, herramienta `automatizar`), solo el dueño:
    - Canales: un programado con «Publicar solo» (`auto`) sube cada video terminado a YouTube (API oficial, resumable, #Shorts si es vertical y corto) y/o Instagram (Reels por Graph API, con un enlace de un solo uso en `SERGIO_PUBLIC_URL`), con tope diario `SERGIO_PUBLICAR_DIA` (3). Un canal que ya lo recibió no se repite. Sin `auto`, el video espera su «Publicar» como antes. Tokens sellados con `pagos.cifrado`.
    - **Sergio no crea cuentas de YouTube ni de Instagram** (va contra sus reglas): el dueño las crea y las conecta.
    - Respuestas a comentarios: Sergio las redacta; **solo salen las que el dueño aprueba**.
    - Clientes y empleos: RemoteOK, Himalayas, Arbeitnow, We Work Remotely y búsqueda web; puntos según su perfil y borradores. **Nada se envía solo**: él copia y envía.
    - Trading: Alpaca, **en papel por defecto**; dinero real solo con el ajuste `real` **y** `SERGIO_TRADING_REAL=1`. Límites (orden, símbolo, órdenes al día, pérdida del día que lo detiene), archivo `PARAR`, diario, y prueba con el pasado sin mirar el futuro y con costes. Nunca se prometen ganancias.
  - Estabilidad (`estabilidad.py`): vigía que reinicia el servidor si su `/health` no responde 3 veces (el servicio tiene `Restart=always`; `SERGIO_VIGIA=0` lo apaga), chequeo en palabras simples y reparación diaria (04:00) que nunca toca un video en curso ni los videos terminados.
  - Inicio de sesión primero (`lib/session.ts`): sin sesión, la app va a «/entrar» (o «Crear cuenta» la primera vez); si el servidor no responde, no bloquea. En el propio equipo hay «Seguir sin cuenta en este equipo». Las páginas de pago siguen abiertas.
  - Tour (`components/Tour`): diez pasos con widgets vivos, sale una vez al entrar y vuelve desde Ayuda o la paleta («Ver el tour»). Sustituye la redirección a «Primeros pasos», que sigue en `/get-started`.
- **Dividir pantalla a la vista, bienvenida, «En marcha» y más cine** (dueño, 28 oct. 2026: «no encuentro cómo hacer split screen… más clips de películas y series… mejor tono… más coherencia entre lo que se muestra y se dice… app más simple… mejora la bienvenida y el inicio de sesión… control y acciones en segundo plano»):
  - El botón de dividir (`SplitButton`) vive en el encabezado del chat; Ctrl/⌘ \\ y la paleta siguen. Nunca vuelva a esconder una función solo tras un atajo.
  - Bienvenida de cuatro mosaicos; inicio de sesión con etiquetas visibles.
  - Escenas de películas y series: alrededor del 30 % de las tomas con imagen (`plan.add_film`, `FILM_SHARE`), nunca dos seguidas.
  - La revisión del editor exige «SAY = SHOW» (la imagen muestra lo que se dice).
  - El tono de cada parte mueve la voz de ElevenLabs (`TONE_SETTINGS`).
  - «En marcha» (`RunningPill` y `/v1/personal/en-marcha`): todo lo que corre en segundo plano, con su botón de parar. Algo nuevo que corra solo debe aparecer ahí.
- **Conversación en vivo presente y productiva** (dueño, 28 oct. 2026): ante un trabajo largo Sergio dice «sigo con eso» en vez de callar (`STILL_AFTER`, `SERGIO_VOZ_SIGO`), el cliente muestra `hearing`, `thinking` y `working`, y `VOICE_NOTE` pide respuesta primero, resultado concreto y un solo siguiente paso útil. Un silencio largo sin explicación es un fallo.
- **Video por género** (dueño, 28 oct. 2026: «no solo videos inspiracionales, también cortos cinematográficos, animaciones y edición pesada tipo MrBeast»): `video_essay/genres.py` (inspiracional, cine, animación, pesada, documental) elige estilo, fuentes, búsqueda, cuota de cine y la pasada de gráficos animados (contador, círculo, flecha, barra, letterbox). Los estilos `corto-cine` y `edicion-pesada` son de Sergio: técnicas, nunca imitar a un creador. Género nuevo: agréguelo ahí, con su estilo y su prueba.
- **Escenas de cine con sentido** (dueño, 28 oct. 2026: «que los clips sean también de películas y tengan coherencia con el tema; mejor subtitulado y narración»): las tomas de cine reciben una película o serie real y su escena exacta (`films.py`); un clip cuyo título no tiene que ver se descarta (`sources.fits`); los subtítulos no terminan en palabras pequeñas (`render.WEAK`) y la narración sale pareja (`script.even`). Nunca se inventa una película.
- **El núcleo es cualquier modelo; OpenRouter lo configura todo** (dueño, 28 oct. 2026): sin la clave de una empresa, sus modelos van por OpenRouter (`engine.cloud.through_openrouter`); al entrar o crear cuenta se configura la clave del dueño, la subclave del cliente y la lista de modelos (`accounts/autoconfig.py`). Sin Gemini, la voz en vivo es la propia. Una respuesta fallida nunca cuelga la llamada (`turn_error`).
- **Guía en pantalla** (dueño, 28 oct. 2026: «Sergio dibuja flechas, círculos o líneas en 2D y 3D sobre tu pantalla… y desaparecen al hacer clic»): `sergio_escritorio/guia.py`, acción `guide` de `desktop_action`, `marks` de la ayuda de pantalla y `guiar` en llamada. Nunca toma un clic ni el foco; se va con el primer clic, Esc, «entendido» o a los 25 s.
- **Edición al nivel de los explicativos 3D y de los canales de retos** (dueño, 28 oct. 2026): géneros `explicado3d` y `corto3d`, el método de retención en la nota de `pesada` (en palabras nuestras, sin nombrar ni imitar a nadie) y **como mucho tres skills por género y etapa** (`Genre.skills`): «usa más skills pero no amontones todas para confundir al modelo».
- **Tendencias reales** (dueño, 28 oct. 2026): `automatiza/tendencias.py`; una idea sin señal real se descarta. Nunca se inventa una tendencia ni una cifra.
- **Automatizar es una conversación** (dueño, 28 oct. 2026: «tipo chat, pero mejor y sin caer en solo Instagram y YouTube»): `automatiza/charla.py` responde con tarjetas y botón; nada cambia sin el toque del dueño. Donde no hay API oficial (TikTok, Facebook, LinkedIn, X) el video queda listo para que él lo suba; Sergio nunca entra a una red por él.
- **Reglas de diseño editorial** (dueño, 28 oct. 2026), por ahora en Automatizar: sin degradados violeta/azul eléctrico/rosa, sin brillos ni cuadrículas flotantes, sin ilustraciones genéricas; tres colores como mucho (papel, tinta, un azul profundo); secciones claras y oscuras alternadas; apertura asimétrica; una serif o display con carácter para títulos y una sans industrial para texto (no Inter ni Geist); botones con cambio de color sólido o 1 px de desplazamiento; bordes de 1 px. El dueño dirá qué sección sigue; mientras, el resto conserva el diseño Apple.
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

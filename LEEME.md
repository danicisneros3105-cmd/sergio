# Sergio — tu asistente todo-en-uno

Un solo asistente personal que une el poder de tres proyectos:

| Pieza | Qué aporta | Dónde vive |
|---|---|---|
| **OpenJarvis** (núcleo, Python) | El cerebro: chat, memoria, tareas programadas, skills, voz, canales (Telegram…), IA local con Ollama o por API | `src/openjarvis/` |
| **OpenClacky** (Ruby) | Las manos: usa la terminal, tus archivos y **tu Chrome real** (entra a páginas, hace clic, rellena formularios) | `extensions/clacky/` |
| **God's Eye View** (JS) | Los ojos sobre el mundo: globo 3D con aviones, barcos, satélites y terremotos en vivo | `extensions/globe/` |

No son tres programas sueltos:

- **Un comando** (`sergio gui`) arranca todo, y al cerrarlo se apaga todo.
- **Una interfaz:** Chat, Globe y Clacky son pestañas de la misma app.
- **Un solo cerebro:** Clacky usa automáticamente el modelo que configures en
  Sergio, sea local o por API. No hay que configurarlo dos veces.
- **Una sola configuración:** `~/.openjarvis/config.toml`.
- **Herramientas cruzadas:** desde el chat de Sergio puedes pedir tareas que
  ejecuta Clacky, consultar datos en vivo del mundo y mover el globo.

## Instalar

**Windows 11** (PowerShell como administrador):

```powershell
git clone https://github.com/TU_USUARIO/sergio.git
cd sergio
Set-ExecutionPolicy -Scope Process Bypass; .\scripts\install-windows.ps1
```

**Linux o WSL:**

```bash
git clone https://github.com/TU_USUARIO/sergio.git ~/sergio
cd ~/sergio && ./scripts/install-todo-en-uno.sh
```

## Usar

```bash
uv run sergio gui                    # abre la app completa
uv run sergio extensions status      # estado de Clacky y del globo
uv run sergio extensions logs clacky # qué está haciendo Clacky
uv run sergio gui --no-extensions    # solo OpenJarvis
uv run sergio approvals list         # tareas esperando tu aprobación
uv run sergio approvals approve ID   # aprobar desde la terminal
```

Ejemplos de cosas que puedes pedir en el chat:

- *"Muéstrame Tokio en visión nocturna"*: usa la herramienta `globe_view` y
  la pestaña Globe vuela hasta allí.
- *"¿Qué aviones pasan ahora sobre Madrid?"*: usa `live_flights`, con datos
  ADS-B en vivo.
- *"¿Hubo terremotos fuertes hoy cerca de México?"*: usa `live_earthquakes`
  (USGS).
- *"¿Cuándo es el próximo lanzamiento de SpaceX?"*: usa `upcoming_launches`.
- *"Organiza mi carpeta Descargas por tipo de archivo"*: usa `clacky_task`.
  Aparece en la campana 🔔 de la app; cuando apruebas, Clacky lo ejecuta.

El instalador ya activa estas herramientas en `~/.openjarvis/config.toml`
(sección `[tools] enabled`), además de compilar el motor nativo en Rust que
usan la memoria de documentos y la búsqueda.

## Modo permanente (siempre encendido)

Sergio puede vivir en segundo plano y arrancar solo cada vez que enciendes el
PC. Lo abres cuando quieras en **http://localhost:8000**.

```bash
sergio servicio instalar      # instalar y encender (una sola vez)
sergio servicio apagar        # apagarlo; sigue apagado tras reiniciar
sergio servicio encender      # volver a encenderlo
sergio servicio estado        # ¿está corriendo?
sergio servicio desinstalar   # quitar el servicio (tus datos se conservan)
```

- Son dos servicios de systemd: `sergio.service` (servidor e interfaz) y
  `sergio-extensiones.service` (Clacky y el globo, con un vigilante que los
  reinicia si se caen). Si algo falla, systemd lo reinicia; al arrancar el
  PC, reintenta hasta que Ollama esté listo.
- **En Windows:** `scripts\windows-autoarranque.ps1 -Activar` hace que WSL
  arranque al iniciar sesión, sin ventanas. `-Desactivar` lo quita.
  `install-windows.ps1` ya hace todo esto por ti.
- **Claves de API en modo servicio:** ponlas en `~/.openjarvis/sergio.env`
  (`ANTHROPIC_API_KEY=...`), porque los servicios no leen tu terminal.

## Configuración (`~/.openjarvis/config.toml`)

```toml
[intelligence]
default_model = "qwen3:8b"        # local con Ollama
# default_model = "claude-sonnet-5-5"   # por API (con engine "cloud" y ANTHROPIC_API_KEY)

[engine]
default = "ollama"                # o "cloud"

[extensions]
autostart = true                  # arrancar Clacky y el globo con `sergio gui`

[extensions.clacky]
enabled = true
port = 7070
timeout_seconds = 900             # tiempo máximo por tarea delegada

[extensions.globe]
enabled = true
port = 4173

[analytics]
enabled = false
```

Clacky lee el modelo de esta misma configuración:

| Motor de OpenJarvis | Cómo se conecta Clacky |
|---|---|
| `ollama` | A Ollama por su API compatible con OpenAI. |
| `vllm`, `sglang`, `llamacpp`, `lmstudio` | Al endpoint `/v1` de ese motor. |
| `cloud` con modelo `claude-*` | A Anthropic, con `ANTHROPIC_API_KEY`. |
| `cloud` con modelo `openrouter/...` | A OpenRouter, con `OPENROUTER_API_KEY`. |
| `cloud` con modelo `gemini-*` | A Google, con `GEMINI_API_KEY` o `GOOGLE_API_KEY`. |
| `cloud` con cualquier otro modelo | A OpenAI, con `OPENAI_API_KEY`. |

## Problemas que arregla la unión

- **Telemetría:** la de Clacky queda siempre apagada (`CLACKY_TELEMETRY=0`) y
  el instalador apaga también la analítica de OpenJarvis.
- **Embeber el globo:** el globo prohibía que otra página lo mostrara (CSP
  `frame-ancestors 'none'`). Ahora acepta solo a la interfaz local de Sergio
  (`GLOBE_FRAME_ANCESTORS`, limitado a orígenes loopback) y sigue bloqueando
  cualquier otro sitio.
- **Configuración duplicada:** antes cada proyecto tenía su propia
  configuración de modelo; ahora hay una sola.
- **Arranque manual:** antes había que lanzar tres servicios a mano; ahora el
  supervisor (`src/openjarvis/unified/`) los arranca, comprueba que responden
  y los detiene juntos.

## Evolución: Sergio se adapta a ti

1. **Aprende en cada conversación.** La memoria (`[memory] enabled = true`, que
   el instalador activa) extrae en segundo plano datos duraderos: tus
   preferencias, cómo te gusta que te hable, personas, rutinas y metas.
2. **Consolida tu perfil.** Una vez al día, al abrir `sergio gui`, reescribe
   `~/.openjarvis/USER.md` con lo aprendido. Cuando dos datos se contradicen,
   gana el más nuevo; los duplicados se fusionan. Ese perfil va en cada
   conversación.
3. **Se puede revisar y deshacer.** Cada versión anterior se guarda como
   `USER.md.<fecha>.bak` (se conservan las 5 últimas). Lo que el escáner de
   seguridad marca como sospechoso nunca entra en tu perfil.

```bash
uv run sergio evolve --show     # evolucionar ahora y ver el perfil
uv run sergio memory list       # ver todo lo que ha aprendido
```

## Mejores respuestas con menos tokens

- **LLMLingua-2** ([microsoft/LLMLingua](https://github.com/microsoft/LLMLingua),
  licencia MIT, gratis) comprime entre 2 y 5 veces los resultados largos de
  páginas web, PDFs y búsquedas antes de pasárselos al modelo. Conserva los
  números (precios, fechas, teléfonos). Nunca toca código, archivos ni
  comandos. Se instala con `./scripts/install-todo-en-uno.sh --ahorro-tokens`
  (unos 2 GB) y se activa con `[compression] tool_output = true`. Si falla,
  Sergio usa el texto original.
- **Ya existía en OpenJarvis:** la compresión de sesiones largas (activa) y un
  enrutador que puede mandar las preguntas simples al modelo pequeño (hay que
  configurarlo). La evolución también ahorra tokens: envía un perfil
  consolidado en lugar de cientos de datos sueltos.

## Llamadas y WhatsApp

Sergio puede **llamar por teléfono** (a ti o a un restaurante), **recibir tus
llamadas** y **escribir por WhatsApp**. Lo que dice lo oye la otra persona
con una voz en español generada en tu PC (Kokoro), y entiende lo que le
dicen con Whisper. Piensa con el mismo modelo que el chat.

**Necesitas tres cuentas** (las de Twilio y ngrok tienen nivel gratis):

1. **Twilio** (twilio.com): un número de teléfono virtual. Llamar cuesta
   céntimos por minuto según el país. En la cuenta de prueba solo puedes
   llamar a números que verifiques en Twilio.
2. **ngrok** (ngrok.com): una dirección pública fija y gratuita para que
   Twilio y WhatsApp lleguen a tu PC. En el panel copia el *Authtoken* y crea
   tu *static domain* gratis.
3. **WhatsApp Business** (developers.facebook.com, opcional): registra allí
   el mismo número de Twilio. Copia *Access token*, *Phone number ID* y
   *App secret*.

Luego, en Ubuntu:

```bash
sergio telefono configurar    # te pide los datos uno a uno y lo deja listo
sergio servicio apagar && sergio servicio encender
sergio telefono probar        # Sergio te llama para probar
sergio telefono estado        # qué falta (nunca muestra tus claves)
```

En el chat: *"Llama al restaurante La Pizzería al +593 2 222 2222 y reserva
mesa para dos a las 5 pm a nombre de Dani"*.

**Reglas de seguridad (están en el código):**

- Sergio **siempre dice que es un asistente de IA** al llamar a terceros.
- Toda llamada o WhatsApp a alguien que no seas tú **espera tu aprobación**
  en la campana 🔔 (o `sergio approvals approve <ID>`); a tus propios números
  va directo.
- **Solo tus números** pueden hablar con Sergio por WhatsApp/SMS o llamarle;
  cualquier otro es ignorado o escucha un aviso y se cuelga.
- Las llamadas duran como máximo `max_call_minutes` (10 por defecto) y
  Sergio cuelga solo al terminar.
- WhatsApp solo permite texto libre a quien te escribió en las últimas 24 h.

## Reconocimiento facial (Faces)

Pestaña **Faces** de la app: enciende la cámara, escribe un nombre, marca que
esa persona **está de acuerdo** y pulsa *Save face* (3–5 fotos desde ángulos
distintos mejoran el resultado). *Who is this?* dice quién aparece.

- Todo ocurre **en tu PC** (OpenCV YuNet + SFace); se guardan solo
  "huellas" numéricas de la cara, no las fotos.
- Sergio **solo reconoce a quien registraste**; el resto sale como
  "desconocido". Él no puede registrar caras por su cuenta.
- Terminal: `sergio rostros registrar NOMBRE foto.jpg`,
  `sergio rostros identificar foto.jpg`, `sergio rostros lista`,
  `sergio rostros olvidar NOMBRE` (borra todo lo de esa persona).

## Sergio en Windows: compañero del cursor

Sin ventanas. Sergio vive junto a tu puntero como una pequeña esfera que te
sigue, te escucha y usa la computadora por ti:

- **Di «Sergio, …»** en cualquier momento («Sergio, abre Spotify», «oye
  Sergio, ¿qué tengo en pantalla?»). Si solo dices «Sergio», responde «¿Sí?»
  y escucha lo siguiente. **Ctrl+Espacio** también sirve, sin decir su nombre.
- **El notch**: arriba al centro de la pantalla, como en un MacBook, vive el
  personaje de Sergio: una carita que parpadea y te sigue con la mirada.
  Pequeño en reposo; crece para mostrar lo que oye, piensa y responde. Un clic
  en él para hablarle. Se esconde solo si ves un video o juegas a pantalla
  completa (y reaparece cuando Sergio habla).
- La esfera junto al cursor cambia según lo que hace: azul en reposo, roja escuchando, ámbar
  pensando, verde hablando. Al lado aparece una burbuja con lo que oyó y lo
  que responde, y contesta en voz alta en español.
- **Usa tu pantalla como tú**: lee los botones, campos y enlaces de la ventana
  activa (accesibilidad de Windows), y hace clic, escribe, pulsa teclas, abre
  programas, páginas y archivos. El puntero viaja visible hasta cada botón
  antes de hacer clic.
- **Ctrl+Alt+Fin** pausa o reanuda al instante su control del mouse y del
  teclado. Llevar el mouse a la esquina superior izquierda también lo frena.
  No compra, paga, borra ni envía mensajes salvo que se lo pidas claramente.
- Todo se procesa en tu laptop. Mientras habla no se escucha a sí mismo, y las
  conversaciones que no empiezan con «Sergio» se ignoran.
- Clic derecho en su icono junto al reloj: activar o quitar la palabra
  «Sergio», ocultar la esfera o el notch, pausar el control, abrir el chat o
  salir.

- **Cámara flotante** (Ctrl+Alt+C o clic derecho en el icono → Cámara): una
  ventanita redonda que arrastras a donde quieras (la rueda del mouse cambia
  su tamaño). Pregúntale «Sergio, ¿qué tengo en la mano?», «¿qué gesto
  hago?» o «¿quién está aquí?»: mira por la cámara con un modelo con visión
  (Kimi o Gemini) y reconoce a las personas que registraste en Rostros. La
  cámara se apaga sola 20 s después de usarla.
- **Voz natural**: voces neuronales de Microsoft (Luis o Andrea de Ecuador,
  México, Colombia, España, Argentina). Sin internet usa la voz local.
- **Personalizar a Sergio** (clic derecho en el icono): colores (Océano,
  Atardecer, Aurora, Rosa, Menta, Grafito), ojos, tamaño junto al cursor y voz.
- Por voz también usa la búsqueda web, el globo 3D (God's Eye View) y las
  guías expertas de ECC.
- **Tareas de varios pasos**: «Sergio, abre Google, busca Nvidia y entra al
  primer link»: abre la búsqueda, lee la página, hace clic y sigue hasta
  terminar.
- **Editar videos**: «Sergio, edita un video con la carpeta *Viaje* al estilo
  del canal *X*, vertical para Shorts». Busca cómo son los videos de ese canal,
  corta y une tus clips (16:9, 9:16 o 1:1), pone título y música, lo guarda en
  *Videos\\Sergio* y te lo abre para que lo revises. Basta con decir el nombre
  de la carpeta: la busca en Videos, Escritorio, Descargas, Documentos y
  OneDrive. «Inspirado en un canal» es una aproximación (formato, ritmo,
  títulos), no una copia exacta.
- **Aprobar con tu cara**: primero di «Sergio, aprende mi cara» mirando a la
  cámara. Antes de publicar, subir, enviar, pagar o borrar algo, Sergio te
  pide mirar a la cámara y solo sigue si reconoce **tu** cara (si hay más
  personas registradas, pon tu nombre en `SERGIO_OWNER_NAME` dentro de
  `~/.openjarvis/sergio.env`). Publica en YouTube subiendo el video desde
  YouTube Studio en tu navegador, como lo harías tú (tu sesión debe estar
  abierta).
- **Blender**: «Sergio, abre Blender y crea un castillo enorme». Escribe un
  script de Blender que construye el modelo y abre Blender con el resultado
  para que sigas editándolo. Instala Blender antes:
  `winget install BlenderFoundation.Blender`.
- **Ordenar archivos**: «Sergio, ordena mi carpeta de Descargas». Primero te
  dice qué va a mover (Imágenes, Videos, Documentos, Instaladores…) y solo lo
  hace si le dices que sí. Nunca borra ni sobrescribe; «Sergio, deshaz el
  orden» lo deja todo como estaba. También puede ordenar por mes.
- **Python**: «Sergio, calcula…», «convierte estas fotos a PNG», «renombra los
  archivos de esta carpeta»: escribe y ejecuta un programa de Python en tu
  laptop (carpeta *Documentos\\Sergio*) y te dice el resultado.
- **Tareas largas**: primero carga la guía experta de ECC que corresponde,
  planea los pasos y los hace uno por uno.
- **Mejor oído**: con la tarjeta NVIDIA usa el modelo grande de Whisper
  (large-v3-turbo) en la GPU; si no puede, usa el pequeño en el procesador.
  Sube el volumen de tu voz y revisa en Windows → Sonido → Entrada que esté
  elegido el micrófono correcto.

Instalar o actualizar (en Ubuntu):

```bash
cd ~/sergio && git pull && sergio escritorio instalar
sergio escritorio estado        # comprobar que está conectado
```

Para que además describa imágenes de la pantalla (fotos, gráficos), añade
`--vision`: descarga un modelo de visión local de unos 6 GB.

## Modelos en la nube: Kimi y Gemini

Para respuestas más rápidas e inteligentes que el modelo local, Sergio puede
pensar con **Kimi** (Moonshot) o **Gemini** (Google):

```bash
sergio nube configurar      # pide las claves (no se ven al escribir)
```

- Comprueba la clave de Kimi, elige su mejor modelo (p. ej. `kimi-k2.6`) y lo
  deja como principal; `qwen3:8b` queda de respaldo si no hay internet.
- Las claves se guardan **solo** en `~/.openjarvis/sergio.env` (privado), nunca
  en el repositorio ni en `config.toml`.
- Kimi usa su modo rápido (sin "pensamiento largo") para que la voz responda
  ágil, y puede usar todas las herramientas de Sergio (pantalla, llamadas...).
- Claves nuevas de Google que empiezan con `AQ.` funcionan (modo express).
- Lo que dices y las respuestas viajan al proveedor de la nube; el oído
  (Whisper) y la voz de Sergio siguen en tu laptop.

## ECC: guías expertas bajo demanda

Sergio incluye [ECC (Everything Claude Code)](https://github.com/affaan-m/ECC),
licencia MIT: unas 290 skills y 60 guías de agentes sobre investigación,
escritura, marketing, planificación, programación, seguridad y datos.

Para no gastar tokens, no se meten en cada mensaje. Sergio tiene una sola
herramienta (`skill_guide`): busca la guía que sirve y la lee solo cuando la
necesita. El instalador la descarga (unos 12 MB, solo `skills/` y `agents/`).

```bash
sergio ecc actualizar           # descargar o actualizar
sergio ecc buscar deep research # ver qué guías hay sobre un tema
sergio ecc estado
```

## Estado y límites

- Comprobado en Linux: `sergio extensions start` levanta Clacky y el globo.
  `clacky_task` delega una tarea real a Clacky usando el modelo de OpenJarvis.
  Las pestañas Globe y Clacky se muestran dentro de la app, y el globo aplica
  la vista que pide el chat.
- `live_flights`, `live_earthquakes` y `upcoming_launches` están probadas con
  respuestas simuladas. Contra las APIs reales hay que probarlas en tu laptop.
- `clacky_task` da a Clacky control total del ordenador mientras dura la
  tarea, por eso cada tarea espera tu aprobación en la campana 🔔 (5 minutos;
  después puedes aprobarla y pedirle a Sergio que continúe). Lo aprobado no
  se puede cambiar después: Clacky ejecuta exactamente lo que aprobaste.
- Qué tareas son viables y sus límites legales (correos masivos, Instagram,
  llamadas, tareas escolares): [docs/es/CAPACIDADES.md](docs/es/CAPACIDADES.md).

## Mantener al día

Los tres proyectos originales siguen mejorando. Para traer sus cambios:

```bash
git subtree pull --prefix=extensions/clacky https://github.com/clacky-ai/openclacky.git main --squash
git subtree pull --prefix=extensions/globe  https://github.com/bilawalsidhu/gods-eye-view.git main --squash
git pull https://github.com/open-jarvis/OpenJarvis.git main
```

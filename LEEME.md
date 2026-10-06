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
  Aparece en la campana de la app; cuando apruebas, Clacky lo ejecuta.

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
  en la campana (o `sergio approvals approve <ID>`); a tus propios números
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
- **Nunca más «todos son Daniel Cisneros»**: antes, si alguien pedía «aprende
  la cara» sin decir el nombre, Sergio guardaba a esa persona con el nombre
  del dueño, y desde ahí confundía a todos. Ahora (1) sin nombre, pregunta
  «¿cómo se llama?»; (2) una foto nueva guardada con un nombre tiene que
  parecerse a las fotos que ya tiene esa persona, si no, la rechaza; (3) al
  arrancar, Sergio **repara solo** la lista: si a una persona le guardaron
  caras ajenas, se queda solo con el grupo de fotos que se parecen entre sí
  (probado con fotos reales: de 13 fotos mezcladas quedaron las 8 correctas,
  y la otra persona dejó de salir como Daniel); (4) en la cámara, si una cara
  se ve clara y no es nadie conocido, el nombre anterior se borra al
  instante (ya no «hereda» el nombre de quien estaba ahí).
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

- **Órdenes al instante** (sin esperar a la IA): «Sergio, abre Spotify»,
  «cierra Chrome», «busca Nvidia», «abre YouTube y busca…», «busca recetas en
  YouTube», «abre gmail», «sube/baja el volumen», «silencia», «pausa»,
  «siguiente canción», «captura de pantalla», «minimiza todo», «¿qué hora
  es?», «¿qué día es hoy?», «abre/cierra la cámara», «abre el globo»,
  «muéstrame Quito en el globo», «¿qué avión pasa encima?», «crea un cubo»,
  «pásalo a Blender», «toma una foto», «cállate».
- **Más rápido**: la charla normal va directa al modelo (sin el agente de
  herramientas), empieza a hablar con la primera frase mientras prepara el
  resto, recuerda el audio de frases cortas y escucha con Gemini Flash-Lite.
  Cada acción en pantalla comprueba qué ventana quedó al frente.
- **Reconoce caras solo**: con la cámara abierta pone el nombre sobre cada
  cara (o «Desconocido») y te saluda cuando apareces. «Sergio, aprende mi
  cara» ahora toma cinco fotos (mueve un poco la cabeza).
- **Conversación de verdad**: después de responder sigue escuchándote unos
  segundos, así que puedes contestarle sin volver a decir «Sergio». Habla
  como un caballero británico culto (y en español), recuerda lo que dijiste
  y te pregunta cuando no entiende.
- **Voz y oído de Gemini**: voz humana y nítida de caballero británico de
  unos cuarenta años (Gemini TTS; puedes elegir entre varias en el notch), y
  Gemini escucha lo que le dices a Sergio (mucho mejor que Whisper en el
  procesador). El Whisper local solo vigila la palabra «Sergio».
- **Con tus manos** (cámara → botón *Manos*, o «Sergio, quiero usar las
  manos»): *Gestos* (pulgar arriba = sí, mano abierta = calla, dos dedos = ¿qué ves?), *Mouse* (la mano
  mueve el puntero sin temblar, pellizco = clic, mantener = arrastrar,
  pulgar con el medio = clic derecho, dos dedos arriba/abajo = desplazar,
  puño = pausa) y
  *3D* (en Blender: pellizca y mueve para girar, dos manos para escalar,
  puño para mover, pulgar arriba añade un cubo, dos dedos duplica). «Sergio, abre Blender y
  crea un jarrón que pueda moldear con las manos».
- **Prueba de verdad**: `sergio probar` usa a Sergio en tu laptop —
  cerebro con herramientas, voz, oído, pantalla, abrir y cerrar el Bloc de
  notas, terminal, cámara, visión, caras, manos y globo— y dice qué falla.
- **Mantén Ctrl+Alt y habla (como Clicky)**: mientras mantienes las teclas
  te escucha; al soltarlas mira tu pantalla, te responde como un maestro
  paciente y la esfera vuela a señalar el botón. Si vuelves a hablar mientras
  responde, lo interrumpes. (Ctrl+Alt+C y AltGr siguen funcionando normal.)
- **Tiene vida**: duerme con «z» si no mueves el mouse un rato, despierta de
  un saltito, se estira al moverse rápido, salta cuando haces clic, sonríe
  después de responder, muestra una onda mientras te escucha y puntos
  girando mientras piensa. Si lo ocultas, igual aparece cuando le hablas.
- **Cerebro**: Gemini 3.8 Flash para lo rápido y Gemini 3.1 Pro para lo
  difícil, con niveles de esfuerzo. En el notch: *Auto* (elige solo),
  *Rápido*, *Normal* o *Profundo*. Si Pro no está disponible con tu clave,
  usa Flash pensando a fondo.
- **Centro de control en el notch** (clic en el notch): se despliega como
  el Dynamic Island, en negro, con cuatro pestañas:
  - *Inicio*: escríbele a Sergio (útil si no te oye bien) o pulsa Hablar, y
    botones estilo iPhone para «Escuchar Sergio», control de pantalla,
    cámara y la esfera junto al cursor.
  - *Sergio* (estilo Muse de Meta; su nombre es siempre Sergio):
    estilo *Orbe de luz* o *Personaje*, color (o el tuyo), ojos, boca,
    accesorio (sombrero de copa, monóculo, corbatín, laurel, gorra, gafas,
    audífonos, moño, gorro de fiesta, corona), personalidad (por defecto
    *Caballero británico*), voz, velocidad y tamaño — todo en vivo.
  - *Mundo* (God's Eye View): sismos de las últimas 24 h y próximos
    lanzamientos, y «Ir a un lugar» abre el globo 3D en su propia ventana
    (sin barras de navegador).
  - *Guías*: busca una guía experta de ECC y «Usar esta guía».
- **Te ayuda con tu pantalla, como Clicky**: «Sergio, ¿dónde está el botón
  de exportar?», «¿qué es esto?», «explícame esto». Mira tu pantalla,
  te responde en voz alta y la esfera **vuela hasta el botón y lo señala**
  con un círculo. Si le das una orden («haz clic en Guardar»), lo hace.
- **Sergio ve** (cámara flotante, Ctrl+Alt+C): marca las caras en vivo, y
  tiene botones *¿Qué ves?*, *Espejo* y *Foto* (se guarda en
  Imágenes\\Sergio); su respuesta aparece escrita sobre la imagen.
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

## Hablar con Sergio como en una llamada

**Personalidad**: brillante, carismático y sarcástico — humor seco, ironía
elegante y remates rápidos, pero primero resuelve y, si el momento es serio,
baja la ironía. («Tres monitores suelen ser suficientes para la mayoría de los
mortales, a menos que esté intentando vigilar toda la bolsa de Wall Street.»)
Se cambia en «Personalizar a Sergio».

Sergio habla con una **voz masculina grave, relajada y algo rasposa**
(«Algenib», de Gemini Live), en las llamadas y en las respuestas por turnos,
así suena siempre igual. Una copia 1:1 de la voz de un actor real (p. ej.
Brad Pitt) no se hace: clonar o imitar la voz de una persona real no es
legal ni ético; Algenib es la voz de Gemini más parecida a ese estilo. Otra
voz se elige en «Personalizar a Sergio».

**Voz aún más grave y rasposa, y más rápida (opcional, ElevenLabs)**: una voz
original de la biblioteca de ElevenLabs («J Thomas — Warm, Raspy & Real»:
cálida, grave, con aspereza en los tonos bajos, relajada). No imita a nadie.
Empieza a sonar casi al instante (modelo Flash, en streaming). Actívala con
tu clave de ElevenLabs:

```bash
sergio nube voz --elevenlabs TU_CLAVE
```

Desde ahí las respuestas por turnos usan esa voz; las llamadas en vivo siguen
con Gemini Live (Algenib), que ya contesta en menos de un segundo. Si se acaba
el crédito o falla, vuelve sola a Algenib. También se elige en «Personalizar
a Sergio».

**Sin esperas**: en las llamadas Gemini no «piensa» antes de hablar (primera
palabra en ~0,7 s) y las respuestas por turnos se oyen mientras se generan
(empiezan a sonar en ~2 s). Si un modelo está saturado o sin cuota, Sergio lo
recuerda y no vuelve a esperarlo.

Di «Sergio…» (o pulsa Ctrl+Espacio) y empieza una **llamada en tiempo real**
(Gemini Live): contesta en menos de un segundo, puedes interrumpirlo
hablando, y sigue escuchándote sin repetir su nombre. La llamada se cuelga
sola tras un minuto de silencio, cuando te despides («gracias, eso es todo»)
o con Ctrl+Espacio. El notch muestra una píldora verde con el tiempo.

* **Oído instantáneo**: un reconocedor pequeño (Vosk, 40 MB, sin internet)
  escucha la palabra «Sergio» mientras hablas. En cuanto la oye, la llamada
  ya se está conectando y tus palabras se guardan; al terminar la frase, se
  la entrega completa. Antes cada ruido de la sala pasaba por Whisper (varios
  segundos y el micrófono quedaba sordo mientras tanto): por eso a veces no
  te oía o contestaba tarde. Si dices «Sergio» en medio de otra frase
  («ayer vi a Sergio») no se activa.
* Si una llamada falla, vuelve a intentarlo a los 20 segundos (antes
  esperaba 10 minutos) y te dice el motivo en pantalla.
* `sergio probar` y `sergio revisar` muestran la línea de tiempo de la última
  vez que lo llamaste (cuándo oyó «Sergio», cuándo conectó, cuándo habló),
  para ver qué parte tarda.
* Te oye aunque suene por los parlantes del laptop: cancelación de eco WebRTC.
* Si la cámara está abierta, **ve lo que ve la cámara**; «mira mi pantalla»
  o mantener Ctrl+Alt le enseña tu pantalla.
* Durante la llamada usa sus herramientas al instante: abrir y cerrar apps o
  webs, buscar, volumen y música, señalar, cámara, hologramas, Blender,
  vuelos, fotos y caras, recordatorios, estado del sistema, protocolos,
  archivos, terminal, Python, video y el globo. Los encargos largos
  («tarea») corren en segundo plano y te avisa al terminar.
* Si la llamada no puede abrirse (sin cuota de Gemini Live), Sergio vuelve a
  responder por turnos. `"conversation": "turnos"` en `config.json` lo deja
  siempre por turnos.

## Abrir y cerrar apps al instante

«Sergio, abre Spotify» ya no escribe en el menú Inicio: Sergio conoce todas
las apps de tu menú Inicio (y las de la Tienda) y la abre directamente, en
menos de un segundo, **en la pantalla donde tienes el mouse** y al frente.
Entiende cómo las llamas («la calculadora», «el Word», «bloc de notas»,
«configuración»). Para cerrar busca el programa, no solo el título (la
ventana de Spotify se llama como la canción). Las capturas de pantalla
también son de la pantalla que estás usando.

También al instante, sin IA: «maximiza / minimiza / cierra esta ventana»,
«cambia de ventana», «nueva pestaña», «copia», «pega», «guarda», «deshaz»,
«pon el brillo al 70», «baja el brillo», «modo oscuro», «pon el volumen al
30», «abre la configuración del wifi / bluetooth / pantalla», «abre
descargas», «escribe: hola». Funciona igual dicho con cortesía («¿me puedes
abrir el Word, por favor?») y en la llamada. Si le pides varias cosas
seguidas, las hace en orden (antes ignoraba las que llegaban mientras
hablaba). WhatsApp y Spotify abren la app instalada; si no está, su web.

**Videos de YouTube como los describes**: «pon un video de MrBeast en el que
salga con traje negro». Sergio busca, Gemini mira las miniaturas de los
primeros resultados y elige el que cumple lo que pediste, y el cursor lo abre
con un clic a la vista (si no lo encuentra en pantalla, lo abre directo).

## Mouse y teclado como una persona

**Sin demora (modo rápido, el de siempre ahora)**: el puntero llega en una
décima de segundo (lo ves deslizarse, pero no espera), el clic dura 20 ms y
el texto aparece de golpe (antes: 0,4–0,7 s por movimiento y 85 ms por
letra; 100 letras eran 8,5 s). Después de cada acción ya no hay pausas
fijas: mira la ventana y sigue en cuanto cambia. Si mueves tú el mouse, o con
Ctrl+Alt+Fin, se detiene. Para grabar videos con el estilo «mano humana»
lenta: `"control_speed": "humano"` en `config.json`.

**Órdenes de pantalla al instante (sin pasar por la IA)**:

* «**Haz clic en Suscribirse**», «pulsa el botón Enviar», «dale a Aceptar»,
  «toca Me gusta», «haz doble clic en Documentos», «clic derecho en la
  papelera»: busca el botón por su nombre en la ventana de enfrente (aunque lo
  digas sin tilde o parecido) y hace clic. Si no lo encuentra, se lo pasa a la
  IA, que mira la pantalla.
* «Presiona enter», «dale tab dos veces», «flecha abajo 3 veces», «escape».
* «Baja», «sube», «más abajo», «ve al final», «ve al inicio».
* «Atrás», «adelante», «siguiente pestaña», «pestaña anterior», «reabre la
  pestaña», «historial», «modo incógnito», «zoom normal».
* «**Cambia a Chrome**», «trae Spotify al frente» (si no está abierto, lo abre).
* «Escribe hola, ¿cómo estás? y dale enter».
* Estas órdenes se confirman **en pantalla, sin voz**, para que puedas dar la
  siguiente enseguida (`"confirm_aloud": true` las vuelve a decir en voz alta).
* La IA también ganó «clic por nombre»: un paso en vez de mirar la pantalla y
  luego hacer clic. Las capturas de pantalla se preparan más rápido y la
  lectura de botones tiene un tope de 2 s (antes 4 s).

> Mensajes, correos y llamadas a otras personas (Instagram, WhatsApp, Gmail,
> teléfono): la pieza que lo hace está escrita pero **no está conectada** en
> esta versión; el sistema de permisos de Claude bloqueó conectarla. Ver el
> mensaje de la actualización.

## Sergio ve: cámara y hologramas

La ventana de la cámara ya **no tiene botones**: todo es por voz y con las
manos. Arrástrala para moverla, rueda del mouse para el tamaño.

**Vista limpia**: solo lo útil a la vista — el nombre de cada persona (sobre
su cabeza), lo que tienes en la mano, animales, los puntos de tu cara y los
hologramas. Sergio **sigue midiendo todo** (distancia a la pantalla,
parpadeos, a dónde miras, postura, manos, ánimo) y te avisa si hace falta;
pregúntale «**qué mides**» o «cómo está mi postura» y te lo dice. «**Muestra
los datos**» los pone en pantalla; «**modo limpio**» los quita.

**Lo que ve**

* Detector moderno **YOLO11** (Ultralytics; en la tarjeta NVIDIA si la hay):
  se equivoca mucho menos que el anterior (una ventana ya no es «televisor»
  ni una hoodie «corbata»). Si no se pudo instalar, usa el anterior.
* **Segunda opinión con vocabulario propio (YOLOE)**: un segundo modelo busca
  66 cosas por su nombre en español (labial, audífonos, taza, control…). Si
  YOLO11 duda, gana el nombre preciso; si los dos discrepan en un animal,
  Gemini decide. En una NVIDIA corre en la GPU (CUDA, media precisión, más de
  15 imágenes por segundo); el instalador pone PyTorch con CUDA solo si hay
  `nvidia-smi`.
* **Medido, no supuesto** (COCO128, 128 fotos etiquetadas a mano): de cada 100
  nombres que muestra, **92–94 son correctos** (94 con el modelo de la GPU), y
  encuentra el 69–74 % de las cosas visibles. Revisé a ojo los nombres extra
  de YOLOE: con poca confianza fallaban mucho («anillo» sobre la piel,
  «labial» en una sonrisa); ahora cada nombre necesita estar seguro, salvo lo
  que tienes **en la mano**, que es justo para lo que sirve (de ~55 % a ~85 %
  de aciertos en esos nombres).
* **Tus manos nunca son cosas**: Sergio sigue tus manos y descarta lo que el
  detector confunde con ellas (plátano, «otra persona», un dedo). Lo que
  sostienes se marca «en tu mano» y Gemini le pone su nombre real de cerca.
* **Menos ruido**: sin porcentajes ni muebles; solo personas, animales, lo
  que tienes en la mano y unas pocas cosas destacadas.
* **Caras con rasgos, no siluetas**: una red de puntos característicos (ojos,
  cejas, nariz, boca, pómulos, mandíbula) y las distancias entre ellos —las
  175 medidas— con el nombre pegado a la cara.
* **Tus manos, cara y cuerpo**: qué mano, cuántos dedos, el gesto y hacia
  dónde señalas; a dónde miras, parpadeos por minuto, ojos cansados y la
  distancia a la pantalla (por el tamaño del iris); tu postura (te avisa con
  amabilidad si llevas un rato encorvado, con los ojos cansados o demasiado
  cerca) y las sentadillas que haces.
* «Analiza lo que ves» describe todo con detalle; «toma una foto», «modo
  espejo», «abre / cierra la cámara».

**Hologramas 3D con tus manos (estilo Iron Man)**

* **Hologramas de cualquier cosa**: «haz un holograma de un teléfono», «haz un
  modelo de una silla gamer», «modela un dron en 3D» (con los hologramas
  activos basta «crea una guitarra eléctrica»). Gemini lo diseña **pieza por
  pieza con medidas reales**: un teléfono salió con 20 piezas (cuerpo
  redondeado, cristal, módulo de cámaras con 3 lentes y sus anillos, flash,
  LiDAR, botones, USB-C, altavoz). Se ve con sus materiales y su tamaño real
  (16 cm), y se mueve y gira con las manos como cualquier holograma. Las
  formas simples («crea un cubo rojo») siguen siendo instantáneas.
* **Blender sincronizado en vivo**: «pásalo a Blender» abre Blender con los
  hologramas a tamaño real y con sus materiales, y **sigue a tus manos**: lo que
  muevas, gires, agrandes, esculpas, crees o borres se ve en Blender al
  instante (antes era una copia fija). Guarda con Ctrl+S en Blender.
* Para los objetos diseñados, **Blender Pro** hace además la versión detallada
  y profesional, partiendo de esas mismas piezas, y te avisa al terminar.

* **Para empezar**: «Sergio, activa las manos» (o «modo hologramas»). Aparece
  un cubo y, arriba a la derecha, la guía de gestos durante 25 segundos; para
  verla otra vez: «ayuda hologramas». Para guardarlo: «pásalo a Blender».
* «Crea un cubo rojo», «crea dos esferas», cilindro, cono, toroide,
  pirámide, jarrón, diamante.
* **Pellizca** (pulgar con índice) un holograma para agarrarlo: te sigue,
  **gira igual que tu muñeca**, y se acerca o aleja si acercas o alejas la
  mano. **Suéltalo en movimiento** y sale volando y girando. Pasa la mano
  abierta rápido por encima y lo haces girar como un globo.
* **Dos manos** pellizcando: sepáralas para agrandarlo, gíralas para rotarlo.
* «**Modo esculpir**»: pellizca la superficie y tira; la «arcilla» se
  deforma suavemente. «Suavízalo» la alisa.
* «**Modo dibujar**»: pellizca en el aire y dibuja; al soltar, el trazo se
  vuelve un tubo 3D. «Dibuja con el torno» convierte un perfil en un jarrón;
  «dibuja una silueta» la vuelve un sólido.
* «Más grande», «gíralo», «duplícalo», «bórralo», «borra todo»,
  «activa la gravedad» (caen, rebotan y se pueden lanzar).
* Se ven como en las películas: luz azul, líneas de escaneo, un anillo
  proyector bajo cada holograma y anillos que giran cuando lo sujetas.
* **También con el mouse**: arrastra para moverlo, clic derecho y arrastra
  para girarlo, Ctrl + rueda para el tamaño.
* **Y con la voz**: «muévelo a la izquierda», «súbelo», «gíralo 90 grados»,
  «voltéalo», «céntralo», «más grande».
* Ya no hay control de la computadora por gestos ni mouse en el aire: las
  manos son para los hologramas.

## Blender

* «**Pásalo a Blender**»: tus hologramas (con lo que esculpiste o dibujaste)
  se reconstruyen en Blender con materiales, luz y cámara, y el proyecto se
  guarda en `Documentos\Sergio\Blender`.
* «**Analiza el objeto que tengo en las manos y pásalo a Blender**»: Gemini
  estudia la foto de la cámara (qué es, medidas reales, piezas, materiales)
  y escribe un modelo detallado; Sergio revisa que el script solo modele
  (nada de archivos, internet ni programas) y Blender lo construye y guarda
  el `.blend`. Tarda uno o dos minutos. Probado de verdad: de una foto de un
  reloj salió un modelo de 97 piezas (caja, corona, eslabones, broche).
* **Blender Pro ya no se cae por un detalle**: antes, un solo error de la API
  de Blender (un nombre de material mal escrito) paraba todo el script y
  quedaba un cubo o nada. Ahora el modelo se construye paso a paso: si un paso
  falla, se salta, el resto se construye y guarda, y la siguiente revisión
  corrige ese paso. Probado: el mismo script que fallaba 3 veces dio un
  teléfono de 41 piezas. Además primero diseña las piezas reales del objeto y
  exige detalle (un teléfono, 20+ piezas; nunca un cubo con otro nombre).
* **Blender Pro** («en Blender haz una casa low poly con techo rojo», «haz un
  logo 3D de Sergio en metal en Blender»): Gemini escribe la escena, Blender
  hace un render rápido sin abrir ventana, Gemini **mira el render** (y la
  foto del objeto, si la hay) y el registro de errores, corrige y repite
  (dos revisiones visuales y hasta cuatro arreglos de errores). Al final se
  abre el `.blend` listo. Tarda varios minutos y usa Gemini Pro.
* Necesitas Blender instalado (`winget install BlenderFoundation.Blender`).

## Video Pro: editar y subir videos

* «**Edita un video con la carpeta Viaje para YouTube Shorts**»: Sergio mira
  cada clip (una hoja con 12 fotogramas marcados con su tiempo), Gemini hace
  de editor (los mejores momentos, gancho en los primeros 3 s, ritmo, textos
  cortos, título) y ffmpeg lo monta: recortes, formato 9:16 o 16:9,
  fundidos, textos, volumen normalizado a −14 LUFS (lo de YouTube) y música
  que baja sola cuando alguien habla. Queda en `Videos\Sergio`, con un `.txt`
  con título, descripción y etiquetas para YouTube.
* «**Súbelo a YouTube**»: abre YouTube Studio, te deja el archivo señalado y
  copia el título y la descripción. **Tú pulsas Publicar**: Sergio no publica
  nada en tu nombre.

## Caras: firma de 175 medidas, fotos antiguas y parecido familiar

* Cada persona registrada guarda dos descripciones de su cara: la red
  neuronal (SFace) que decide quién es, y una **firma geométrica de 175
  medidas** sobre la malla 3D de 478 puntos: 153 distancias entre 18 puntos
  óseos (comisuras de ojos, pupilas, raíz y punta de la nariz, alas nasales,
  pómulos, ángulos de la mandíbula, mentón, frente), 10 índices
  antropométricos (facial, nasal, intercantal, boca/cara…) y 12 ángulos. No
  cambia con la distancia ni con el giro de la cabeza.
* «¿Quién es el de esta foto?»: sostén la foto frente a la cámara, o
  «…de la foto de la pantalla», o un archivo. Las fotos viejas, descoloridas
  o escaneadas se mejoran antes (contraste local). Si no está seguro, dice a
  quién se parece y cuánto, sin inventar nombres.
* «¿A quién se parece?» / «¿es hermano de Daniel?»: estima el **parecido
  familiar** con las personas registradas. Es un indicio por rasgos y
  proporciones, **no una prueba**: solo el ADN confirma un parentesco.
* Probado con caras reales: la misma cara «envejecida» como foto antigua
  sigue reconociéndose (similitud media 0,80; mínimo 0,67 con la mejora), y
  personas distintas quedan en 0,10 de media.

## Vuelos encima de ti y el globo

* «**¿Qué avión pasa encima?**»: Sergio usa tu ubicación exacta (la de
  Windows: GPS o Wi-Fi) y la hora, pregunta a la vez a cuatro redes ADS-B
  (adsb.lol, airplanes.live, adsb.fi y OpenSky, las de God's Eye View), y
  en pocos segundos te dice cuál está más alto en tu cielo: vuelo,
  aerolínea, avión, matrícula, ruta, altura, velocidad y hacia dónde mirar.
  Tiene en cuenta que Cuenca está a 2 500 m. Deja God's Eye View apuntando a
  ese avión: «muéstramelo» lo abre.
* «**Muéstrame Cuenca en God's Eye View**»: abre el globo en esa ciudad (los
  nombres sin país se buscan primero en Ecuador).
* Activa la ubicación: Configuración > Privacidad y seguridad > Ubicación
  (también «Permitir que las aplicaciones de escritorio…»). Sin ella usa la
  ubicación aproximada por internet. En Ecuador las redes abiertas tienen
  pocas antenas: puede que no vea todos los aviones.

## Funciones tipo JARVIS

* «Recuérdame en 10 minutos sacar la ropa», «pon una alarma a las 7 y
  media», «¿qué recordatorios tengo?», «cancela las alarmas». Sobreviven a
  un reinicio.
* «¿Cómo está la batería?» / «estado del sistema»: batería, procesador,
  memoria y disco.
* «Dame el informe»: hora, fecha, batería y pendientes del día.
* Protocolos: «protocolo trabajo» (correo y agenda), «modo concentración»,
  «modo fiesta», «protocolo descanso», «modo música». Puedes crear los tuyos
  en `config.json` → `"protocolos"`.

## Gimnasio mental (cada 12 minutos)

Cada **12 minutos de reloj** (de inicio a inicio; cuenta también si
reinicias Sergio) aparece un ejercicio a pantalla completa que **no se
puede saltar**. Termina solo y Sergio te dice cómo te fue. Si estás lejos
(5 minutos sin tocar la computadora) o está bloqueada, espera a que vuelvas.
Si la laptop se suspende o se apaga, no corre: al volver espera unos minutos,
un ejercicio interrumpido vuelve a empezar, y si nadie respondió no cuenta (ya
no sale «0 · a seguir entrenando»). Antes de cada uno tienes **11 segundos**
con los pasos explicados y un **ejemplo animado** de cómo se resuelve.

| Ejercicio | Cantidad y tiempo |
|---|---|
| Interferencia tipo Stroop | 15 en 1,5 min |
| Cálculo mental aleatorio | 10 en 1,5 min |
| Detección de patrones asimétricos | 20 en 1,5 min |
| Dual N-Back adaptativo (micro) | 1 bloque continuo de 2 min |
| Marcos relacionales lógicos | 3 problemas en 2 min |
| Rotación mental de objetos (3D) | 5 figuras en 2 min |
| Retención de listas invertidas | 4 secuencias en 2 min |
| Matrices progresivas | 2 matrices en 2 min |
| Asociación de palabras restringida | 3 desafíos en 2 min |
| Secuencias de coordinación (dos manos) | 5 patrones en 2 min |
| Repaso espaciado (recuperación activa) | 6 preguntas en 2 min |
| Pausa activa (sentadillas / saltos) | 1 minuto |

**El orden sigue la evidencia**: los cuatro con mejores estudios salen el
doble de veces (dual n-back, matrices, rotación mental y repaso espaciado),
y cada ejercicio muestra antes por qué está ahí:

* **Dual n-back**: el más estudiado para la inteligencia fluida; metaanálisis
  g = 0,24 (Au et al., 2015), casi 0 frente a controles activos.
* **Matrices**: practicar el formato de los tests de CI sube 0,23–0,42 DE en
  esos tests (Scharfen et al., 2018), aunque no la inteligencia general.
* **Rotación mental**: el entrenamiento espacial mejora, dura y se transfiere
  a otras tareas espaciales, g = 0,47 (Uttal et al., 2013).
* **Repaso espaciado**: la técnica de aprendizaje con más evidencia, g = 0,61
  (Adesope et al., 2017). Lo que aciertas vuelve a 1, 3, 7, 16 y 35 días.
* **Pausa activa**: un minuto de ejercicio intenso mejora un poco la función
  ejecutiva en los minutos siguientes (metaanálisis de 113 estudios).
* Lo único con efecto demostrado y grande sobre el CI es **aprender**: cada año
  de educación suma 1 a 5 puntos (Ritchie y Tucker-Drob, 2018).

**¿Funciona? Lo que dice la ciencia, sin adornos**

* Mejorarás en los ejercicios que practicas (eso está bien demostrado). Pero
  que eso se traslade a la inteligencia general o a la vida diaria
  («transferencia lejana») **no tiene evidencia sólida**: la revisión de
  Simons et al. (2016, *Psychological Science in the Public Interest*, 132
  estudios) y el metaanálisis de Melby-Lervåg, Redick y Hulme (2016, 87
  publicaciones) no encontraron mejoras fiables fuera de lo entrenado.
* La excepción más citada es el entrenamiento de velocidad de procesamiento
  del estudio ACTIVE (2 802 mayores, 10 años): 29 % menos riesgo de demencia
  (Edwards et al., 2017), aunque es un análisis secundario y discutido.
* Las pausas cortas sí ayudan a sentirse con más energía y menos cansado
  (metaanálisis de Albulescu et al., 2022: efecto pequeño), pero no
  mejoraron el rendimiento en tareas exigentes.
* Ojo con el costo: interrumpir cada 12 minutos sube el estrés y deja
  «residuo de atención» en lo que hacías (Mark et al., 2008; Leroy, 2009).

**Cómo lo comprueba Sergio contigo (prueba científica personal)**: el primer
ejercicio de cada día es una **prueba de control que no se entrena**
(sustitución dígito-símbolo, una medida estándar de velocidad de
procesamiento, con la clave cambiada cada vez). Sergio compara tu progreso
en los ejercicios entrenados con la tendencia de esa prueba, con un
intervalo de confianza del 95 %. Pregúntale «¿funciona el gimnasio mental?»:
si la prueba no entrenada no sube, te lo dirá. Necesita 5 días de datos.

**Tu perfil personal**: cada respuesta se evalúa (acierto y rapidez) y arma
tu perfil por habilidad, de 0 a 100: memoria de trabajo, razonamiento,
visoespacial, atención, cálculo mental, fluidez verbal, memoria a largo plazo
y coordinación (las sesiones recientes pesan más; el n-back cuenta el nivel).
Al terminar cada ejercicio Sergio te compara **contigo mismo** («mejor que
tu media en razonamiento (72 %), y más rápido»), y **una de cada tres veces
te pone lo que más te cuesta**. Pregúntale «¿cómo va mi perfil mental?» o
«¿funciona el gimnasio mental?».

**Mira que estés ahí**: antes de empezar, Sergio enciende la cámara unos
segundos y busca una cara (de frente o de lado). Si no te ve, no empieza y
vuelve a mirar cada minuto; en cuanto te ve, arranca. Todo se analiza en tu
laptop: no se guarda ninguna imagen ni se envía a internet, y la luz de la
cámara se apaga enseguida. Si no hay cámara (o la usa otra app), decide el
teclado como antes. Se apaga con `"gym_camera": false`.

Para hacer uno ya: «Sergio, gimnasio mental». Se cambia en `config.json`
(`"gym"`, `"gym_minutes"`, `"gym_camera"`).

## Modelos en la nube: Kimi y Gemini

Para respuestas más rápidas e inteligentes que el modelo local, Sergio puede
pensar con **Kimi** (Moonshot) o **Gemini** (Google):

```bash
sergio nube configurar      # pide las claves (no se ven al escribir)
```

- Comprueba la clave de Kimi, elige su mejor modelo (p. ej. `kimi-k2.6`) y lo
  deja como principal; `qwen3:8b` queda de respaldo si no hay internet.
- Solo con Gemini: `sergio nube configurar --gemini TU_CLAVE` usa
  `gemini-3.8-flash` (y `gemini-3.1-pro-preview` para tareas difíciles). La
  clave puede ser de AI Studio o de Vertex: Sergio prueba las dos. Si la clave
  de Kimi falla, la de Gemini se guarda igual.
- **Globo 3D**: si no estaba encendido, Sergio lo arranca al abrirlo (la
  primera vez tarda un minuto). `sergio revisar` dice por qué si no arranca.
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
  tarea, por eso cada tarea espera tu aprobación en la campana (5 minutos;
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

# Bitácora del equipo (Codex y Claude)

Lo más reciente arriba. Cada sesión añade una entrada (ver AGENTS.md §5).

## 2026-10-13 · Claude · 7632a4b…(este envío) (diseño ChatGPT, Dots y programas reales)
- Diseño igual a ChatGPT (petición del dueño: «no vibe coded»): una sola
  barra lateral (nuevo chat, buscar chats, biblioteca, secciones, chats, la
  conversación y «Señor»), plegable a carril de iconos y cajón en el móvil;
  paleta neutra (#fff/#212121, barra #f9f9f9/#181818), letra del sistema,
  botones negros (blancos de noche), burbuja gris del usuario, respuestas sin
  burbuja, compositor con el anillo de ChatGPT y botón de voz negro con
  barras. Se quitaron degradados, colores por sección y el panel de historial
  aparte. Ctrl/⌘ ⇧ O abre un chat nuevo.
- Nodes: los personajes ya no son de fieltro (el filtro de pelo daba miedo);
  ahora son juguetes de vinilo brillantes como los Dots, con elenco propio
  (guijarro, mochi, gotita, corazón, ranita, osito, estrella, fantasmita,
  setita, cactus y planeta). Los aspectos guardados siguen valiendo.
- Creator sobre programas reales: Diseño = OpenDesign (MIT) dentro de la web,
  traducido al español al instalarlo, y «Pídale un diseño a Sergio» lo crea
  allí (probado: post en 6 s, editable); Código = VSCodium web (reh-web, con
  token) + VSCodium de Windows; Arquitectura = plano → IFC4 con IfcOpenShell
  (muros, puertas y ventanas recortadas) o DXF, abierto en FreeCAD, Bonsai o
  LibreCAD; Imagen y video = ArtCraft + Kdenlive; Bolsa = Kronos en su propio
  Python (torch CPU). Los de Windows los instala y abre
  `sergio_escritorio/creator_apps.py` (winget o la versión de GitHub; Bonsai
  vía extensiones de Blender) y el instalador los pide en segundo plano.
- «Anatomy» ya no es una pestaña: la herramienta sigue siempre activa y la
  lámina se dibuja dentro de la respuesta del chat (el enlace no se ve ni se
  lee en voz alta). `/creator/anatomia` redirige a Creator.
- Revisé lo de Codex: no hubo cambios nuevos en `main` desde e1396e7.
- Pendiente / para el otro: no pude probar aquí nada de Windows (ArtCraft,
  Kdenlive, FreeCAD, LibreCAD, Bonsai), ni VSCodium web ni Kronos con datos
  reales (este entorno bloquea GitHub-descargas, Hugging Face y los datos de
  bolsa): quedaron probados con dobles. LidoJS no se usa (sin licencia
  abierta). Fallos viejos que siguen: tests/tools/test_http_request (red) y
  el PDF malformado de subida.

## 2026-10-12 · Claude · 6123384…5b43cfe (pedido grande del dueño)
- Para el usuario común: el chat contesta enseguida y con el carácter de
  Sergio (persona escrita en `persona.py`, pensamiento «bajo» por defecto en
  Gemini 3.x), aspecto nuevo (Inter, degradado aurora, color por sección) en
  todas las páginas, y la voz siempre activa en la web (`liveSession.ts`,
  orbe en la barra, subtítulos arriba; sin botón de llamada).
- Face ID de Sergio (`faces/faceid.py`): las reglas de Apple adaptadas a una
  webcam (reto aleatorio, giro sostenido, parpadeo con brillo, plantillas
  cifradas, código con esperas, 5 fallos, 48 h). 15/15 ataques con foto
  rechazados en pruebas. Sin promesas de 1 en 1 000 000: es una webcam.
- Una sola marca: Sergio. «OpenJarvis» ya no se ve; créditos en NOTICE.
- Skill «anatomy» (MIT) convertida (`creator/anatomy`, herramienta
  `anatomy_figure`) y **Creator** (`/creator`): Modelado 3D y Arquitectura
  (three.js, atajos de Blender, GLB, muros, DXF, guion para Blender), Diseño
  e Imagen (Fabric.js, diseños de Sergio, recorte con red U²-Net local),
  Anatomía y Código (Monaco, ejecutar acotado, cambios de Sergio como diff).
- Respaldo en paralelo para Gemini (`engine/hedge.py`) en el chat, el
  coach/cerebro, Creator y el diseño 3D: con Google saturado una respuesta
  tardaba 1-3 min; ahora otro modelo entra a los pocos segundos.
- Agent Swarm: registro «En vivo» de lo que hace cada parte; reparto por
  elementos si el orquestador falla; informe legible (tabla) si el supervisor
  falla. Probado: 7 agentes, 5 a la vez, 53 s.
- Nodes: «Reglas propias» en palabras con revisión por código antes de cada
  acción (como Dots) y sugerencias de siguientes pasos (como Muse).
- Workspace: vistas Lista/Galería/Calendario, columnas de varias opciones,
  enlace, correo y teléfono, bloques Ecuación/Índice/Marcador, historial de
  versiones con restaurar.
- Revisé lo de Codex: faltaban `verified_math` y `scene_reason` en el
  inventario de capacidades (añadidas) y el formato de algunos tests.
- Pendiente / para Codex: los 200 tests de motores locales en
  `tests/engine` fallan en este entorno sin red simulada (ya fallaban antes);
  el de PDF malformado sigue necesitando pdfplumber o PyPDF2. La clave de
  prueba de Gemini no tiene cuota de imágenes (Imagen/Veo): con la del dueño
  sí, si su cuenta la tiene.

## 2026-10-12 · Claude · actualizador + 3 commits de Codex
- El comando universal fallaba en el PC del dueño con «Instala Node 22.22+»:
  `bash -lc` desde PowerShell no ve el Node del instalador. Ahora
  `scripts/actualizar-sergio.sh` y `sergio servicio instalar` añaden solos
  `~/.local/share/sergio-toolchain/node-*/bin` al PATH.
- Revisé lo nuevo de Codex (60d5459, 864383e, 1a532a4) y lo traje a main.
  **Ojo, Codex:** su 864383e fusionó un `main` viejo (0549820) y, al hacerlo,
  borraba su propio trabajo anterior (upload_limits, process_runner,
  windows_job, test_sergio_update…). Un merge normal lo habría borrado de main.
  Apliqué solo lo que usted cambió en ese merge (voz Live con puerta de
  atención, worklet, verified_math, scene_reason, fiabilidad de rutinas,
  comprobación del SDK Live y `--extra desktop` en el actualizador).
- Mantengo: rama `main` en el actualizador, la regla de que una voz externa
  elegida no se cambia en silencio en llamadas (su test «AlvaroNeural → ''»
  la contradecía; lo quité y dejé el resto de sus tests de llamada).
- Su guardia de red en `tests/conftest.py` es buena; dejé pasar los nombres
  reservados `.test/.example/.invalid` (respx los usa). Actualicé
  `test_escritorio_cmd.py` a sus nuevas herramientas y extras.
- Pendiente para Codex: `git fetch origin && git merge origin/main` antes de
  seguir; trabaje sobre `main`, no sobre su rama vieja. Su función
  `Actualizar-Sergio` antigua del dueño instalaba su rama en
  `~/sergio-versiones`; ya no se usa.

## 2026-10-12 · Claude · fusión en main
- Uní `codex/professional-reliability-audit` con `main`: ahora hay un solo Sergio.
- Nodes: un solo sistema. El Node vive en `nodes/store.py`; lo de Codex
  (objetivos, notas, auditoría, integraciones revisadas Browser-use/OpenClaw,
  claves Dev) pasó a `nodes/records.py` y `server/nodes_pro_routes.py`, colgando
  de los mismos ids: `/v1/nodes/{id}/goals|notes|audit|integrations`. Sus 19
  tests de Codex pasan con las rutas nuevas. En la web: pestaña «Objetivos» e
  «Integraciones revisadas» en Conexiones.
- Voz: se mantiene la regla de Codex (no cambiar la voz elegida en silencio) y
  lo mío (idioma por frase, limpieza, frase anterior). El selector de voz con
  ID propio de ElevenLabs está en Ajustes del panel.
- Personalidad: reglas de fiabilidad de Codex + «señor», caballero y humor negro
  con límites (decisión del dueño).
- Panel: pestañas de main; la lista del Agent Swarm muestra los enjambres del
  servidor y las tareas del PC con el detalle paso a paso de Codex.
- Instalador de Windows: Python oficial firmado (de Codex). `actualizar-sergio.sh`
  ahora usa `main` y reinstala el servicio en `~/sergio`.
- Pendiente para Codex: revisar `nodes_pro_routes.py` (las rutas de su API
  cambiaron de nombre) y el test de PDF malformado, que necesita pdfplumber o
  PyPDF2 instalados para dar 400.

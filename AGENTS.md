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
- Nodes (dueño, oct. 2026): elenco fijo de cuatro y **nadie lo personaliza**:
  rinoceronte de ojos cerrados con camiseta a rayas celeste y blanco,
  dálmata, guante médico azul inflado con boina y cara de marcador, y orbe
  invisible con gafas de leopardo y ojos negros. Dibujados en tinta, con el
  trazo grueso de un dibujo a mano, y animados como un fenaquistoscopio: 12
  cuadros por vuelta, cada uno entintado de nuevo; grande se ve el disco
  (anillo de cuadros que gira de a un paso y ventana central), pequeño un
  medallón de papel (`components/Nodes/NodeCritter.tsx`, solo CSS `steps`).
  Una plantilla decide el personaje; el servidor ignora color, ropa y ojos
  que lleguen de fuera (`nodes/store.py: CAST`, `clean_avatar`). El 3D
  anterior (`dots3d.ts`) ya no existe.
- Sin emojis y sin colores en la interfaz (dueño, oct. 2026): negro, blanco y
  grises; iconos de línea. El color solo vive en lo que el dueño crea (sus
  diseños, fotos, 3D) y en los cuatro personajes de los Nodes.
- Workspace igual a Notion (en blanco y negro), con lo de Notion 2026:
  Biblioteca, secciones de la barra, Papelera, pestañas, Presentar y Panel.
- Creator retirado de la interfaz por petición del dueño (2026-10-16): sin menú
  ni rutas de editor; enlaces antiguos redirigen al chat. Herramientas internas
  y programas instalados (`professional_apps`, `opendesign`, `kronos_forecast`,
  `anatomy_figure`, `blender_create`, `video_edit`) se conservan para uso
  exclusivo de Sergio y sus agentes (Chat, Live, Nodes, Agent Swarm y Cowork).
- Windows es una app: chat/Nodes/Swarm en ventana sin barra de direcciones
  (launch.py, Edge --app), nunca fallback de páginas internas a una pestaña.
  Loopback es transporte interno. Notch: ocultar/recuperar en 220 ms, sin
  partículas ni gotas; respetar movimiento reducido y reposo oculto.
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
- Todo es Sergio: ningún logo ni nombre de empresa externa a la vista
  (los créditos de licencias van en NOTICE, LICENSE y «Acerca de»).
- La conversación de voz está siempre activa en la web (sin botón de
  llamada); en el escritorio se abre al decir «Sergio» y sigue abierta.
- Las llamadas a Gemini van con respaldo en paralelo (`engine/hedge.py`): si
  un modelo tarda, otro empieza y gana la primera respuesta válida. No lo
  quite: con Google saturado, sin él Sergio tardaba minutos.
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

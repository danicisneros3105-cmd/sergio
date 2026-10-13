# Bitácora del equipo (Codex y Claude)

Lo más reciente arriba. Cada sesión añade una entrada (ver AGENTS.md §5).

## 2026-10-13 · Codex · verificación paralela Creator y equivalencia
- Revisé main 7acb4b0 completo y las funciones de Nodes/Swarm/Cowork del equipo,
  con una revisión independiente de Creator autorizada por el señor.
- Resultado: nombres de Creator y ArtCraft 13 representados; no todos los motores
  completos instalados/integrados. LidoJS solo referencia. No hay equivalencia
  completa con Face ID, Muse, Dots, ChatGPT Work o Kimi: carpeta no es VM,
  reglas no son Sentinel y 300 subtareas no son 300 trabajadores simultáneos.
- Corregí esas afirmaciones en docstrings, presentación de Node, texto Swarm y
  NODES-Y-SWARM.md. No cambié el motor, permisos o límites para fingir paridad.
- Consulté 30 refs GitHub: 29 resuelven, The-Swarm-Corporation/swarms devuelve 404.
  Mantengo sus proyectos específicos revisados y los pins; no importo los 163 repos.
- Pruebas actuales: 170 Python pasan, 2 omitidas; 161 frontend, tsc/build y Ruff pasan.
  Browser-use 0.13.11 MCP real: 16 herramientas, cierre; OpenClaw 2026.9.9 CLI real:
  --version exit 0. Instalados solo en entornos de auditoría, sin cuentas personales.
  Anatomy: 93 archivos, 3 adaptaciones, 90 blobs idénticos al pin. SwarmEngine controlado:
  300 subtareas terminadas con parallel solicitado 300 limitado a 64. No benchmark IA.
- El cotejo textual puede aceptar una misma afirmación falsa repetida por un
  subagente: no es verificación de verdad externa. Se documenta ese contraejemplo.
- Entrego matrices VERIFICACION-REPOS-Y-PARIDAD y CREATOR-VERIFICACION,
  inventario JSON y scripts/verificar-integraciones.py de solo lectura.
- Pendiente de uso real: hardware Windows Hello, instalaciones/artefactos de
  aplicaciones, activación Bonsai/IFC, editor OpenDesign, pesos/inferencia Kronos,
  navegación completa Browser-use y Gateway OpenClaw. No atribuyo pruebas
  simuladas a motores reales ni afirmo seguridad/velocidad/calidad iguales.

## 2026-10-13 · Codex · diseño profesional y consentimiento Windows Hello
- Partí de main e1396e7 y conservo su árbol completo, incluidos los cambios de
  Claude y los archivos que faltaban en mi checkout parcial anterior. La rama
  corta es `codex/design-professional-2026-10-12`; esta publicación sustituye
  el estado bloqueado descrito en RECUPERACION-DISENO-2026-10-12.md.
- Estudio reúne 32 programas completos y un instalador WinGet selectivo;
  alias /developer y /creator, adaptadores reales OpenDesign y Kronos aislado.
  No simulo aplicaciones instaladas ni previsiones si faltan los pesos.
- Anatomy MIT está adaptada y incluida como guía interna, siempre aplicada a
  agentes y Live. Mantengo Inter/Josefin, el shell y los personajes del equipo,
  con superficies más calmadas, pelo suave y hologramas sin polos degenerados.
- Revisé la galería y el escaneo de Claude: preservo Fernet, cifro galerías
  heredadas válidas al leerlas, evito regenerar claves perdidas y guardo de
  forma atómica. La webcam sirve para reconocimiento, no autorización segura.
- El compañero y su API de control requieren consentimiento Windows Hello
  para las acciones que necesitan aprobación; errores y cancelaciones deniegan.
  La hoja permite leer la acción íntegra como texto plano, sin truncarla.
- El comando universal conserva los commits locales: eliminé checkout -B
  de AGENTS; el actualizador ya exige fast-forward y crea respaldo.
- Validación final: 720 pruebas escritorio + 526 backend + 161 frontend;
  6 omitidas en Python. Ruff analiza/formatea 1821 archivos; tsc y build pasan.
  Anatomy: 32 pruebas puras. No se ejecutaron los tests Live con Ollama,
  autenticación Windows Hello física, inferencia Kronos con pesos ni todas las
  funciones de las aplicaciones externas. No afirmo equivalencia con Face ID,
  Muse/Dots, ChatGPT o Kimi, ni un rendimiento sin latencia medido.
- Pendiente: instalar/probar los programas en Windows, activar Bonsai en
  Blender, poner los pesos de Kronos y validar Hello en hardware compatible.
  LidoJS queda como referencia por falta de licencia declarada. Véase el
  informe DISENO-Y-APLICACIONES-2026-10-12.md para contratos y comandos.

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

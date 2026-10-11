# Bitácora del equipo (Codex y Claude)

Lo más reciente arriba. Cada sesión añade una entrada (ver AGENTS.md §5).

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

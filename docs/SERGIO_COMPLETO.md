# Sergio: guía completa de la app y de su código

Base revisada: `5e3117805342f9a27249508d042eef945560d12b`. Esta guía distingue código presente, integración configurada y prueba real. Un módulo o una herramienta registrados **no demuestran** que un servicio externo esté instalado, autenticado o funcionando en su equipo.

## Qué es y cómo se usa

Sergio combina una app de escritorio, una interfaz React y un servidor Python. Windows abre una ventana propia; HTTP local es el transporte interno entre esas piezas. El acceso por teléfono depende de la red, HTTPS, permisos del sistema y autenticación. No hay una app nativa completa equivalente para cada plataforma.

La marca oficial es `assets/marca/sergio.svg`: círculo azul y anillo blanco. Las variantes de instalador y accesos directos se generan desde esa fuente. Esta actualización conserva ese archivo.

| Área | Qué hay implementado | Dónde encontrarlo / código | Requisito o límite |
|---|---|---|---|
| Conversación | Mensajes, streaming, historial, adjuntos, artefactos y distintas empresas/modelos | Chat; `server/routes.py`, `engine/`, `agents/`, `frontend/src/components/Chat/` | Requiere un modelo conectado o instalado; no es una nueva familia de modelos entrenada por Sergio |
| Voz | Entrada de micrófono, transcripción, audio en vivo, idioma, atención al nombre, interrupciones y reconexión | `speech/`, `server/live_routes.py`, escritorio y clientes de voz | Depende de micrófono, altavoces, red y proveedor; no hay cero latencia ni clonación de una persona real |
| Pantalla y control del PC | Capturas, accesibilidad, clics, teclado, ventanas, programas, guías superpuestas y acciones del sistema | `tools/desktop_tools.py`, `windows/sergio_escritorio/` | Las operaciones dependen del SO; webcam y permisos reales no se prueban en un servidor sin dispositivos |
| Multitarea | Dos programas del equipo lado a lado y tareas en marcha | Botón de multitarea; `SplitButton`, backend de Windows | El soporte exacto varía por dispositivo |
| Nodes | Equipo fijo Rihno, Manchas, Hous y Tennessee; chat, actividad, rutinas, memoria, cola, pausar/cancelar | Nodes; `nodes/`, `pages/nodes/` | Son agentes persistentes, no personas ni réplicas verificadas de Dots/Muse |
| Agent Swarm | División de tareas, trabajadores paralelos, estados, resultados y fuentes | Swarm; `swarm/`, `SwarmPage.tsx` | Su capacidad depende de modelos, herramientas, permisos y presupuesto |
| Cowork | Tareas con plan, archivos, registro, indicaciones y apps conectadas | Cowork; `cowork/`, `CoworkPage.tsx` | No implica que todas las herramientas externas estén autorizadas |
| Organizador | Hoy, pendientes, correo y notas/workspace | Dentro de Cowork, Organizador; `/workspace`, `reminders/`, `workspace/` | El correo necesita conexión; preparar un borrador no equivale a enviarlo |
| Automatizaciones | Rutinas por horario, vigilancia de cambios y tareas en segundo plano, pausa y cancelación | Dentro de Cowork, Automatizaciones; `automatiza/`, `asistente/tareas.py` | Las acciones salientes siguen su política de autorización; publicación automática solo donde está expresamente configurada |
| Proyectos | Instrucciones y archivos del proyecto incorporados al contexto | Proyectos; `proyectos.py`, `server/proyectos_routes.py` | No es almacenamiento ilimitado ni garantía de recordar todo |
| Investigación | Búsqueda web, lectura de páginas, fuentes, vistas previas e investigación más extensa | Chat/Swarm; `research/`, herramientas web | Fuentes inaccesibles, límites del proveedor y autenticación pueden impedir una búsqueda |
| Archivos y documentos | Lectura, escritura, PDF, hojas de cálculo, código y artefactos | Herramientas de Chat; `tools/`, `asistente/` | Formatos y aplicaciones concretos requieren dependencias; archivos sensibles necesitan permisos |
| Programación | Ejecución, revisión, pruebas, depuración, refactorización y entorno de código externo | Chat y Extensiones; `tools/`, agente de código | Ejecutar código tiene permisos y límites; pruebas aprobadas no prueban ausencia de todos los fallos |
| Conectores | MCP remoto/stdio, OAuth donde lo soporta el servicio, CLI y configuración de herramientas | Configuración → Personalizar; `mcp/`, `server/mcp_routes.py` | Gmail, Notion, GitHub, etc. requieren su cuenta y permisos reales; un logo no certifica la conexión |
| Plugins y skills | Catálogos, instrucciones de habilidades, importación compatible y permisos | Configuración → Personalizar; `plugins/`, `skills/`, `prompt_library/` | No todos los repos de terceros se ejecutan íntegramente dentro de Sergio |
| Imagen y diseño | Generación/edición mediante proveedores, búsqueda de imágenes y programas de diseño | Chat/Extensiones; `creator/`, herramientas de imagen | Credenciales, licencias y programas instalados condicionan disponibilidad |
| Video completo | Brief, investigación, tratamiento, guion, voz, plan, tomas, música, montaje, efectos, subtítulos, exportación y créditos | Chat → Video; `video_essay/` | La generación externa cuesta cuota; el tiempo y la calidad dependen de las fuentes y del modelo |
| Inspiración | Selección de referencias, diversidad por creador y estudio del estilo | `inspiracion_video`, `video_essay/inspiracion.py` | YouTube/Instagram/TikTok no ofrecen las mismas APIs; una referencia no concede derechos sobre ella |
| Tendencias | Google Trends, Wikipedia, Reddit, YouTube, consultas, competencia y propuestas vinculadas a señales | `radar_tendencias`, `automatiza/tendencias.py`, `estudio/radar.py` | Popularidad no garantiza relevancia futura ni viralidad; datos privados de audiencia requieren analítica propia |
| Storyboard y tomas propias | Plan por plano, animática, subir cada toma y montar material del usuario | `planear_video`, `video_essay/montaje.py`, tarjetas del Chat | Un plano ausente no debe presentarse como filmado |
| Recortes y calendario | Detectar momentos de una transcripción, cortar verticales, subtitular y planificar publicaciones en XLSX | `recortes_video`, `calendario_contenido`, `estudio/` | Sin transcripción se necesita Whisper o SRT; el ranking es una heurística editorial |
| Animación y VFX | Blender, Geometry Nodes, materiales, humo/fuego, fluidos, tela, destrucción, pelo, volumetría y nueva plantilla 2D/3D | `vfx/`, `blender_*`, `motion_design` | Blender es necesario. No se afirma haber ejecutado aquí las simulaciones sin Blender |
| 3D y arquitectura | Modelos, despieces y adaptadores a programas externos | `creator/`, `professional/` | FreeCAD, Bonsai/BlenderBIM, LibreCAD, Blender y demás siguen siendo programas que se instalan por separado |
| Salud | Registro local, métricas, importación, dispositivos, medicinas, salud mental y exportación | Salud; `health/`, `server/health_routes.py` | Sin datos reales no hay medición; no es diagnóstico ni sustitución de un profesional |
| Identidad y seguridad | Cuentas, roles, sesión, Visage para aprobaciones, capacidades, bóveda, cifrado y respaldos | Configuración/Perfil; `accounts/`, `security/`, `faces/`, `backup/` | Una webcam no equivale al hardware de Face ID; no hay seguridad absoluta |
| Memoria y cerebro | Contexto, recuerdos, aprendizaje de rutas y cableado de mosca como mecanismo experimental de selección | Cerebro; `connectome/`, `memory/` | No reentrena el modelo de lenguaje ni demuestra inteligencia humana/AGI |
| Consumo, planes y pagos | Cuotas, modelos, costes, planes, cobros y subclaves según configuración | Configuración → Cuenta; `quota.py`, `tiers.py`, `pagos/` | Requiere procesadores y configuración; no se hicieron cobros reales en esta revisión |
| Finanzas y oportunidades | Adaptadores de pronóstico, clientes/empleos y trading con límites | `professional/kronos.py`, `automatiza/` | Predicciones no son garantías de rentabilidad; no se opera dinero real en esta revisión |
| Ayuda y mantenimiento | Tour animado, guías, actualización, servicio y diagnósticos | Ayuda/Configuración; `scripts/`, `estabilidad.py` | Windows real e instaladores requieren validación en ese SO |

## Cómo funciona una petición

1. La interfaz envía el mensaje y sus archivos al servidor autenticado.
2. Cuenta, permisos, proyecto y contexto determinan qué datos y herramientas pueden usarse.
3. El motor selecciona el modelo configurado; memoria, skills y contexto aportan información.
4. El agente propone llamadas de herramientas. Los permisos y aprobaciones controlan sus efectos.
5. El resultado vuelve en streaming o como artefacto/archivo; las tareas largas publican estado.
6. Una integración no conectada debe explicar el bloqueo. No debería anunciar que reservó, publicó o midió algo solo porque preparó un plan.

## Flujo completo para un creador

- **Explorar:** radar, tendencias, inspiración y competencia con fuente identificable.
- **Preparar:** idea, título, miniatura, gancho y calendario; no inventar la mejor hora sin estadísticas.
- **Escribir:** tratamiento, partes del guion, revisión del ritmo y protección de nombres/cifras.
- **Planificar:** storyboard, encuadre, duración y tomas que hacen falta.
- **Producir:** grabaciones propias, material con sus condiciones de uso, generación por proveedor, 2D/3D o programas externos.
- **Editar:** selección de clips, encuadre, transiciones, motion graphics, efectos y color.
- **Sonido:** voz, música, pausas, efectos y cadena de mezcla. La escucha humana sigue siendo necesaria.
- **Entregar:** subtítulos, duración y relación de aspecto verificadas; archivo y créditos.
- **Distribuir:** publicación únicamente con una conexión y autorización/política explícitas. Preparado no significa publicado.

Ejemplos para pedir en Chat (requieren las conexiones indicadas): «Busca referencias para un video sobre energía solar en Ecuador»; «Planea un video con mis tomas»; «Encuentra cinco momentos de mi podcast y corta el segundo»; «Haz una animación 3D editable con el título de mi producto»; «Organiza tres publicaciones por semana en un calendario». Las pruebas de esta sesión verifican los contratos de código y exportaciones locales descritos en la bitácora, no esas conversaciones completas con cuentas personales.

## Cambios de esta revisión

- Corrige la petición de tendencias con OAuth: antes se pasaba `headers` dos veces.
- Ranking de señales sin mutar la entrada: deduplicación, popularidad relativa, antigüedad conocida, nicho y coincidencia temática entre fuentes.
- YouTube conserva URL y fecha pública; las ideas exigen el nombre exacto de una señal. El peso no es una probabilidad de éxito.
- Las reescrituras de guion rechazan cambios de cifras/nombres detectados. Esto no demuestra que una afirmación sea verdadera: todavía requiere comprobar la fuente.
- Recortes rechazan tiempos inválidos, respetan duración, limpian etiquetas SRT, no sobrescriben exportaciones previas y revisan vídeo, encuadre y duración. Si falla incrustar subtítulos se informa, no se entrega silenciosamente sin ellos.
- Sin OpenCV se permite recorte central: no se anuncia seguimiento de personas.
- `motion_design`: títulos cinéticos 2D y escena de producto 3D con fotogramas clave; guarda .blend y vistas previas verificables cuando Blender está disponible.
- Marca azul coherente con el SVG oficial; texto de acento y foco legibles. Nodes en reposo quietos y estados activos animados, respetando reducción de movimiento.
- Demo reproducible `scripts/demo_creadores.py`: 6 segundos de diseño procedural original; no muestra una tarea real ni un render de Blender.

## Arquitectura: dónde está cada pieza

| Carpeta | Responsabilidad |
|---|---|
| `frontend/` | React, TypeScript, navegación, estado, componentes, estilos y pruebas de interfaz |
| `src/openjarvis/server/` | FastAPI, autenticación, rutas, streaming, WebSockets y archivos de la app |
| `src/openjarvis/core/` | Tipos, registros y configuración compartida; algunos módulos de investigación separados |
| `src/openjarvis/engine/` | Adaptadores de inferencia, streaming, fallback y salud de modelos |
| `src/openjarvis/agents/` | Bucles del agente y construcción de su contexto/herramientas |
| `src/openjarvis/tools/` | Contratos y ejecución de herramientas registradas |
| `src/openjarvis/nodes/`, `cowork/`, `swarm/` | Tres formas diferentes de organizar el trabajo |
| `src/openjarvis/video_essay/`, `estudio/`, `vfx/` | Producción audiovisual, utilidades para creadores y scripts Blender |
| `src/openjarvis/mcp/`, `plugins/`, `skills/` | Conexiones, paquetes e instrucciones reutilizables |
| `src/openjarvis/accounts/`, `security/`, `pagos/` | Identidad, límites de acceso, cifrado y facturación |
| `src/openjarvis/health/`, `memory/`, `connectome/` | Datos locales, recuerdos y selección/aprendizaje de contexto |
| `windows/sergio_escritorio/` | Integración con Windows, notch, voz y control del equipo |
| `extensions/` | Proyectos externos y sus adaptadores; no todos están activos o instalados |
| `rust/` | Aceleración nativa opcional y puentes con Python |
| `scripts/`, `installer/`, `deploy/` | Actualización, instalación, servicio y despliegue |
| `tests/` | Pruebas de módulos e integración; algunas requieren dependencias o hardware |

## Límites detectados que no quedan certificados

- Los módulos Nexus de `core/agi_engine.py` y `core/agi_reasoning.py` todavía contienen rutas con resultados predeterminados (`success=True`, reserva garantizada y biometría fija). **No se deben usar como prueba de ejecución real ni anunciar como AGI operativa.** Esta revisión de creadores no migra esas rutas.
- No están certificados control de vehículos, todas las marcas de wearables ni todos los servicios externos. Un adaptador o nombre en un catálogo no es una conexión probada.
- No se garantiza eludir barreras de sitios, conseguir descuentos ni reservas agotadas.
- No hay equivalencia demostrada con Face ID, ChatGPT, Muse o Kimi, ni retraso cero ni interpretación de pantalla con FPS fraccionarios exactos.
- No se probó aquí Windows real, cámara, micrófono, GPU/Blender ni publicación con las cuentas del dueño.
- El repositorio contiene páginas y módulos heredados. Una página de código no necesariamente es una sección visible: Creator está redirigido al chat, Organizador/Automatizaciones viven dentro de Cowork y Uso está en Configuración → Cuenta.

## Inventario de herramientas declaradas

La tabla siguiente se obtiene del AST de todos los módulos Python recuperados de `src/openjarvis/`. Enumera identificadores literales registrados con `ToolRegistry.register`; no equivale a afirmar que cada dependencia esté disponible. Las herramientas de MCP se descubren al conectar el servidor y no pueden enumerarse sin esa conexión. Las rutas de clase sirven para revisar su implementación exacta.

| Identificador | Clase | Código |
|---|---|---|
| `agent_kill` | `AgentKillTool` | `src/openjarvis/tools/agent_tools.py` |
| `agent_list` | `AgentListTool` | `src/openjarvis/tools/agent_tools.py` |
| `agent_send` | `AgentSendTool` | `src/openjarvis/tools/agent_tools.py` |
| `agent_spawn` | `AgentSpawnTool` | `src/openjarvis/tools/agent_tools.py` |
| `anatomy_figure` | `AnatomyFigureTool` | `src/openjarvis/tools/creator_tools.py` |
| `apply_patch` | `ApplyPatchTool` | `src/openjarvis/tools/apply_patch.py` |
| `artefacto` | `ArtifactTool` | `src/openjarvis/tools/artefacto.py` |
| `audio_transcribe` | `AudioTranscribeTool` | `src/openjarvis/tools/audio_tool.py` |
| `automatizar` | `AutomatizarTool` | `src/openjarvis/tools/automatizar_tool.py` |
| `blender_create` | `BlenderCreateTool` | `src/openjarvis/tools/desktop_tools.py` |
| `browser_axtree` | `BrowserAXTreeTool` | `src/openjarvis/tools/browser_axtree.py` |
| `browser_click` | `BrowserClickTool` | `src/openjarvis/tools/browser.py` |
| `browser_extract` | `BrowserExtractTool` | `src/openjarvis/tools/browser.py` |
| `browser_navigate` | `BrowserNavigateTool` | `src/openjarvis/tools/browser.py` |
| `browser_screenshot` | `BrowserScreenshotTool` | `src/openjarvis/tools/browser.py` |
| `browser_type` | `BrowserTypeTool` | `src/openjarvis/tools/browser.py` |
| `buscar_fotos` | `BuscarFotosTool` | `src/openjarvis/tools/asistente_tools.py` |
| `calculator` | `CalculatorTool` | `src/openjarvis/tools/calculator.py` |
| `calendar_search` | `CalendarSearchTool` | `src/openjarvis/tools/apple_calendar.py` |
| `calendar_upcoming` | `CalendarUpcomingTool` | `src/openjarvis/tools/apple_calendar.py` |
| `calendario_contenido` | `ContentCalendarTool` | `src/openjarvis/tools/estudio_tools.py` |
| `camera_look` | `CameraLookTool` | `src/openjarvis/tools/desktop_tools.py` |
| `cancel_scheduled_task` | `CancelScheduledTaskTool` | `src/openjarvis/scheduler/tools.py` |
| `channel_list` | `ChannelListTool` | `src/openjarvis/tools/channel_tools.py` |
| `channel_send` | `ChannelSendTool` | `src/openjarvis/tools/channel_tools.py` |
| `channel_status` | `ChannelStatusTool` | `src/openjarvis/tools/channel_tools.py` |
| `check_permission` | `CheckPermissionTool` | `src/openjarvis/tools/proactive_tools.py` |
| `cine_ia` | `CinematicAIVideoTool` | `src/openjarvis/tools/creator_tools.py` |
| `clips_cine` | `FilmClipsTool` | `src/openjarvis/tools/estudio_tools.py` |
| `code_interpreter` | `CodeInterpreterTool` | `src/openjarvis/tools/code_interpreter.py` |
| `code_interpreter_docker` | `DockerCodeInterpreterTool` | `src/openjarvis/tools/code_interpreter_docker.py` |
| `code_review` | `ReviewTool` | `src/openjarvis/tools/coding_tools.py` |
| `conserje` | `ConciergeTool` | `src/openjarvis/tools/conserje_tool.py` |
| `criterio_estetico` | `CriterioEsteticoTool` | `src/openjarvis/tools/estetica_tool.py` |
| `db_query` | `DatabaseQueryTool` | `src/openjarvis/tools/db_query.py` |
| `debug_trace` | `DebugTool` | `src/openjarvis/tools/coding_tools.py` |
| `deep_think` | `DeepThinkTool` | `src/openjarvis/tools/deep_think_tool.py` |
| `desktop_action` | `DesktopActionTool` | `src/openjarvis/tools/desktop_tools.py` |
| `digest_collect` | `DigestCollectTool` | `src/openjarvis/tools/digest_collect.py` |
| `doc_drift` | `DocsTool` | `src/openjarvis/tools/coding_tools.py` |
| `docker_shell_exec` | `DockerShellExecTool` | `src/openjarvis/tools/docker_shell_exec.py` |
| `en_segundo_plano` | `SegundoPlanoTool` | `src/openjarvis/tools/asistente_tools.py` |
| `escuela_video` | `VideoSchoolTool` | `src/openjarvis/tools/estudio_tools.py` |
| `execute_pending_actions` | `ExecutePendingActionsTool` | `src/openjarvis/tools/proactive_tools.py` |
| `face_approval` | `FaceApprovalTool` | `src/openjarvis/tools/desktop_tools.py` |
| `face_enroll` | `FaceEnrollTool` | `src/openjarvis/tools/desktop_tools.py` |
| `face_identify` | `FaceIdentifyTool` | `src/openjarvis/tools/face_tools.py` |
| `face_list` | `FaceListTool` | `src/openjarvis/tools/face_tools.py` |
| `file_read` | `FileReadTool` | `src/openjarvis/tools/file_read.py` |
| `file_write` | `FileWriteTool` | `src/openjarvis/tools/file_write.py` |
| `files_organize` | `FilesOrganizeTool` | `src/openjarvis/tools/desktop_tools.py` |
| `flights_overhead` | `FlightsOverheadTool` | `src/openjarvis/tools/live_world.py` |
| `get_pending_actions` | `GetPendingActionsTool` | `src/openjarvis/tools/proactive_tools.py` |
| `get_weather` | `WeatherTool` | `src/openjarvis/tools/weather.py` |
| `git_commit` | `GitCommitTool` | `src/openjarvis/tools/git_tool.py` |
| `git_diff` | `GitDiffTool` | `src/openjarvis/tools/git_tool.py` |
| `git_log` | `GitLogTool` | `src/openjarvis/tools/git_tool.py` |
| `git_status` | `GitStatusTool` | `src/openjarvis/tools/git_tool.py` |
| `globe_view` | `GlobeViewTool` | `src/openjarvis/tools/live_world.py` |
| `hoja_calculo` | `HojaCalculoTool` | `src/openjarvis/tools/asistente_tools.py` |
| `http_request` | `HttpRequestTool` | `src/openjarvis/tools/http_request.py` |
| `image_generate` | `ImageGenerateTool` | `src/openjarvis/tools/image_tool.py` |
| `imagenes_web` | `WebImagesTool` | `src/openjarvis/tools/imagenes_web.py` |
| `inspiracion_video` | `InspiracionTool` | `src/openjarvis/tools/inspiracion_tool.py` |
| `investigacion_profunda` | `DeepResearchWebTool` | `src/openjarvis/tools/deep_research_web.py` |
| `juego_unreal` | `UnrealGameTool` | `src/openjarvis/tools/creator_tools.py` |
| `kg_add_entity` | `KGAddEntityTool` | `src/openjarvis/tools/knowledge_tools.py` |
| `kg_add_relation` | `KGAddRelationTool` | `src/openjarvis/tools/knowledge_tools.py` |
| `kg_neighbors` | `KGNeighborsTool` | `src/openjarvis/tools/knowledge_tools.py` |
| `kg_query` | `KGQueryTool` | `src/openjarvis/tools/knowledge_tools.py` |
| `knowledge_search` | `KnowledgeSearchTool` | `src/openjarvis/tools/knowledge_search.py` |
| `knowledge_sql` | `KnowledgeSQLTool` | `src/openjarvis/tools/knowledge_sql.py` |
| `kronos_forecast` | `KronosTool` | `src/openjarvis/tools/professional.py` |
| `list_scheduled_tasks` | `ListScheduledTasksTool` | `src/openjarvis/scheduler/tools.py` |
| `live_earthquakes` | `LiveEarthquakesTool` | `src/openjarvis/tools/live_world.py` |
| `live_flights` | `LiveFlightsTool` | `src/openjarvis/tools/live_world.py` |
| `llm` | `LLMTool` | `src/openjarvis/tools/llm_tool.py` |
| `long_context_qa` | `LongContextTool` | `src/openjarvis/tools/coding_tools.py` |
| `mejorarme` | `AutomejoraTool` | `src/openjarvis/tools/automejora_tool.py` |
| `memory_index` | `MemoryIndexTool` | `src/openjarvis/tools/storage_tools.py` |
| `memory_manage` | `MemoryManageTool` | `src/openjarvis/tools/memory_manage.py` |
| `memory_retrieve` | `MemoryRetrieveTool` | `src/openjarvis/tools/storage_tools.py` |
| `memory_search` | `MemorySearchTool` | `src/openjarvis/tools/storage_tools.py` |
| `memory_store` | `MemoryStoreTool` | `src/openjarvis/tools/storage_tools.py` |
| `miniaturas` | `ThumbnailsTool` | `src/openjarvis/tools/estudio_tools.py` |
| `modelo_por_piezas` | `TakeApartModelTool` | `src/openjarvis/tools/creator_tools.py` |
| `motion_design` | `MotionDesignTool` | `src/openjarvis/tools/estudio_tools.py` |
| `movimiento_personaje` | `CharacterMotionTool` | `src/openjarvis/tools/creator_tools.py` |
| `opendesign` | `OpenDesignTool` | `src/openjarvis/tools/professional.py` |
| `optimize_code` | `OptimizeTool` | `src/openjarvis/tools/coding_tools.py` |
| `pause_scheduled_task` | `PauseScheduledTaskTool` | `src/openjarvis/scheduler/tools.py` |
| `pc_checkup` | `PcCheckupTool` | `src/openjarvis/tools/daily_tools.py` |
| `pdf_extract` | `PDFExtractTool` | `src/openjarvis/tools/pdf_tool.py` |
| `phone_call` | `PhoneCallTool` | `src/openjarvis/tools/phone_tools.py` |
| `phone_call_status` | `PhoneCallStatusTool` | `src/openjarvis/tools/phone_tools.py` |
| `photos_duplicates` | `PhotosDuplicatesTool` | `src/openjarvis/tools/daily_tools.py` |
| `planear_video` | `PlanearVideoTool` | `src/openjarvis/tools/planear_tool.py` |
| `polyglot` | `PolyglotTool` | `src/openjarvis/tools/coding_tools.py` |
| `professional_apps` | `ProfessionalAppsTool` | `src/openjarvis/tools/professional.py` |
| `python_run` | `PythonRunTool` | `src/openjarvis/tools/desktop_tools.py` |
| `queue_action` | `QueueActionTool` | `src/openjarvis/tools/proactive_tools.py` |
| `radar_tendencias` | `TrendRadarTool` | `src/openjarvis/tools/estudio_tools.py` |
| `record_decision` | `RecordDecisionTool` | `src/openjarvis/tools/proactive_tools.py` |
| `recortes_video` | `ClipFinderTool` | `src/openjarvis/tools/estudio_tools.py` |
| `reminders` | `RemindersTool` | `src/openjarvis/tools/reminders_tool.py` |
| `repl` | `ReplTool` | `src/openjarvis/tools/repl.py` |
| `resume_scheduled_task` | `ResumeScheduledTaskTool` | `src/openjarvis/scheduler/tools.py` |
| `retrieval` | `RetrievalTool` | `src/openjarvis/tools/retrieval.py` |
| `safe_refactor` | `RefactorTool` | `src/openjarvis/tools/coding_tools.py` |
| `scan_chunks` | `ScanChunksTool` | `src/openjarvis/tools/scan_chunks.py` |
| `scene_reason` | `SceneReasonTool` | `src/openjarvis/tools/scene_reason.py` |
| `schedule_task` | `ScheduleTaskTool` | `src/openjarvis/scheduler/tools.py` |
| `screen_read` | `ScreenReadTool` | `src/openjarvis/tools/desktop_tools.py` |
| `sergio_app` | `SergioAppControlTool` | `src/openjarvis/tools/app_control.py` |
| `shell_exec` | `ShellExecTool` | `src/openjarvis/tools/shell_exec.py` |
| `skill_guide` | `SkillGuideTool` | `src/openjarvis/tools/skill_guide_tool.py` |
| `skill_manage` | `SkillManageTool` | `src/openjarvis/tools/skill_manage.py` |
| `tdd_codegen` | `TDDTool` | `src/openjarvis/tools/coding_tools.py` |
| `terminal_run` | `TerminalRunTool` | `src/openjarvis/tools/desktop_tools.py` |
| `text_to_speech` | `TextToSpeechTool` | `src/openjarvis/tools/text_to_speech.py` |
| `think` | `ThinkTool` | `src/openjarvis/tools/think.py` |
| `titulos_video` | `TitlesTool` | `src/openjarvis/tools/estudio_tools.py` |
| `upcoming_launches` | `UpcomingLaunchesTool` | `src/openjarvis/tools/live_world.py` |
| `user_profile_manage` | `UserProfileManageTool` | `src/openjarvis/tools/user_profile_manage.py` |
| `verified_math` | `VerifiedMathTool` | `src/openjarvis/tools/verified_math.py` |
| `video_create` | `VideoCreateTool` | `src/openjarvis/tools/video_create.py` |
| `video_edit` | `VideoEditTool` | `src/openjarvis/tools/desktop_tools.py` |
| `video_essay` | `VideoEssayTool` | `src/openjarvis/tools/video_essay_tool.py` |
| `video_pro` | `VideoProTool` | `src/openjarvis/tools/desktop_tools.py` |
| `web_search` | `WebSearchTool` | `src/openjarvis/tools/web_search.py` |
| `whatsapp_send` | `WhatsAppSendTool` | `src/openjarvis/tools/phone_tools.py` |
| `workspace` | `WorkspaceTool` | `src/openjarvis/tools/workspace_tool.py` |

## Árbol de paquetes Python

Lista completa de carpetas de primer nivel bajo `src/openjarvis/` presentes en la base inspeccionada; algunas son bibliotecas internas y no pantallas.

- `a2a/`: 5 archivos Python.
- `accounts/`: 12 archivos Python.
- `agents/`: 62 archivos Python.
- `analytics/`: 7 archivos Python.
- `asistente/`: 5 archivos Python.
- `automatiza/`: 8 archivos Python.
- `backup/`: 5 archivos Python.
- `bench/`: 6 archivos Python.
- `channels/`: 34 archivos Python.
- `cli/`: 87 archivos Python.
- `coach/`: 4 archivos Python.
- `connectome/`: 14 archivos Python.
- `connectors/`: 42 archivos Python.
- `conserje/`: 9 archivos Python.
- `core/`: 19 archivos Python.
- `cowork/`: 6 archivos Python.
- `creator/`: 16 archivos Python.
- `daemon/`: 4 archivos Python.
- `engine/`: 25 archivos Python.
- `estetica/`: 4 archivos Python.
- `estudio/`: 7 archivos Python.
- `evals/`: 152 archivos Python.
- `evolution/`: 6 archivos Python.
- `faces/`: 7 archivos Python.
- `hardware/`: 1 archivos Python.
- `health/`: 9 archivos Python.
- `i18n/`: 1 archivos Python.
- `intelligence/`: 12 archivos Python.
- `learning/`: 84 archivos Python.
- `mcp/`: 13 archivos Python.
- `memory/`: 4 archivos Python.
- `mining/`: 16 archivos Python.
- `nodes/`: 13 archivos Python.
- `operators/`: 4 archivos Python.
- `pagos/`: 7 archivos Python.
- `phone/`: 6 archivos Python.
- `plugins/`: 9 archivos Python.
- `professional/`: 6 archivos Python.
- `prompt/`: 2 archivos Python.
- `prompt_library/`: 6 archivos Python.
- `recipes/`: 3 archivos Python.
- `reminders/`: 2 archivos Python.
- `research/`: 3 archivos Python.
- `sandbox/`: 4 archivos Python.
- `scheduler/`: 4 archivos Python.
- `security/`: 32 archivos Python.
- `server/`: 78 archivos Python.
- `sessions/`: 3 archivos Python.
- `skills/`: 20 archivos Python.
- `speech/`: 23 archivos Python.
- `swarm/`: 3 archivos Python.
- `system/`: 7 archivos Python.
- `telemetry/`: 20 archivos Python.
- `templates/`: 2 archivos Python.
- `tools/`: 110 archivos Python.
- `traces/`: 4 archivos Python.
- `unified/`: 8 archivos Python.
- `vfx/`: 11 archivos Python.
- `video_essay/`: 34 archivos Python.
- `workflow/`: 6 archivos Python.
- `workspace/`: 5 archivos Python.

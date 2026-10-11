# Auditoría de Sergio y ejemplos comprobados

Fecha: 11 de octubre de 2026. Código de partida: `94e566083af0e6eb0ea6fba36934a3ba2d72ba6e`, rama `codex/professional-reliability-audit`.

## Resultado

Sergio tiene funciones locales útiles y comprobadas, pero no cumple todavía todas las peticiones anteriores. No integra todos los motores externos, no reproduce íntegramente Kimi K3/PARL, Muse, DOTS o ChatGPT Work y no contiene una voz idéntica a Brad Pitt. Tampoco hay mediciones que permitan afirmar superioridad frente a todos ellos, ausencia de lag o eliminación de alucinaciones.

Esta revisión inventaría la versión completa y aplica controles automatizados amplios, con inspección manual de las fronteras más importantes. No significa que cada archivo, combinación de dispositivos, modelo y servicio haya sido probado exhaustivamente.

## Identidad y alcance

- Árbol publicado: 5.711 entradas, sin truncamiento.
- Comparación por SHA de blob de 5.100 archivos publicados, excluyendo los assets compilados de `src/openjarvis/server/static/`: 5.087 coincidencias exactas.
- Las 13 diferencias son ocho documentos de marketing, tres fuentes y dos archivos de pesos YOLO. El código principal y sus pruebas coinciden con la versión publicada antes de los cambios de esta revisión. No se cargaron esos pesos ni se certifica la tipografía nativa.
- Análisis de sintaxis de los 1.844 archivos Python publicados: sin errores.
- Sintaxis Bash de 16 scripts: sin errores. PowerShell, Rust, Ruby/OpenClacky, GPU y ejecución nativa Windows no se compilan/certifican en este entorno.
- Revisión manual enfocada en Nodes, MCP/CLI, ejecución y aprobación, scheduler, workflows, Swarm, voz, rutas y acceso a la interfaz, importación de skills, autenticación, procesos y actualización.

## Defectos corregidos en esta revisión

1. **Nodes no tenía ruta web.** `App.tsx` importaba `NodesPage`, pero no registraba `/nodes`. El menú y el botón Windows apuntaban a una ruta sin contenido. Se añadió la ruta; el menú ya existía. Una regresión renderiza la aplicación real en `/nodes` y verifica el contenido de Nodes y una sola entrada en el menú. La compilación incorpora su chunk.
2. **Cuatro módulos nuevos omitían sus exports públicos.** Se declara `__all__` en `nodes/catalog.py`, `nodes/sessions.py`, `skills/audit.py` y `agents/workflows.py`, respetando el contrato comprobado por la suite del repositorio.
3. **Una prueba de Blender aún consultaba GitHub.** `test_old_blender_is_told_instead_of_breaking` simulaba descarga/Blender, pero consultaba la última release de SculptMate. Ahora simula también la URL de release; prueba compatibilidad y activación sin servicio externo.
4. **Personalidad por turnos y pruebas antiguas de voz.** Se recuperó el tratamiento «señor» que ya mantenía Gemini Live, con humor ocasional subordinado a resolver la tarea. Se actualizaron dos pruebas obsoletas: conservar una orden legítima de Google/YouTube y exigir opt-in para cambiar a una voz de respaldo. La prueba comprueba primero el rechazo del respaldo automático y después su aceptación explícita; no se desactiva ese límite para obtener un resultado verde.

## Estado real de los repos solicitados

| Proyecto | Presente en Sergio | Lo que no debe darse por hecho |
|---|---|---|
| Anil-matcha/open-dots | Patrón propio de pausa tras tres fallos recurrentes; Nodes conserva objetivos y memoria | No se instala ni ejecuta su backend. No están todas sus funciones |
| openclaw/openclaw | Preset opcional de CLI con revisión de argumentos y límites | Hay que instalarlo y configurar sus permisos. Sus acciones internas no se auditan individualmente desde Sergio |
| kyegomez/swarms | Workflows propios secuenciales y de dos expertos paralelos con síntesis; validación de dependencias | No se importa ni instala el framework. No están todas sus arquitecturas |
| browser-use/browser-use | Preset opcional MCP, sesiones persistentes acotadas y aprobación por acción | Requiere ejecutable, navegador y configuración. Las pruebas de esta revisión usan un servidor MCP de prueba; no navegación real con Browser-use |
| The-Swarm-Corporation | Ideas de SkillScanner y GraphWorkflow-Paper, implementadas localmente | No se incorpora toda la organización. La referencia anterior a su repo `swarms` devolvió 404; GraphWorkflow-Paper enlaza kyegomez/swarms |
| marcoazeem/duo-open | Adaptación Qt de apertura, inclinación y blur; atribución y licencia MIT incluida | No es el motor Android, su shader completo ni una animación idéntica de iPhone |
| Notch líquido proporcionado | SVG del indicador de objetivos y menisco nativo; textos fuera del filtro | No reproduce el compositor de Apple ni cuenta con medición de FPS en el equipo del usuario |

En este entorno de auditoría, los ejecutables `browser-use` y `openclaw` no están instalados. Eso no indica su estado en el PC del usuario. El catálogo comprueba presencia del ejecutable, no salud de toda la integración.

Referencias revisadas: [open-dots](https://github.com/Anil-matcha/open-dots), [OpenClaw](https://github.com/openclaw/openclaw), [Swarms](https://github.com/kyegomez/swarms), [Browser-use](https://github.com/browser-use/browser-use), [organización Swarm](https://github.com/orgs/The-Swarm-Corporation/repositories), [duo-open](https://github.com/marcoazeem/duo-open). Los pins y decisiones anteriores siguen documentados en `integraciones-opensource-2026-10-11.md` y `swarms-duo-notch-auditoria-2026-10-11.md`; no se sustituyeron por HEAD nuevos automáticamente.

## Qué hace Sergio

| Área | Capacidad actual | Condición o límite |
|---|---|---|
| Chat y conocimiento | Conversación con modelos configurados, herramientas, búsqueda e ingestión de documentos/conectores | La calidad de respuestas depende del modelo y la calidad de fuentes; cuentas externas requieren conexión |
| Desarrollo y archivos | Python/terminal con aprobación, resultados y códigos de salida; previsualizar organización y deshacer movimientos | Ejecutar en el host tiene los permisos de la cuenta. Contenedor de proyecto es opt-in |
| Cowork | Objetivos, plan, pasos, revisión, aprobación/rechazo, cancelación y trazas persistentes | Ejecutor propio; no todos los proyectos, nube y servicios de ChatGPT Work |
| Agent Swarm | Dependencias, trabajo en paralelo, expansión y seguimiento/cancelación de tareas | Default ocho trabajadores, fanout máximo 300, hasta 4.000 pasos y 4.000 turnos de agente; no equivale a 4.000 llamadas de herramienta ni 300 modelos simultáneos |
| Nodes | Personajes propios Lumen/Bruma/Nival, color y pelaje, rol, objetivos, memoria editable y registro | Máximo 32 personajes; memoria/objetivos/conexiones acotados. Olvidar memoria no borra automáticamente trazas antiguas |
| Rutinas de Nodes | Objetivos recurrentes de lectura, pausa/reanudación y pausa tras tres fallos | Requiere servidor y equipo encendidos, modelo y scheduler configurados. No es un servicio cloud siempre activo |
| API, MCP y CLI | Claves propias sujetas al plan Dev, conexiones revisadas, revocación y cierre de sesiones | Dos sesiones MCP persistentes, cierre por inactividad de 120 s; ticket de un uso y acción concreta. CLI 30 s y salida acotada |
| Voz | Transcripción WAV/VAD, idioma y contexto; voz seleccionada, streaming y errores visibles | Voces genéricas o ID autorizado de proveedor. ElevenLabs/Edge usan turnos; Gemini Live utiliza voces Gemini. Micrófono/acento real sin medir |
| Escritorio | Control de aplicaciones, pantalla y periféricos, con fronteras de aprobación | La mayor parte de pruebas simula Windows y dispositivos. No certifica clics en todas las aplicaciones reales |
| Multimedia y compañía | Código de reuniones, visión, manos, Blender/vídeo, perfil, estudio y bienestar | Hardware, modelos, Blender y dependencias específicos; no se prometen diagnósticos ni resultados creativos perfectos |
| Extensiones | Globo 3D y OpenClacky incluidos, supervisor y puente de modelos | Globo depende de las fuentes configuradas. OpenClacky necesita Ruby y gems; no se ejecutó su suite aquí |
| Skills | Catálogo y ejecución; análisis previo a importación, límites y copia temporal | Heurísticas estáticas, no certificación de seguridad ni análisis exhaustivo de binarios/scripts |

## Ejemplos comprobados y forma correcta de presentarlos

1. **Informe de un proyecto.** Se ejecutó Python mediante `files.run_python` en una carpeta temporal. Creó `latencias.csv` con 120, 80 y 100 ms y `informe.md` con **100 ms de media**. Se comprobó el contenido real. La carpeta contiene también el script que Sergio conserva. Se organizaron los tres archivos y deshacer restauró sus bytes originales. Comprueba ejecución y gestión de archivos; el código del ejemplo fue escrito deliberadamente, no generado por un modelo ni dictado por micrófono.
2. **Node revisor.** Se guardó un personaje con rol y pelaje, y memoria «Usamos Python 3.13». Tras cerrar y reabrir SQLite, ambos persistieron; borrar la memoria dejó la lista vacía. Comprueba almacenamiento, no un aprendizaje espontáneo del personaje.
3. **Build diario de un desarrollador.** La prueba existente ejecuta veinte procesos Python reales, conserva directorio y resultado de cada turno y detecta los exit 42 como fallos. Verifica que una variable privada de prueba no aparezca en su salida. La aprobación se simula mediante callback.
4. **Comando aprobado.** Nodes ejecuta un proceso Python real que imprime `REAL_OUTPUT`. Sin ticket se rechaza; volver a usarlo o cambiar argumentos se rechaza. Los tests prueban carrera de aprobación y revocación. No prueba todos los comandos externos posibles.
5. **MCP con estado.** Un servidor stdio de prueba real conserva estado entre acciones revisadas; tickets antiguos y sesiones revocadas quedan inválidos. No equivale a probar compras o formularios en un navegador real.
6. **Trabajo repartido.** Un plan con 300 pasos finaliza con hasta cuatro trabajadores en la prueba configurada. El plan y la respuesta del modelo son dobles; prueba planificación, límites y propagación, no 300 investigaciones correctas.
7. **Cowork revisable.** Tests verifican aprobación/rechazo, dependencias bloqueadas, cancelación durante espera, límites y persistencia tras reinicio. Los modelos están simulados; la ejecución de una tarea arbitraria debe comprobarse por sus resultados y archivos.

## Pruebas de esta revisión

| Comprobación | Resultado |
|---|---|
| Suite local de core/tools/agents/skills/MCP/memory/scheduler/backup/CLI/unified/install | 4.567 aprobadas, 43 omitidas, 14 fallos y un error iniciales |
| Causa de esos fallos | Cuatro exports ausentes; diez fallos por `croniter` ausente; error de colección por `respx` ausente en el entorno de auditoría |
| Regresiones tras corregir exports e instalar croniter/respx en sus versiones del lock | 1.027 aprobadas; incluyen todos esos módulos fallidos, HTTP, scheduler, Nodes y análisis de skills |
| Nodes/Cowork/seguridad/voz/archivos/Swarm/notch, suite aislada | 717 aprobadas, dos omitidas |
| Complementos de Blender tras aislar consulta de release | 35 aprobadas |
| Escritorio sin arranque completo en subprocess, tras aislar Blender | 683 aprobadas, diez omitidas y tres fallos iniciales; dos tests obsoletos y una regresión de personalidad identificados |
| Escritorio final, sin `test_app_starts.py` | 686 aprobadas, diez omitidas; los tres fallos anteriores resueltos |
| Frontend final | 124 aprobadas, TypeScript y build de producción correctos; incluye apertura real de la ruta Nodes por SSR |
| Globo, tests ordinarios | 5.372 aprobadas, una omitida |
| Globo, probe de memoria ejecutado | Una aprobada |
| Límites de imports del Globo | 834 módulos y 66 entradas portables, comprobación correcta |
| Ruff src/tests final | Correcto |
| Ruff Windows | 181 líneas largas y cinco imports por ordenar; pendientes de estilo |
| Bandit src/Windows | 944 archivos, 1.251 alertas: 1.142 bajas, 109 medias, ninguna alta según sus reglas |

Las suites se solapan: no se suman para afirmar un total de pruebas únicas. El resto de checks de asignaciones del Globo y los resultados finales de escritorio deben leerse con sus límites, no reemplazarse por cifras de informes históricos. Esta revisión utilizó Python 3.12.14, Node 24.19.0 y PySide6 6.11.2; no es el entorno de instalación Windows del usuario ni una ejecución completa de todos los extras del lock.

La batería general que incluía conectores fue bloqueada por la revisión automática de permisos por una conexión inesperada a Google, sin verificación de los datos de salida. Una batería completa de escritorio también fue bloqueada por una conexión inesperada a GitHub; se identificó y aisló la prueba de Blender descrita arriba. No se da ninguna de esas ejecuciones interrumpidas por superada. No se usaron cuentas reales para comprobar resultados comerciales.

## Pendientes y riesgos que la auditoría no elimina

- Paridad completa de productos cerrados y motores externos: pendiente. K3/PARL y todos los servicios Muse/DOTS no se reproducen con un coordinador local.
- Voz idéntica a Brad Pitt: no implementada ni comprobada; los presets existentes son genéricos.
- Validación en Windows real, micrófono, ruido/acento, GPU, instalaciones y modelos/conectores facturados: pendiente.
- Las alertas Bandit son pistas, no vulnerabilidades confirmadas ni garantía por ausencia de alertas altas. Se inspeccionaron ejemplos de SQL parametrizado y eval de tipos/aritmética, pero no se adjudicaron individualmente las 1.251 alertas.
- El REPL local ejecuta en un hilo: su timeout devuelve un error, pero no termina por fuerza el hilo. El perfil contenedor lo desactiva; no debe describirse como aislamiento global.
- CLI/MCP con aprobación no son VM: programas externos pueden leer archivos del usuario y delegar acciones internamente; un Gateway externo puede continuar tras el timeout de su CLI.
- La CSP conserva `unsafe-inline`/`unsafe-eval`; mejorarla requiere validar componentes y proveedores. No se declara la interfaz blindada.
- No hay medición de FPS/consumo ni benchmark de precisión diario comparable. Limitar colas, contextos, polling y salidas reduce trabajo innecesario, pero no garantiza cero lag.
- Las respuestas generadas siguen necesitando evidencia. Marcar «pendiente de revisión» o bajar temperatura no demuestra la verdad de una conclusión.

## Actualizar

En el PowerShell donde ya quedó instalado el comando universal:

```powershell
Actualizar-Sergio
```

El comando local del usuario y `scripts/actualizar-sergio.ps1` no son necesariamente la misma versión: la definición universal instalada no está disponible en esta auditoría. El script Bash del repo preserva código con una ref y exige checkout limpio/fast-forward; no arregla por sí solo la divergencia anterior. No se afirma haber vuelto a ejecutar la actualización completa en ese Windows.

El actualizador debe compilar el frontend: los cambios de fuente de `/nodes` necesitan `npm run build` para sustituir los assets servidos. La compilación se comprobó aquí; no se publican incidentalmente todos los assets generados en esta revisión.

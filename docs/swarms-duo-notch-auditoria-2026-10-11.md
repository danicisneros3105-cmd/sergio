# Swarms, multitasking y notch: revisión e implementación

Revisión del 11 de octubre de 2026. Alcance: interfaces y archivos indicados,
integración con Sergio y regresiones locales. No es una auditoría exhaustiva de
la organización, de todos los repositorios ni una certificación de seguridad.

## Proyectos y decisión

El enlace recibido lleva al catálogo de The-Swarm-Corporation. La API devuelve
404 para `The-Swarm-Corporation/swarms`; el framework enlazado por su proyecto
GraphWorkflow es `kyegomez/swarms`, revisado también en la entrega anterior.

| Proyecto | Commit revisado | Incorporación |
| --- | --- | --- |
| [SkillScanner](https://github.com/The-Swarm-Corporation/SkillScanner/tree/2811b2d57fd5d4dffd41431763e221054628cfc6) | `2811b2d57fd5d4dffd41431763e221054628cfc6` | Adoptar el análisis estático previo a importar skills, con implementación propia y sin dependencias nuevas. |
| [GraphWorkflow-Paper](https://github.com/The-Swarm-Corporation/GraphWorkflow-Paper/tree/9364cb7633825da1ba5009b3dd8c2939d6517816) | `9364cb7633825da1ba5009b3dd8c2939d6517816` | Adoptar validación previa de grafos. Conservar el ejecutor y los límites de trabajadores de Sergio. |
| [Swarms / GraphWorkflow](https://github.com/kyegomez/swarms/blob/cdd3e9ea5311e696ae3594891364b13d04fe0924/swarms/structs/graph_workflow.py) | `cdd3e9ea5311e696ae3594891364b13d04fe0924` | Inspeccionar compilación, validación y planificación. No instalar un segundo motor ni trasladar sus cifras de benchmark a Sergio. |
| [duo-open](https://github.com/marcoazeem/duo-open/tree/b6d6c8dccf63999b407c59ca9c9c6e423ecd2643) | `b6d6c8dccf63999b407c59ca9c9c6e423ecd2643` | Adaptar el mapeo de ángulo a desenfoque del panel interior al notch Qt. Conservar la licencia MIT en el paquete de Windows. |

Archivos examinados de SkillScanner: `pyproject.toml`, `static.py`, `rules.py`,
`models.py`, `api.py` y su modelo de seguridad. GraphWorkflow-Paper: README,
ejemplo diamante y harness de benchmarks; framework: `graph_workflow.py`.
Duo-open: README, LICENSE, `DuoShader.kt`, `Panels.kt`, `FoldEffect.kt`.

SkillScanner instala Swarms incluso para su modo estático. Su API examinada no
incluye autenticación; su documentación señala telemetría del framework por
defecto y límites de la revisión con un modelo. Sergio incorpora un subconjunto
local de sus ideas, sin copiar su código ni enviar skills a un proveedor.

GraphWorkflow compila mapas y capas reutilizables. La compilación inspeccionada
registra ciertos errores de validación; la validación estricta requiere
`validate(raise_on_error=True)`. Sergio rechaza sus planes inválidos antes de
ejecutarlos. Los benchmarks publicados usan nodos sin trabajo: no demuestran
menor latencia de modelos ni mayor precisión de respuestas.

## Correcciones de Sergio

- El enjambre rechazaba referencias válidas e inválidas de forma indistinta al
  filtrar dependencias. Ahora rechaza referencias futuras, al propio paso,
  booleanos, tipos incorrectos y pasos vacíos. Mantiene índices estables.
- Un fanout superior a 300 elementos se rechaza; antes se truncaba en silencio.
  Un fanout de un elemento conserva su destinatario. Máximo 4.000 pasos expandidos.
- Finalizar una actividad es idempotente: una notificación duplicada no convierte
  un fallo en éxito ni reinicia el tiempo de permanencia. Progreso no finito se rechaza.
- Importación de skills: nombres contenidos en el destino, rechazo de enlaces
  simbólicos y archivos especiales, texto de hasta 256 KiB, 500 archivos y 500
  directorios de recursos, hasta 16 MiB. Se revisan los recursos que se copiarán.
- Análisis local: ciertos cambios de instrucciones en español/inglés, delimitadores
  de roles, controles Unicode ocultos y algunos formatos de claves privadas/tokens.
  Base64 se decodifica como texto, con profundidad máxima dos; nunca se ejecuta.
  Los hallazgos muestran reglas y líneas, sin reproducir los secretos coincidentes.
- La copia temporal se vuelve a revisar antes de sustituir la instalación. Los
  enlaces se copian como enlaces para poder rechazarlos. Un fallo de copia o
  promoción intenta conservar/restaurar la instalación anterior; si restaurarla
  falla, se conserva la copia anterior y se indica su ubicación.

El análisis es heurístico: puede bloquear documentación que cite instrucciones
problemáticas y omitir ataques nuevos. Requiere corregir/revisar ese contenido;
`confirm_dangerous` no anula el análisis estático. No audita semánticamente todos
los scripts ni los binarios, no protege de modificaciones posteriores, no es
aislamiento del sistema y no elimina las alucinaciones.

## Animación y filtro líquido

El panel interior de duo-open mapea 20..172 grados a una inclinación visual de
hasta 45 grados. La adaptación Qt resuelve el desenfoque antes de quedar plano;
usa una transición temporal de 650 ms y un pequeño bitmap de 36 píxeles, con
desenfoque aproximado por reescalado. No captura otras aplicaciones ni instala
el servicio de accesibilidad Android; no reproduce exactamente su shader AGSL.

El notch de Windows fusiona las siluetas mediante un menisco vectorial acotado.
La máscara de clic incluye esa misma geometría y deja libre el espacio entre
islas al quedar abierto. Los textos del panel principal permanecen nítidos.

Nodes incluye el filtro SVG suministrado sobre el fondo de su indicador de
objetivos en ejecución: desenfoque 12, matriz alfa 25/-12 y composición `atop`.
Cada instancia tiene un identificador propio; el filtro tiene límites explícitos
y está en el SVG visible, sin depender de un contenedor `display:none`. Textos y
enlace a Agent Swarm quedan fuera del filtro. El filtro se retira tras la
transición; no hay animación perpetua ni actividades ficticias.

El temporizador de render Qt se detiene cuando el notch está oculto. La detección
del cursor en el borde continúa a 20 Hz para recuperarlo. Las actividades se
consultan como máximo cuatro veces por segundo; movimiento usa hasta 60 Hz,
reposo 30 Hz y ocultación por pantalla completa baja a cuatro Hz sin redibujar.
Se respetan la preferencia de animaciones de Windows y `prefers-reduced-motion`
en web. No se han medido FPS ni consumo energético en el PC del usuario.

Licencia incluida: `windows/sergio_escritorio/resources/licenses/duo-open-LICENSE.txt`.
Crédito: marcoazeem/duo-open, copyright 2026 marcoazeem, MIT.

## Validación y actualización

- 1.264 pruebas locales de skills, Nodes, agentes, MCP, ciclo de vida del servidor,
  actualizador, tareas de escritorio y notch, con sockets externos bloqueados.
- 123 pruebas de frontend, comprobación TypeScript y build de producción.
- Ruff de los archivos Python modificados y pruebas de regresión del último
  ajuste de reactivación del temporizador.
- Render Qt offscreen de las fases 100/125/150/180 grados, inspeccionado visualmente.
- Cuatro pruebas marcadas `live` fallaron al intentar ejecutarse sin Ollama y sin
  las skills esperadas en el perfil local. Se excluyeron de la suite offline;
  no se declaran como superadas. No se probaron modelos pagados, Android real,
  instalación Windows ni comportamiento visual del SVG en un navegador real.

Los cambios se publican en `codex/professional-reliability-audit`. Para obtenerlos,
usar el comando PowerShell ya configurado: `Actualizar-Sergio`.

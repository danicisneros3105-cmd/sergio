# Nodes y Agent Swarm: auditoría y alcance de la actualización

## Resultado

La rama `codex/professional-reliability-audit` incorpora Nodes persistentes con diseño procedural propio, objetivos ejecutables y recurrentes, memoria editable con procedencia, auditoría, reglas para bloquear conexiones, integración MCP stdio y CLI, y API de modelos a partir de Dev. No se afirma equivalencia total con servicios propietarios ni ausencia total de errores o alucinaciones.

## Comparación de funciones

Se revisaron las publicaciones oficiales de [Kimi Agent Swarm](https://www.kimi.ai/help/agent/agent-swarm), [Kimi K3](https://www.kimi.ai/blog/kimi-k3), [Meta Muse](https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/), [Dots](https://openai.com/index/introducing-dots/), [la guía de Dots](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot) y [Apple iPhone Duo](https://www.apple.com/iphone-duo/). Las siguientes son correspondencias funcionales, no certificaciones de paridad.

| Referencia | Función | Sergio: estado real |
|---|---|---|
| Kimi Swarm | Coordinación y reparto en paralelo | Grafo de dependencias y expansión por elemento; pool compartido en escritorio. |
| Kimi Swarm | Hasta 300 subagentes | Límite de 300 elementos por expansión; 8 trabajadores simultáneos por defecto, configurable hasta 300. No equivale a rendimiento de la infraestructura Kimi. |
| Kimi Swarm | Miles de pasos/herramientas | Máximo 4000 pasos y 4000 turnos del agente por tarea; cada turno puede usar varias herramientas. No es una medición de 4000 llamadas de herramientas. |
| Kimi Swarm | Contexto por especialista | Cada paso recibe resultados de sus dependencias, con límites por resultado y de contexto. Solicitudes demasiado grandes deben dividirse. |
| Kimi Swarm | Progreso y entregables | Actividades/isla del escritorio, estados de agentes, tareas y trazas existentes; salidas de Nodes en pantalla, pendientes de revisión. |
| Kimi Swarm | Seguimiento y nuevas instrucciones | Mensajes, chat y tareas de Agent Swarm ya existentes; objetivos nuevos de Nodes. |
| Kimi K3 | Acceso al modelo | Ruta Moonshot para `kimi-k3`, selección en interfaz y CLI; requiere clave y acceso del proveedor. Pruebas con dobles de API, sin consumo real. |
| Kimi K3 | PARL, pesos y arquitectura propios | No implementados: requieren entrenamiento y modelo del proveedor. |
| Kimi Swarm | Cifras de aceleración | No se transfieren a Sergio. No se dispone de benchmark equivalente. |
| Muse / Dots | Personaje y perfil personal | Lumen, Bruma y Nival, colores y pelaje ajustables; geometría propia. Perfil y responsabilidad editables. |
| Muse / Dots | Objetivos, proyectos y continuidad | Persistencia SQLite y tareas reales del Agent Manager. Un tick toma un objetivo acotado; las tareas recurrentes vuelven a ejecutarse. |
| Muse / Dots | Trabajo mientras la interfaz está cerrada | Programación local con servidor/equipo encendidos; no un ordenador alojado en la nube. |
| Muse / Dots | Memoria y correcciones | Notas con fuente, edición del perfil y borrado de recuerdos. El borrado afecta la memoria de Nodes; no borra retroactivamente tareas ni trazas anteriores. |
| Dots | Aprendizaje por feedback | Módulo de aprendizaje y trazas existente en Agent Swarm, accesible desde Nodes. No se demuestra equivalencia con aprendizaje propietario. |
| Muse / Dots | Actividad y pausa | Estado real de las tareas, resultados, auditoría, pausa y reanudación. Una llamada activa puede terminar antes de detenerse. |
| Muse / Dots | Permisos | Herramientas automáticas de lectura; conexión local bloqueable; revisión de comando/herramienta/argumentos exactos, con ticket de 120 segundos y un solo uso. |
| Muse / Dots | Navegación y tareas profesionales | Herramientas existentes de navegador, escritorio, documentos y desarrollo; no todas habilitadas en un Node automático. |
| Muse / Dots | Apps y canales | Infraestructura existente de conectores, Slack/Teams/correo y MCP; requiere cuentas configuradas. No hay equivalencia probada con un catálogo de miles de apps. |
| Dots | Identidad corporativa, hardware de IT y Agent 365 | No implementados como plataforma de identidad empresarial; requieren IdP, aprovisionamiento e integración externos. |
| Dots | Móvil y voz | PWA, emparejamiento y voz existentes; requieren servidor y permisos de dispositivos. |
| Muse / Dots | Credenciales opacas al modelo | Las nuevas claves no se devuelven al navegador ni se añaden a memoria/auditoría de Nodes; los procesos no heredan claves del modelo. No hay un vault aislado equivalente: un CLI autorizado conserva acceso a archivos del usuario. |
| Muse / Dots | Ordenador/VM en nube | Pendiente de infraestructura y aislamiento real. Los límites de subprocess no constituyen una VM. |
| Muse | Sentinel y control independiente de red | No implementados como producto equivalente; las conexiones locales requieren revisión, pero no hay aislamiento de red por VM. |
| Muse | Pagos, tarjetas temporales, protecciones de compra | No implementados. Requieren proveedores, cuentas y autorización de cada transacción. |
| Muse | Shop Pay, 1Password y Confidential VM anunciados futuros | No implementados ni presentados como disponibles en Sergio. |
| Apple Duo | Apertura con transformación y desenfoque | Recreación propia con dos paneles, rotación, blur y desaparición de la capa a los 700 ms; respeta movimiento reducido. No se verificó identidad visual ni se reutilizaron recursos de Apple. |

## Problemas corregidos

- El Swarm creaba un hilo por paso independiente. Ahora usa un pool compartido, limita admisión a 64 tareas y conserva como máximo unas 200 entradas de historial. El endpoint de ejecución manual del servidor limita sus trabajadores a 8.
- La caché normalizaba mayúsculas, acentos y símbolos: podía reutilizar el plan de otro archivo o comando. Ahora conserva la instrucción en la clave y distingue una lista vacía de herramientas de una lista no especificada.
- La caché también conserva la composición Unicode: nombres NFC y NFD pueden ser archivos distintos en Linux.
- Un veredicto ausente del revisor podía contarse como éxito. Ahora falla la verificación; si un archivo no se puede comprobar, no se acepta como prueba de entrega.
- Un Node sin objetivos no realiza llamadas al modelo. Los objetivos almacenados en Nodes no llegaban al ejecutor. Ahora entran en el tick y producen resultados `needs_review`, nunca `verified` por una mera respuesta del modelo.
- Los subprocess MCP podían dejar descendientes abiertos. Ahora se terminan por grupo en POSIX y por Job Object en Windows. Se limita el tamaño de línea y se drena stderr sin guardarlo.
- Las conexiones CLI tienen límite de 30 segundos y 64 KB por flujo. MCP tiene timeout de respuesta de 10 segundos y línea de hasta 1 MiB. Dos conexiones pueden ejecutarse a la vez; la saturación devuelve 429.
- Guardar API se valida en servidor y CLI de nube; las rutas antiguas de escritura directa de Tauri se bloquean. También se comprueba Dev para guardar credenciales de herramientas. Revocar claves sigue permitido con licencia vencida. Las ediciones de Nodes prevalecen sobre claves heredadas al reiniciar.
- El instalador Windows elige Python oficial 3.13 firmado, prueba `decimal`, `bz2` y módulos de escritorio, y dirige los accesos al entorno nuevo. No cambia la política de seguridad de Windows. La salida distingue un proceso iniciado de una interfaz visible.
- El actualizador PowerShell escribe un archivo UTF-8 con LF y lo ejecuta por argumentos, evitando el problema de CR final y del PATH con paréntesis.

## Skills

Se agregan cinco skills de la aplicación: desarrollo verificable, investigación con fuentes, integraciones bajo control, memoria/objetivos y rendimiento medible. Se inyectan por coincidencia temática con un presupuesto de 2400 caracteres. Los permisos y límites se implementan en código; las instrucciones de una skill no sustituyen esos controles.

## Verificación y límites

Los tests usan cuentas y APIs simuladas, servidores MCP locales reales, SQLite y subprocess reales. No ejecutan pagos ni envían mensajes. La revisión automática bloqueó un intento de suite general por posible acceso a Google Tasks. Se inspeccionaron los tests: los unitarios usan token ficticio y API reemplazada; las pruebas de cuentas reales deben quedar excluidas. Se añadió una barrera que bloquea llamadas Google Tasks no simuladas y una activación explícita para las pruebas reales. La validación se hizo con mocks, excluyendo tests live/cloud.

Resultados finales por tandas aisladas: **10.080 pruebas generales aprobadas**, 84 omitidas y 32 excluidas por marcador; **681 pruebas de escritorio, Nodes y planificación aprobadas**, 4 omitidas; **118 pruebas de frontend aprobadas**, TypeScript y build de producción correctos. También pasan las 2 pruebas unitarias simuladas de Google Tasks y las 15 de Swarm/actualizador/instalación. Los recuentos de tandas se solapan y no deben sumarse como pruebas únicas.

Una ejecución conjunta con Qt 6.12.0 pasó 10.737 assertions pero terminó con SIGSEGV al cerrar el proceso. La tanda de Qt reprodujo el cierre con 6.12.0 y terminó correctamente con 6.11.2, sin cambiar los tests. Se fija `PySide6-Essentials==6.11.2` en el proyecto Windows para instalar la versión comprobada; esto no sustituye una prueba nativa en Windows. El backend general también termina con código 0 cuando se prueba separado de Qt.

La suite cubre persistencia, aislamiento entre Nodes, borrado, objetivos que llegan al ejecutor, recurrencia, Dev con firmas de licencia reales de prueba, revocación, autorización de un uso, cambios de argumentos, bloqueo y eliminación de conexiones, ausencia de claves heredadas, límites de salida, 300 pasos con 4 trabajadores, errores de subagentes y verificación de archivos.

La revisión visual usa los SVG producidos por los componentes React reales, renderizados con Qt. El frontend se valida con TypeScript, Vitest y build de producción. Los tests Qt se ejecutan sin pantalla en Linux. No se dispone del equipo Windows del usuario para comprobar Smart App Control, control real del cursor, micrófono, cámara, GPU ni los módulos opcionales instalados allí. Tampoco se compila aquí el binario completo Tauri ni se compara la animación en un iPhone físico.

API solo desde Dev: la licencia necesita un emisor con clave pública configurada. No se inventa un precio, una cuenta de pago ni una licencia del usuario.

## Uso

Abre `http://localhost:8000/nodes` con Sergio activo. En el compañero de Windows puedes escoger «Node peludito» en los ajustes de apariencia; el estilo anterior se conserva si ya lo habías elegido. Crea un personaje, agrega recuerdos con fuente y ejecuta un objetivo. Para programar, configura al menos cinco minutos. Para MCP/CLI agrega un programa instalado como lista JSON, descubre herramientas y revisa una llamada con argumentos explícitos. Usa las opciones Bloquear y Revocar para detener futuros usos. Los canales y trazas se gestionan en Agent Swarm.

La configuración privada y los datos del usuario se conservan al actualizar. El comando final se proporciona con el SHA realmente publicado; no debe reutilizarse un SHA anterior ni agregarse dentro de una cadena `bash -lc` con PATH de Windows expandido.

# Integraciones y coordinación de Sergio

Revisión del 11 de octubre de 2026. Se revisaron interfaces y código concreto;
esto no es una auditoría exhaustiva de todos los archivos ni una certificación de seguridad.

## Decisión por proyecto

| Proyecto | Commit inspeccionado | Decisión |
| --- | --- | --- |
| [Anil-matcha/open-dots](https://github.com/Anil-matcha/open-dots/tree/fb871a1549911981658383f994215fba9dcb3949) | `fb871a1549911981658383f994215fba9dcb3949` | Adoptar el patrón de pausa tras tres fallos de tareas recurrentes, con código propio. No copiar ni instalar su backend. |
| [openclaw/openclaw](https://github.com/openclaw/openclaw/tree/3529142cc84f8b45d00bda9c78e03d29e82dfd7d) | `3529142cc84f8b45d00bda9c78e03d29e82dfd7d` | Adaptador opcional de CLI instalada, con argumentos revisados y límite de 30 segundos. |
| [kyegomez/swarms](https://github.com/kyegomez/swarms/tree/cdd3e9ea5311e696ae3594891364b13d04fe0924) | `cdd3e9ea5311e696ae3594891364b13d04fe0924` | Implementación propia de coordinación secuencial y dos especialistas en paralelo con síntesis. No añadir el paquete completo. |
| [browser-use/browser-use](https://github.com/browser-use/browser-use/tree/c75e8476e26d18b7617643bc2ae082fae8eae431) | `c75e8476e26d18b7617643bc2ae082fae8eae431` | Adaptador MCP stdio opcional con sesión persistente, para ejecutar varias acciones sobre el mismo navegador. |

Open Dots declara ser un prototipo y describe dependencias de Boat, PostgreSQL,
OAuth y una URL pública para aprobaciones. Su README reconoce que la interfaz
web no tiene autenticación real. Aunque su descripción dice MIT, el árbol del
commit revisado no contiene LICENSE/NOTICE: no se ha copiado su implementación.
Se inspeccionó `backend/app/services/permission_service.py` y la documentación
de programación y limitaciones.

Se comprobaron las licencias MIT de OpenClaw y Browser-use y Apache-2.0 de
Swarms. No se distribuye código de esos proyectos: las conexiones llaman
interfaces de programas instalados por el propietario y los flujos son propios.

## Lo que cambió

- Nodes muestra presets de Browser-use y OpenClaw, detectando su ejecutable
  sin lanzarlo ni instalarlo. Agregar una conexión no ejecuta el programa.
- Browser-use usa `browser-use --mcp`, comprobado en su `browser_use/cli.py`
  y `browser_use/mcp/server.py`. Cada llamada requiere el ticket de revisión
  existente, ligado al comando, argumentos y revisión de la sesión.
- MCP persistente conserva el proceso entre acciones, admite dos sesiones
  retenidas y serializa las acciones. Se cierra tras 120 segundos de inactividad,
  al bloquear/revocar/editar la conexión, por fallo de transporte o al apagar
  el servidor. Hay botón de cierre manual. Respuestas MCP limitadas a 30 segundos.
- Una acción o cierre invalida las autorizaciones MCP anteriores. La revisión
  se comprueba de nuevo dentro del bloqueo de ejecución para evitar carreras.
  Esto no detecta cambios autónomos de una web: vuelve a obtener su estado antes
  de usar índices de elementos. No se reejecuta automáticamente una llamada fallida.
- CLI admite argumentos JSON en la interfaz, sin intérprete de shell. Conserva
  los límites de proceso y salida y no hereda las claves API del servidor.
- Un objetivo puede usar un agente, tres etapas secuenciales o dos especialistas
  independientes y una síntesis. Estos modos siguen usando AgentExecutor y sus
  permisos. No llaman a Swarms. Los flujos con especialistas comparten ocho
  plazas de ejecución; cada flujo paralelo crea como máximo dos trabajadores.
- Contextos limitados a 32.000 caracteres por etapa y propuestas recortadas a
  6.000 caracteres. Los metadatos de uso de etapas completadas se suman cuando
  están disponibles. Cada etapa conserva su límite de turnos; tres etapas pueden
  consumir más tokens que un objetivo simple. El uso no informado por un proveedor
  o una etapa que falla antes de devolver resultados no puede contabilizarse aquí.
- Tres fallos consecutivos pausan el agente de un objetivo recurrente. Reanudar
  restablece sus contadores. La interfaz muestra la pausa. Una revisión por otro
  modelo no convierte el resultado en evidencia: permanece `verified: false`.
- Dos skills de Sergio guían navegación revisada y coordinación limitada.
  La configuración de claves dentro de Sergio sigue requiriendo Dev o superior.

## Instalación opcional

La actualización normal no instala motores externos ni sus dependencias.
Browser-use 0.13.11 fue probado en un entorno separado. Para instalarlo en WSL:

```bash
uv tool install --python 3.13 browser-use==0.13.11
```

Después, en Nodes, pulsa **Comprobar programas instalados** y agrega Browser-use.
La navegación real necesita un navegador y sus dependencias disponibles para el
runtime. Algunas herramientas de extracción/agente requieren además un proveedor
de modelo y pueden tener coste. No se conecta automáticamente tu Chrome personal.

OpenClaw debe instalarse y configurarse siguiendo su documentación oficial.
El preset permite comprobarlo con argumentos `["--version"]`. Si ejecutas un
agente de OpenClaw, autorizas sus acciones internas como una delegación completa:
configura también sus permisos. Un Gateway externo puede continuar después de un
timeout de la CLI; comprueba la sesión antes de repetir una operación.

## Validación

- 897 pruebas de Nodes, agentes, MCP, ciclo de vida del servidor y actualizador,
  con sockets externos bloqueados y credenciales de prueba.
- 120 pruebas del frontend; comprobación TypeScript y build de producción.
- Ruff de los archivos Python modificados.
- Browser-use 0.13.11 instalado en entorno aislado: inicialización MCP real y
  descubrimiento de 16 herramientas, seguido de cierre del proceso.
- Servidor MCP de prueba ejecutado como proceso real: conservación del estado
  entre llamadas, rechazo de tickets antiguos, cierre por inactividad y capacidad.
- Pruebas de ejecución de especialistas independientes, dependencias, suma de uso,
  bloqueo de síntesis si falla un especialista y pausa/reanudación tras tres fallos.

No se probaron llamadas pagadas, cuentas personales, navegación completa con
Chromium, ejecución real de agentes OpenClaw ni el instalador nativo de Windows
en este entorno. MCP/CLI no son aislamiento de archivos ni eliminan alucinaciones.
La versión se publica en `codex/professional-reliability-audit`; se obtiene con
el comando `Actualizar-Sergio` configurado en PowerShell.
